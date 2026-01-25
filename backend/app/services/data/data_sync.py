"""Data synchronization service for pulling and storing TaoStats data."""

from datetime import datetime, timezone
from decimal import Decimal
from typing import Dict, List, Optional, Any

import structlog
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import get_settings
from app.core.database import get_db_context
from app.models.subnet import Subnet, SubnetSnapshot
from app.models.position import Position, PositionSnapshot
from app.models.portfolio import PortfolioSnapshot
from app.models.slippage import SlippageSurface
from app.models.validator import Validator
from app.services.data.taostats_client import taostats_client, TaoStatsError

settings = get_settings()
logger = structlog.get_logger()

# Standard slippage test sizes per spec
SLIPPAGE_TEST_SIZES = [Decimal("2"), Decimal("5"), Decimal("10"), Decimal("15"), Decimal("20")]

# Conversion: 1 TAO = 1e9 rao
RAO_PER_TAO = Decimal("1000000000")


def rao_to_tao(rao: str | int | Decimal) -> Decimal:
    """Convert rao to TAO."""
    return Decimal(str(rao)) / RAO_PER_TAO


class DataSyncService:
    """Service for synchronizing data from TaoStats to local database."""

    def __init__(self):
        self.wallet_address = settings.wallet_address
        self._last_sync: Optional[datetime] = None
        self._last_sync_results: Dict[str, Any] = {}

    async def sync_all(self, include_analysis: bool = True) -> Dict[str, Any]:
        """Run full data synchronization.

        Args:
            include_analysis: If True, run transaction sync, cost basis, NAV, and risk analysis.
        """
        logger.info("Starting full data sync", wallet=self.wallet_address, include_analysis=include_analysis)
        results = {
            "subnets": 0,
            "pools": 0,
            "positions": 0,
            "validators": 0,
            "slippage_surfaces": 0,
            "transactions": 0,
            "cost_basis_computed": False,
            "nav_computed": False,
            "risk_check": False,
            "portfolio_snapshot": False,
            "errors": [],
            "timestamp": datetime.now(timezone.utc).isoformat(),
        }

        try:
            # Sync subnets and pools
            subnet_count = await self.sync_subnets()
            results["subnets"] = subnet_count

            pool_count = await self.sync_pools()
            results["pools"] = pool_count

            # Sync wallet positions
            position_count = await self.sync_positions()
            results["positions"] = position_count

            # Sync validators
            validator_count = await self.sync_validators()
            results["validators"] = validator_count

            # Create portfolio snapshot
            await self.create_portfolio_snapshot()
            results["portfolio_snapshot"] = True

            if include_analysis:
                # Lazy imports to avoid circular imports
                from app.services.analysis.transaction_sync import transaction_sync_service
                from app.services.analysis.cost_basis import cost_basis_service
                from app.services.analysis.slippage_sync import slippage_sync_service
                from app.services.analysis.nav_calculator import nav_calculator
                from app.services.analysis.risk_monitor import risk_monitor

                # Sync transaction history
                try:
                    tx_results = await transaction_sync_service.sync_transactions()
                    results["transactions"] = tx_results.get("new_transactions", 0)
                except Exception as e:
                    logger.error("Transaction sync failed", error=str(e))
                    results["errors"].append(f"Transaction sync: {str(e)}")

                # Compute cost basis from transactions
                try:
                    cb_results = await cost_basis_service.compute_all_cost_basis()
                    results["cost_basis_computed"] = cb_results.get("positions_computed", 0) > 0
                except Exception as e:
                    logger.error("Cost basis computation failed", error=str(e))
                    results["errors"].append(f"Cost basis: {str(e)}")

                # Sync slippage surfaces
                try:
                    slip_results = await slippage_sync_service.sync_slippage_surfaces()
                    results["slippage_surfaces"] = slip_results.get("surfaces_updated", 0)
                except Exception as e:
                    logger.error("Slippage sync failed", error=str(e))
                    results["errors"].append(f"Slippage sync: {str(e)}")

                # Compute NAV with executable pricing
                try:
                    nav_result = await nav_calculator.compute_portfolio_nav()
                    results["nav_computed"] = True
                    results["nav_executable_tao"] = float(nav_result.get("nav_executable_tao", 0))
                except Exception as e:
                    logger.error("NAV computation failed", error=str(e))
                    results["errors"].append(f"NAV: {str(e)}")

                # Run risk check
                try:
                    risk_result = await risk_monitor.run_risk_check()
                    results["risk_check"] = True
                    results["risk_score"] = risk_result.get("risk_score", 0)
                    results["alerts"] = len(risk_result.get("alerts", []))
                except Exception as e:
                    logger.error("Risk check failed", error=str(e))
                    results["errors"].append(f"Risk check: {str(e)}")

            self._last_sync = datetime.now(timezone.utc)
            self._last_sync_results = results
            logger.info("Data sync completed", results=results)

        except Exception as e:
            logger.error("Data sync failed", error=str(e))
            results["errors"].append(str(e))

        return results

    async def sync_subnets(self) -> int:
        """Sync subnet data from TaoStats."""
        logger.info("Syncing subnets")

        try:
            response = await taostats_client.get_subnets()
            subnets_data = response.get("data", [])

            async with get_db_context() as db:
                count = 0
                for subnet_data in subnets_data:
                    netuid = subnet_data.get("netuid")
                    if netuid is None:
                        continue

                    await self._upsert_subnet(db, subnet_data)
                    count += 1

                await db.commit()
                logger.info("Subnets synced", count=count)
                return count

        except Exception as e:
            logger.error("Failed to sync subnets", error=str(e))
            raise

    async def _upsert_subnet(self, db: AsyncSession, subnet_data: Dict) -> Subnet:
        """Insert or update subnet record."""
        netuid = subnet_data.get("netuid")
        stmt = select(Subnet).where(Subnet.netuid == netuid)
        result = await db.execute(stmt)
        subnet = result.scalar_one_or_none()

        now = datetime.now(timezone.utc)

        if subnet is None:
            subnet = Subnet(netuid=netuid, created_at=now)
            db.add(subnet)

        # Update fields from API response
        subnet.name = subnet_data.get("name") or f"Subnet {netuid}"
        subnet.description = subnet_data.get("description")
        subnet.owner_address = subnet_data.get("owner", {}).get("ss58") if isinstance(subnet_data.get("owner"), dict) else subnet_data.get("owner")
        subnet.owner_take = Decimal(str(subnet_data.get("owner_take", 0) or 0))

        # Registration date and age - API uses registration_timestamp
        registered = subnet_data.get("registration_timestamp") or subnet_data.get("registered_at") or subnet_data.get("created_at")
        if registered:
            try:
                if isinstance(registered, str):
                    subnet.registered_at = datetime.fromisoformat(registered.replace("Z", "+00:00"))
                subnet.age_days = (now - subnet.registered_at).days if subnet.registered_at else 0
            except (ValueError, TypeError):
                pass

        # Emission - API returns raw emission, we store as proportion of total (converted later)
        # For now store raw emission value, eligibility gate will handle thresholds
        raw_emission = subnet_data.get("emission", 0) or subnet_data.get("projected_emission", 0) or 0
        # Emission is in rao, convert to TAO proportion (rough estimate)
        subnet.emission_share = Decimal(str(raw_emission)) / Decimal("1e18") if raw_emission else Decimal("0")
        subnet.total_stake_tao = rao_to_tao(subnet_data.get("total_stake", 0) or 0)

        # Taoflow metrics from API - net_flow fields are already in TAO
        flow_1d = subnet_data.get("net_flow_1_day", 0) or 0
        flow_7d = subnet_data.get("net_flow_7_days", 0) or 0
        flow_30d = subnet_data.get("net_flow_30_days", 0) or 0
        # Store as proportional change (rough estimate based on pool size or fixed scale)
        # These are absolute TAO values, convert to approximate proportion
        subnet.taoflow_1d = Decimal(str(flow_1d)) / Decimal("1e9") if flow_1d else Decimal("0")
        subnet.taoflow_7d = Decimal(str(flow_7d)) / Decimal("1e9") if flow_7d else Decimal("0")
        subnet.taoflow_14d = Decimal(str(flow_30d)) / Decimal("2e9") if flow_30d else Decimal("0")  # Use 30d/2 as proxy for 14d

        # Holder count - not in subnet API, may come from different endpoint
        subnet.holder_count = int(subnet_data.get("holder_count", 0) or subnet_data.get("active_keys", 0) or 100)

        subnet.updated_at = now
        return subnet

    async def sync_pools(self) -> int:
        """Sync dTAO pool data from TaoStats."""
        logger.info("Syncing pools")

        try:
            response = await taostats_client.get_pools()
            pools_data = response.get("data", [])

            async with get_db_context() as db:
                count = 0
                for pool_data in pools_data:
                    netuid = pool_data.get("netuid")
                    if netuid is None:
                        continue

                    await self._update_subnet_pool(db, pool_data)
                    await self._create_subnet_snapshot(db, netuid, pool_data)
                    count += 1

                await db.commit()
                logger.info("Pools synced", count=count)
                return count

        except Exception as e:
            logger.error("Failed to sync pools", error=str(e))
            raise

    async def _update_subnet_pool(self, db: AsyncSession, pool_data: Dict) -> Optional[Subnet]:
        """Update subnet with pool data."""
        netuid = pool_data.get("netuid")
        stmt = select(Subnet).where(Subnet.netuid == netuid)
        result = await db.execute(stmt)
        subnet = result.scalar_one_or_none()

        if subnet is None:
            return None

        # Pool API has the actual subnet name
        pool_name = pool_data.get("subnet_name") or pool_data.get("name")
        if pool_name:
            subnet.name = pool_name

        # Pool metrics - API returns total_tao, total_alpha (in rao)
        subnet.pool_tao_reserve = rao_to_tao(pool_data.get("total_tao", 0) or pool_data.get("tao_reserve", 0) or 0)
        subnet.pool_alpha_reserve = rao_to_tao(pool_data.get("total_alpha", 0) or pool_data.get("alpha_reserve", 0) or 0)
        subnet.alpha_price_tao = Decimal(str(pool_data.get("price", 0) or 0))

        subnet.updated_at = datetime.now(timezone.utc)
        return subnet

    async def _create_subnet_snapshot(self, db: AsyncSession, netuid: int, pool_data: Dict) -> SubnetSnapshot:
        """Create subnet snapshot for history."""
        # Get current subnet for additional data
        stmt = select(Subnet).where(Subnet.netuid == netuid)
        result = await db.execute(stmt)
        subnet = result.scalar_one_or_none()

        snapshot = SubnetSnapshot(
            netuid=netuid,
            timestamp=datetime.now(timezone.utc),
            alpha_price_tao=Decimal(str(pool_data.get("price", 0) or 0)),
            pool_tao_reserve=rao_to_tao(pool_data.get("total_tao", 0) or pool_data.get("tao_reserve", 0) or 0),
            pool_alpha_reserve=rao_to_tao(pool_data.get("total_alpha", 0) or pool_data.get("alpha_reserve", 0) or 0),
            emission_share=subnet.emission_share if subnet else Decimal("0"),
            holder_count=subnet.holder_count if subnet else 0,
            flow_regime=subnet.flow_regime if subnet else "neutral",
        )
        db.add(snapshot)
        return snapshot

    async def sync_positions(self) -> int:
        """Sync wallet positions from TaoStats."""
        logger.info("Syncing positions", wallet=self.wallet_address)

        try:
            # Get account data
            account_response = await taostats_client.get_account(self.wallet_address)
            account_data = account_response.get("data", [{}])[0] if account_response.get("data") else {}

            # Get stake balances (use coldkey to get all dTAO positions)
            stake_response = await taostats_client.get_stake_balance(coldkey=self.wallet_address)
            stakes_data = stake_response.get("data", [])

            # Deduplicate by netuid - keep only the latest entry for each netuid
            # The API may return multiple entries per netuid (historical data)
            stakes_by_netuid: Dict[int, Dict] = {}
            for stake_data in stakes_data:
                netuid = stake_data.get("netuid")
                if netuid is None:
                    continue
                # Keep the first (most recent) entry for each netuid
                if netuid not in stakes_by_netuid:
                    stakes_by_netuid[netuid] = stake_data

            async with get_db_context() as db:
                count = 0

                for netuid, stake_data in stakes_by_netuid.items():
                    await self._upsert_position(db, stake_data)
                    await self._create_position_snapshot(db, stake_data)
                    count += 1

                await db.commit()
                logger.info("Positions synced", count=count)
                return count

        except Exception as e:
            logger.error("Failed to sync positions", error=str(e))
            raise

    async def _upsert_position(self, db: AsyncSession, stake_data: Dict) -> Position:
        """Insert or update position record."""
        netuid = stake_data.get("netuid")
        stmt = select(Position).where(
            Position.wallet_address == self.wallet_address,
            Position.netuid == netuid,
        )
        result = await db.execute(stmt)
        position = result.scalar_one_or_none()

        now = datetime.now(timezone.utc)

        # Get subnet name
        subnet_stmt = select(Subnet).where(Subnet.netuid == netuid)
        subnet_result = await db.execute(subnet_stmt)
        subnet = subnet_result.scalar_one_or_none()
        subnet_name = subnet.name if subnet else f"Subnet {netuid}"

        if position is None:
            position = Position(
                wallet_address=self.wallet_address,
                netuid=netuid,
                subnet_name=subnet_name,
                created_at=now,
                entry_date=now,
            )
            db.add(position)
        else:
            position.subnet_name = subnet_name

        # Update position data - 'balance' is alpha balance in rao
        alpha_balance = rao_to_tao(stake_data.get("balance", 0) or 0)
        position.alpha_balance = alpha_balance

        # Get TAO value from 'balance_as_tao' (mid valuation in rao)
        tao_value = rao_to_tao(stake_data.get("balance_as_tao", 0) or 0)
        position.tao_value_mid = tao_value

        # Compute alpha price from balance ratio
        if alpha_balance > 0:
            alpha_price = tao_value / alpha_balance
        else:
            alpha_price = Decimal("0")

        # Set entry price if first time
        if position.entry_price_tao == 0 and alpha_price > 0:
            position.entry_price_tao = alpha_price
            position.cost_basis_tao = tao_value

        # Extract validator hotkey from nested structure
        hotkey_data = stake_data.get("hotkey")
        if isinstance(hotkey_data, dict):
            position.validator_hotkey = hotkey_data.get("ss58")
        else:
            position.validator_hotkey = hotkey_data

        position.updated_at = now

        return position

    async def _create_position_snapshot(self, db: AsyncSession, stake_data: Dict) -> PositionSnapshot:
        """Create position snapshot for history."""
        netuid = stake_data.get("netuid")
        alpha_balance = rao_to_tao(stake_data.get("balance", 0) or 0)
        tao_value = rao_to_tao(stake_data.get("balance_as_tao", 0) or 0)

        # Compute alpha price from balance ratio
        if alpha_balance > 0:
            alpha_price = tao_value / alpha_balance
        else:
            alpha_price = Decimal("0")

        snapshot = PositionSnapshot(
            wallet_address=self.wallet_address,
            netuid=netuid,
            timestamp=datetime.now(timezone.utc),
            alpha_balance=alpha_balance,
            tao_value_mid=tao_value,
            alpha_price_tao=alpha_price,
        )
        db.add(snapshot)
        return snapshot

    async def sync_validators(self) -> int:
        """Sync validator data from TaoStats."""
        logger.info("Syncing validators")

        try:
            response = await taostats_client.get_validators()
            validators_data = response.get("data", [])

            async with get_db_context() as db:
                count = 0
                for val_data in validators_data:
                    await self._upsert_validator(db, val_data)
                    count += 1

                await db.commit()
                logger.info("Validators synced", count=count)
                return count

        except Exception as e:
            logger.error("Failed to sync validators", error=str(e))
            raise

    async def _upsert_validator(self, db: AsyncSession, val_data: Dict) -> Validator:
        """Insert or update validator record."""
        hotkey = val_data.get("hotkey", {}).get("ss58") if isinstance(val_data.get("hotkey"), dict) else val_data.get("hotkey")
        netuid = val_data.get("netuid")

        if not hotkey or netuid is None:
            return None

        stmt = select(Validator).where(
            Validator.hotkey == hotkey,
            Validator.netuid == netuid,
        )
        result = await db.execute(stmt)
        validator = result.scalar_one_or_none()

        now = datetime.now(timezone.utc)

        if validator is None:
            validator = Validator(
                hotkey=hotkey,
                netuid=netuid,
                created_at=now,
            )
            db.add(validator)

        validator.name = val_data.get("name")
        validator.coldkey = val_data.get("coldkey", {}).get("ss58") if isinstance(val_data.get("coldkey"), dict) else val_data.get("coldkey")
        validator.vtrust = Decimal(str(val_data.get("vtrust", 0) or 0))
        validator.stake_tao = rao_to_tao(val_data.get("stake", 0) or 0)
        validator.take_rate = Decimal(str(val_data.get("take", 0) or 0))
        validator.apy = Decimal(str(val_data.get("apy", 0) or 0))
        validator.is_active = val_data.get("is_active", True)
        validator.updated_at = now

        return validator

    async def sync_slippage_surfaces(self, netuids: Optional[List[int]] = None) -> int:
        """Compute and cache slippage surfaces for subnets.

        Per spec: maintain surfaces for sizes 2, 5, 10, 15, 20 TAO
        """
        logger.info("Syncing slippage surfaces")

        async with get_db_context() as db:
            # Get netuids to process
            if netuids is None:
                stmt = select(Subnet.netuid).where(Subnet.pool_tao_reserve > 0)
                result = await db.execute(stmt)
                netuids = [row[0] for row in result.fetchall()]

            count = 0
            for netuid in netuids:
                for size in SLIPPAGE_TEST_SIZES:
                    for action in ["stake", "unstake"]:
                        try:
                            slippage_data = await taostats_client.get_slippage(
                                netuid=netuid,
                                amount=size,
                                action=action,
                            )
                            await self._upsert_slippage_surface(db, netuid, action, size, slippage_data)
                            count += 1
                        except TaoStatsError as e:
                            logger.warning("Slippage fetch failed", netuid=netuid, size=size, error=str(e))

            await db.commit()
            logger.info("Slippage surfaces synced", count=count)
            return count

    async def _upsert_slippage_surface(
        self,
        db: AsyncSession,
        netuid: int,
        action: str,
        size: Decimal,
        slippage_data: Dict
    ) -> SlippageSurface:
        """Insert or update slippage surface record."""
        stmt = select(SlippageSurface).where(
            SlippageSurface.netuid == netuid,
            SlippageSurface.action == action,
            SlippageSurface.size_tao == size,
        )
        result = await db.execute(stmt)
        surface = result.scalar_one_or_none()

        now = datetime.now(timezone.utc)

        if surface is None:
            surface = SlippageSurface(
                netuid=netuid,
                action=action,
                size_tao=size,
            )
            db.add(surface)

        data = slippage_data.get("data", [{}])[0] if slippage_data.get("data") else {}
        surface.slippage_pct = Decimal(str(data.get("slippage_pct", 0) or 0))
        surface.expected_output = Decimal(str(data.get("expected_output", 0) or 0))
        surface.pool_tao_reserve = rao_to_tao(data.get("pool_tao", 0) or 0)
        surface.pool_alpha_reserve = rao_to_tao(data.get("pool_alpha", 0) or 0)
        surface.computed_at = now

        return surface

    async def create_portfolio_snapshot(self) -> PortfolioSnapshot:
        """Create portfolio-level snapshot."""
        logger.info("Creating portfolio snapshot")

        async with get_db_context() as db:
            # Get all positions
            stmt = select(Position).where(Position.wallet_address == self.wallet_address)
            result = await db.execute(stmt)
            positions = result.scalars().all()

            # Get TAO price
            try:
                price_data = await taostats_client.get_tao_price()
                price_info = price_data.get("data", [{}])[0] if price_data.get("data") else {}
                tao_price_usd = Decimal(str(price_info.get("price", 0) or 0))
            except TaoStatsError:
                tao_price_usd = Decimal("0")

            # Get wallet TAO balance
            try:
                account_data = await taostats_client.get_account(self.wallet_address)
                account_info = account_data.get("data", [{}])[0] if account_data.get("data") else {}
                tao_balance = rao_to_tao(account_info.get("balance_free", 0) or 0)
                root_stake = rao_to_tao(account_info.get("balance_staked_root", 0) or 0)
            except TaoStatsError:
                tao_balance = Decimal("0")
                root_stake = Decimal("0")

            # Calculate totals
            dtao_value_mid = sum(p.tao_value_mid for p in positions)
            nav_mid = tao_balance + root_stake + dtao_value_mid

            snapshot = PortfolioSnapshot(
                wallet_address=self.wallet_address,
                timestamp=datetime.now(timezone.utc),
                total_tao_balance=tao_balance,
                nav_mid=nav_mid,
                nav_exec_50pct=nav_mid,  # Will be computed by analysis service
                nav_exec_100pct=nav_mid,  # Will be computed by analysis service
                tao_price_usd=tao_price_usd,
                nav_usd=nav_mid * tao_price_usd,
                root_allocation_tao=root_stake,
                dtao_allocation_tao=dtao_value_mid,
                unstaked_buffer_tao=tao_balance,
                active_positions=len(positions),
            )
            db.add(snapshot)
            await db.commit()

            logger.info("Portfolio snapshot created", nav_mid=nav_mid, positions=len(positions))
            return snapshot

    @property
    def last_sync(self) -> Optional[datetime]:
        """Get last sync timestamp."""
        return self._last_sync

    def is_data_stale(self) -> bool:
        """Check if data is stale."""
        if self._last_sync is None:
            return True
        age_minutes = (datetime.now(timezone.utc) - self._last_sync).total_seconds() / 60
        return age_minutes > settings.stale_data_threshold_minutes


# Singleton instance
data_sync_service = DataSyncService()
