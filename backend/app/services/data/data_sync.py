"""Data synchronization service for pulling and storing TaoStats data."""

from datetime import datetime, timezone, timedelta
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
from app.models.transaction import DelegationEvent, PositionYieldHistory
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
            "delegation_events": 0,
            "yield_history_records": 0,
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

            # Sync yield data to positions (uses validator APY data)
            yield_count = await self.sync_position_yields()
            results["positions_with_yield"] = yield_count

            # Sync delegation events for historical income tracking
            try:
                delegation_count = await self.sync_delegation_events()
                results["delegation_events"] = delegation_count
            except Exception as e:
                logger.warning("Delegation events sync failed", error=str(e))
                results["delegation_events"] = 0

            # Sync stake balance history for actual yield calculation
            try:
                yield_history_count = await self.sync_stake_balance_history(days=30)
                results["yield_history_records"] = yield_history_count
            except Exception as e:
                logger.warning("Stake balance history sync failed", error=str(e))
                results["yield_history_records"] = 0

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
        """Sync validator yield data from TaoStats.

        Uses the validator/yield endpoint which provides per-subnet APY data.
        Fetches validators specifically for subnets we have positions in.
        """
        logger.info("Syncing validators with yield data")

        try:
            async with get_db_context() as db:
                # First, get the list of netuids we have positions in
                pos_stmt = select(Position.netuid).where(
                    Position.wallet_address == self.wallet_address
                ).distinct()
                pos_result = await db.execute(pos_stmt)
                position_netuids = [row[0] for row in pos_result.fetchall()]

            logger.info("Fetching validators for position netuids", netuids=position_netuids)

            total_count = 0
            async with get_db_context() as db:
                # Fetch validators for each netuid we have positions in
                for netuid in position_netuids:
                    try:
                        response = await taostats_client.get_validator_yield(
                            netuid=netuid,
                            limit=50  # Get top 50 validators per subnet
                        )
                        validators_data = response.get("data", [])

                        for val_data in validators_data:
                            await self._upsert_validator(db, val_data)
                            total_count += 1

                    except TaoStatsError as e:
                        logger.warning("Failed to fetch validators for netuid", netuid=netuid, error=str(e))
                        continue

                await db.commit()
                logger.info("Validators synced", count=total_count)
                return total_count

        except Exception as e:
            logger.error("Failed to sync validators", error=str(e))
            raise

    async def _upsert_validator(self, db: AsyncSession, val_data: Dict) -> Validator:
        """Insert or update validator record from yield endpoint data."""
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
        validator.stake_tao = rao_to_tao(val_data.get("stake", 0) or 0)

        # APY data from yield endpoint - these are actual percentages (0.35 = 35%)
        one_day_apy = val_data.get("one_day_apy", 0) or 0
        seven_day_apy = val_data.get("seven_day_apy", 0) or 0
        thirty_day_apy = val_data.get("thirty_day_apy", 0) or 0

        # Store as percentages (multiply by 100)
        validator.apy = Decimal(str(one_day_apy)) * Decimal("100")
        validator.apy_30d_avg = Decimal(str(thirty_day_apy)) * Decimal("100")

        # Also store 7-day APY if we have the field
        if hasattr(validator, 'apy_7d'):
            validator.apy_7d = Decimal(str(seven_day_apy)) * Decimal("100")

        # Epoch participation shows validator reliability
        validator.is_active = val_data.get("one_day_epoch_participation", 1.0) > 0.5
        validator.updated_at = now

        return validator

    async def sync_position_yields(self) -> int:
        """Sync yield data to positions from validator APY data.

        Maps validator APY to each position based on validator_hotkey,
        calculates unrealized P&L and estimated daily/weekly yields.
        """
        logger.info("Syncing position yields")

        async with get_db_context() as db:
            # Get all positions
            pos_stmt = select(Position).where(Position.wallet_address == self.wallet_address)
            pos_result = await db.execute(pos_stmt)
            positions = pos_result.scalars().all()

            # Build a lookup of validators by (hotkey, netuid)
            val_stmt = select(Validator)
            val_result = await db.execute(val_stmt)
            validators = val_result.scalars().all()

            validator_lookup = {}
            for v in validators:
                validator_lookup[(v.hotkey, v.netuid)] = v

            count = 0
            for position in positions:
                # Find matching validator
                validator = validator_lookup.get((position.validator_hotkey, position.netuid))

                if validator:
                    # Use validator's APY (prefer 30d average if available)
                    apy = validator.apy_30d_avg if validator.apy_30d_avg > 0 else validator.apy
                    position.current_apy = apy
                    position.apy_30d_avg = validator.apy_30d_avg

                    # Calculate estimated yields based on position TAO value
                    # Daily yield = position_value * (APY/100) / 365
                    if apy > 0 and position.tao_value_mid > 0:
                        daily_yield = position.tao_value_mid * (apy / Decimal("100")) / Decimal("365")
                        position.daily_yield_tao = daily_yield
                        position.weekly_yield_tao = daily_yield * Decimal("7")
                    else:
                        position.daily_yield_tao = Decimal("0")
                        position.weekly_yield_tao = Decimal("0")
                else:
                    # No validator data - zero out yields
                    position.current_apy = Decimal("0")
                    position.apy_30d_avg = Decimal("0")
                    position.daily_yield_tao = Decimal("0")
                    position.weekly_yield_tao = Decimal("0")

                # Calculate unrealized P&L
                if position.cost_basis_tao > 0:
                    position.unrealized_pnl_tao = position.tao_value_mid - position.cost_basis_tao
                    position.unrealized_pnl_pct = (
                        (position.unrealized_pnl_tao / position.cost_basis_tao) * Decimal("100")
                    )
                else:
                    position.unrealized_pnl_tao = Decimal("0")
                    position.unrealized_pnl_pct = Decimal("0")

                count += 1

            await db.commit()
            logger.info("Position yields synced", count=count)
            return count

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

            # Calculate yield aggregates from positions
            total_daily_yield = sum(p.daily_yield_tao for p in positions)
            total_weekly_yield = sum(p.weekly_yield_tao for p in positions)
            total_monthly_yield = total_daily_yield * Decimal("30")

            # Calculate weighted average APY across positions
            total_value = sum(p.tao_value_mid for p in positions)
            if total_value > 0:
                weighted_apy = sum(p.tao_value_mid * p.current_apy for p in positions) / total_value
            else:
                weighted_apy = Decimal("0")

            # P&L aggregates
            total_unrealized_pnl = sum(p.unrealized_pnl_tao for p in positions)
            total_realized_pnl = sum(p.realized_pnl_tao for p in positions)
            total_cost_basis = sum(p.cost_basis_tao for p in positions)

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
                # Yield aggregates
                portfolio_apy=weighted_apy,
                daily_yield_tao=total_daily_yield,
                weekly_yield_tao=total_weekly_yield,
                monthly_yield_tao=total_monthly_yield,
                # P&L aggregates
                total_unrealized_pnl_tao=total_unrealized_pnl,
                total_realized_pnl_tao=total_realized_pnl,
                total_cost_basis_tao=total_cost_basis,
            )
            db.add(snapshot)
            await db.commit()

            logger.info("Portfolio snapshot created", nav_mid=nav_mid, positions=len(positions))
            return snapshot

    async def sync_delegation_events(self) -> int:
        """Sync delegation events (staking/unstaking history) from TaoStats.

        Fetches all historical delegation events and stores them for
        accurate yield and income tracking.
        """
        logger.info("Syncing delegation events", wallet=self.wallet_address)

        try:
            events = await taostats_client.get_all_delegation_events(
                coldkey=self.wallet_address,
                max_pages=50,
            )

            async with get_db_context() as db:
                count = 0
                for event_data in events:
                    # Generate unique event ID
                    block = event_data.get("block_number", 0)
                    extrinsic_idx = event_data.get("extrinsic_index", 0)
                    event_id = f"{block}-{extrinsic_idx}"

                    # Check if already exists
                    stmt = select(DelegationEvent).where(DelegationEvent.event_id == event_id)
                    result = await db.execute(stmt)
                    if result.scalar_one_or_none():
                        continue

                    # Parse event type
                    action = event_data.get("action", "") or event_data.get("call_name", "")
                    if "add_stake" in action.lower() or "stake" in action.lower() and "unstake" not in action.lower():
                        event_type = "stake"
                    elif "remove_stake" in action.lower() or "unstake" in action.lower():
                        event_type = "unstake"
                    else:
                        event_type = "other"

                    # Parse timestamp
                    ts = event_data.get("timestamp")
                    if isinstance(ts, str):
                        timestamp = datetime.fromisoformat(ts.replace("Z", "+00:00"))
                    elif isinstance(ts, (int, float)):
                        timestamp = datetime.fromtimestamp(ts, tz=timezone.utc)
                    else:
                        timestamp = datetime.now(timezone.utc)

                    # Extract amounts
                    amount_rao = int(event_data.get("amount", 0) or event_data.get("tao_amount", 0) or 0)
                    amount_tao = rao_to_tao(amount_rao)
                    alpha_amount = rao_to_tao(event_data.get("alpha_amount", 0) or 0)

                    # Extract hotkey
                    hotkey_data = event_data.get("hotkey")
                    if isinstance(hotkey_data, dict):
                        hotkey = hotkey_data.get("ss58")
                    else:
                        hotkey = hotkey_data

                    delegation_event = DelegationEvent(
                        wallet_address=self.wallet_address,
                        event_id=event_id,
                        block_number=block,
                        timestamp=timestamp,
                        event_type=event_type,
                        action=action[:64] if action else "unknown",
                        netuid=int(event_data.get("netuid", 0) or 0),
                        hotkey=hotkey,
                        amount_rao=amount_rao,
                        amount_tao=amount_tao,
                        alpha_amount=alpha_amount if alpha_amount > 0 else None,
                        tao_price_usd=Decimal(str(event_data.get("tao_price_usd", 0) or 0)) or None,
                        usd_value=Decimal(str(event_data.get("usd_value", 0) or 0)) or None,
                        is_reward=False,
                        raw_data=event_data,
                    )
                    db.add(delegation_event)
                    count += 1

                await db.commit()
                logger.info("Delegation events synced", count=count)
                return count

        except Exception as e:
            logger.error("Failed to sync delegation events", error=str(e))
            return 0

    async def sync_stake_balance_history(self, days: int = 30) -> int:
        """Sync historical stake balance data for yield calculation.

        Uses daily stake balance snapshots to compute actual yield received.
        Note: The TaoStats stake_balance/history API requires a hotkey parameter,
        so we use the validator_hotkey from each position.
        """
        logger.info("Syncing stake balance history", wallet=self.wallet_address, days=days)

        try:
            # Calculate timestamp range
            now = datetime.now(timezone.utc)
            timestamp_start = int((now - timedelta(days=days)).timestamp())

            # Get all positions with their hotkeys
            async with get_db_context() as db:
                pos_stmt = select(Position).where(Position.wallet_address == self.wallet_address)
                pos_result = await db.execute(pos_stmt)
                positions = pos_result.scalars().all()

            total_records = 0
            for position in positions:
                netuid = position.netuid
                hotkey = position.validator_hotkey

                if not hotkey:
                    logger.debug("Skipping position without hotkey", netuid=netuid)
                    continue

                try:
                    # Use the dtao stake balance history with hotkey
                    response = await taostats_client.get_stake_balance_history(
                        coldkey=self.wallet_address,
                        hotkey=hotkey,
                        netuid=netuid,
                        timestamp_start=timestamp_start,
                        limit=days + 5,
                    )
                    history_data = response.get("data", [])

                    if len(history_data) < 2:
                        continue

                    # Process consecutive days to compute yield
                    async with get_db_context() as db:
                        # Sort by timestamp ascending
                        history_data.sort(key=lambda x: x.get("timestamp", 0))

                        for i in range(1, len(history_data)):
                            prev = history_data[i - 1]
                            curr = history_data[i]

                            # Parse date
                            curr_ts = curr.get("timestamp")
                            if isinstance(curr_ts, str):
                                date = datetime.fromisoformat(curr_ts.replace("Z", "+00:00"))
                            elif isinstance(curr_ts, (int, float)):
                                date = datetime.fromtimestamp(curr_ts, tz=timezone.utc)
                            else:
                                continue

                            # Check if already exists
                            check_stmt = select(PositionYieldHistory).where(
                                PositionYieldHistory.wallet_address == self.wallet_address,
                                PositionYieldHistory.netuid == netuid,
                                PositionYieldHistory.date == date,
                            )
                            check_result = await db.execute(check_stmt)
                            if check_result.scalar_one_or_none():
                                continue

                            # Extract balances
                            alpha_start = rao_to_tao(prev.get("balance", 0) or 0)
                            alpha_end = rao_to_tao(curr.get("balance", 0) or 0)
                            tao_start = rao_to_tao(prev.get("balance_as_tao", 0) or 0)
                            tao_end = rao_to_tao(curr.get("balance_as_tao", 0) or 0)

                            # Get staking activity for this day from delegation events
                            day_start = date.replace(hour=0, minute=0, second=0, microsecond=0)
                            day_end = day_start + timedelta(days=1)

                            stake_stmt = select(DelegationEvent).where(
                                DelegationEvent.wallet_address == self.wallet_address,
                                DelegationEvent.netuid == netuid,
                                DelegationEvent.timestamp >= day_start,
                                DelegationEvent.timestamp < day_end,
                            )
                            stake_result = await db.execute(stake_stmt)
                            day_events = stake_result.scalars().all()

                            # Calculate net staking (positive = added, negative = removed)
                            net_stake = Decimal("0")
                            for evt in day_events:
                                if evt.event_type == "stake":
                                    net_stake += evt.amount_tao
                                elif evt.event_type == "unstake":
                                    net_stake -= evt.amount_tao

                            # Yield = change in alpha balance - net staking
                            # If alpha increased without staking, it's yield
                            yield_alpha = alpha_end - alpha_start
                            # Adjust for staking activity (rough estimate)
                            # This is simplified - actual yield would need alpha price at stake time

                            # Compute yield in TAO terms (change in TAO value - net stake)
                            yield_tao = tao_end - tao_start - net_stake

                            # Compute daily APY (annualized)
                            # Clamp to reasonable range (max 9999% to avoid DB overflow)
                            if tao_start > Decimal("0.1") and yield_tao > 0:
                                daily_return = yield_tao / tao_start
                                daily_apy = min(daily_return * Decimal("365") * Decimal("100"), Decimal("9999"))
                            else:
                                daily_apy = Decimal("0")

                            yield_record = PositionYieldHistory(
                                wallet_address=self.wallet_address,
                                netuid=netuid,
                                date=date,
                                alpha_balance_start=alpha_start,
                                alpha_balance_end=alpha_end,
                                tao_value_start=tao_start,
                                tao_value_end=tao_end,
                                yield_alpha=yield_alpha,
                                yield_tao=max(yield_tao, Decimal("0")),  # Clamp negative
                                net_stake_tao=net_stake,
                                daily_apy=max(min(daily_apy, Decimal("9999")), Decimal("0")),  # Clamp to 0-9999%
                            )
                            db.add(yield_record)
                            total_records += 1

                        await db.commit()

                except Exception as e:
                    logger.warning("Failed to sync stake history for netuid", netuid=netuid, error=str(e))
                    continue

            logger.info("Stake balance history synced", records=total_records)
            return total_records

        except Exception as e:
            logger.error("Failed to sync stake balance history", error=str(e))
            return 0

    async def get_actual_yield_summary(self, days: int = 30) -> Dict[str, Any]:
        """Get actual yield summary from historical data.

        Returns actual realized yield based on balance history,
        not just estimated yield from APY.
        """
        async with get_db_context() as db:
            cutoff = datetime.now(timezone.utc) - timedelta(days=days)

            stmt = select(PositionYieldHistory).where(
                PositionYieldHistory.wallet_address == self.wallet_address,
                PositionYieldHistory.date >= cutoff,
            )
            result = await db.execute(stmt)
            history = result.scalars().all()

            if not history:
                return {
                    "total_yield_tao": Decimal("0"),
                    "avg_daily_yield_tao": Decimal("0"),
                    "avg_apy": Decimal("0"),
                    "days_tracked": 0,
                }

            total_yield = sum(h.yield_tao for h in history)
            days_tracked = len(set((h.netuid, h.date.date()) for h in history))

            # Average APY weighted by position value
            total_weighted_apy = sum(h.tao_value_start * h.daily_apy for h in history)
            total_value = sum(h.tao_value_start for h in history)
            avg_apy = total_weighted_apy / total_value if total_value > 0 else Decimal("0")

            return {
                "total_yield_tao": total_yield,
                "avg_daily_yield_tao": total_yield / Decimal(str(days)) if days > 0 else Decimal("0"),
                "avg_apy": avg_apy,
                "days_tracked": days_tracked,
            }

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
