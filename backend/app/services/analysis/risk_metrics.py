"""Risk-adjusted return metrics service – Phase 4.

Computes:
  1. Portfolio volatility (annualized from daily returns)
  2. Sharpe ratio  – (portfolio_return − risk_free) / volatility
  3. Sortino ratio  – (portfolio_return − risk_free) / downside_deviation
  4. Calmar ratio   – annualized_return / max_drawdown
  5. Max drawdown   – peak-to-trough from NAVHistory
  6. Benchmark comparison – portfolio vs Root-only and vs hold-TAO

Data sources:
  - NAVHistory  (daily_return_pct, nav_exec_close, nav_exec_ath)
  - Subnet(netuid=0).validator_apy  → risk-free rate
  - Subnet(netuid=0) historical SubnetSnapshot.validator_apy → benchmark
"""

import math
from datetime import datetime, timedelta, timezone
from decimal import Decimal
from typing import Any, Dict, List, Optional

import structlog
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import get_settings
from app.core.database import get_db_context
from app.models.portfolio import NAVHistory, PortfolioSnapshot
from app.models.subnet import Subnet
from app.services.analysis.utils import compute_volatility

logger = structlog.get_logger()

_ZERO = Decimal("0")


class RiskMetricsService:
    """Compute risk-adjusted return metrics from NAVHistory."""

    def __init__(self):
        self._settings = None

    @property
    def settings(self):
        if self._settings is None:
            self._settings = get_settings()
        return self._settings

    async def compute_risk_metrics(
        self,
        days: int = 90,
        wallet_address: Optional[str] = None,
    ) -> Dict[str, Any]:
        """Compute all risk-adjusted return metrics.

        Args:
            days: Look-back window for calculations (30, 60, 90).
            wallet_address: Override wallet address.

        Returns dict with:
            period_days, start, end,
            annualized_return_pct, annualized_volatility_pct,
            downside_deviation_pct,
            sharpe_ratio, sortino_ratio, calmar_ratio,
            max_drawdown_pct, max_drawdown_tao,
            risk_free_rate_pct, risk_free_source,
            win_rate_pct, best_day_pct, worst_day_pct,
            benchmarks: [{name, annualized_return_pct, sharpe_ratio, alpha_pct}],
            daily_returns: [{date, return_pct, nav_tao}]  (for sparkline/chart)
        """
        wallet = wallet_address or self.settings.wallet_address
        cutoff = datetime.now(timezone.utc) - timedelta(days=days)

        async with get_db_context() as db:
            # 1. Fetch NAVHistory
            nav_stmt = (
                select(NAVHistory)
                .where(
                    NAVHistory.wallet_address == wallet,
                    NAVHistory.date >= cutoff,
                )
                .order_by(NAVHistory.date.asc())
            )
            nav_result = await db.execute(nav_stmt)
            records = nav_result.scalars().all()

            if len(records) < 2:
                return self._empty_result(days)

            # 2. Get risk-free rate from Root (SN0) validator APY
            root_stmt = (
                select(Subnet)
                .where(Subnet.netuid == 0)
                .limit(1)
            )
            root_result = await db.execute(root_stmt)
            root_subnet = root_result.scalar_one_or_none()

            risk_free_annual = float(root_subnet.validator_apy) if root_subnet else 0.0
            risk_free_daily = risk_free_annual / 365.0

            # 3. Extract daily return series (percentage)
            daily_returns: List[float] = []
            daily_series: List[Dict[str, Any]] = []
            for r in records:
                ret_pct = float(r.daily_return_pct or 0)
                daily_returns.append(ret_pct)
                daily_series.append({
                    "date": r.date.isoformat() if hasattr(r.date, "isoformat") else str(r.date),
                    "return_pct": round(ret_pct, 4),
                    "nav_tao": round(float(r.nav_exec_close or 0), 4),
                })

            n = len(daily_returns)

            # 4. Core statistics
            mean_daily = sum(daily_returns) / n
            std_daily = compute_volatility(daily_returns)

            # Downside deviation: only consider returns below the risk-free daily rate
            downside_sq = [
                (r - risk_free_daily) ** 2
                for r in daily_returns
                if r < risk_free_daily
            ]
            downside_variance = sum(downside_sq) / max(len(downside_sq), 1) if downside_sq else 0.0
            downside_deviation_daily = math.sqrt(downside_variance)

            # 5. Annualize
            annualized_return = mean_daily * 365
            annualized_vol = std_daily * math.sqrt(365)
            annualized_downside = downside_deviation_daily * math.sqrt(365)

            # 6. Ratios
            excess_return = annualized_return - risk_free_annual

            sharpe = excess_return / annualized_vol if annualized_vol > 0 else 0.0
            sortino = excess_return / annualized_downside if annualized_downside > 0 else 0.0

            # 7. Max drawdown from NAV history
            peak_nav = 0.0
            max_dd = 0.0
            max_dd_tao = 0.0
            for r in records:
                nav = float(r.nav_exec_close or 0)
                if nav > peak_nav:
                    peak_nav = nav
                if peak_nav > 0:
                    dd = (peak_nav - nav) / peak_nav * 100
                    dd_tao = peak_nav - nav
                    if dd > max_dd:
                        max_dd = dd
                        max_dd_tao = dd_tao

            calmar = annualized_return / max_dd if max_dd > 0 else 0.0

            # 8. Win/loss stats
            positive_days = sum(1 for r in daily_returns if r > 0)
            win_rate = (positive_days / n * 100) if n > 0 else 0.0
            best_day = max(daily_returns) if daily_returns else 0.0
            worst_day = min(daily_returns) if daily_returns else 0.0

            # 9. Benchmarks
            benchmarks = await self._compute_benchmarks(
                db, records, risk_free_annual, risk_free_daily, annualized_return, n
            )

            # 10. Period dates
            start_date = records[0].date
            end_date = records[-1].date

        return {
            "period_days": n,
            "start": start_date.isoformat() if hasattr(start_date, "isoformat") else str(start_date),
            "end": end_date.isoformat() if hasattr(end_date, "isoformat") else str(end_date),
            "annualized_return_pct": round(annualized_return, 4),
            "annualized_volatility_pct": round(annualized_vol, 4),
            "downside_deviation_pct": round(annualized_downside, 4),
            "sharpe_ratio": round(sharpe, 4),
            "sortino_ratio": round(sortino, 4),
            "calmar_ratio": round(calmar, 4),
            "max_drawdown_pct": round(max_dd, 4),
            "max_drawdown_tao": round(max_dd_tao, 4),
            "risk_free_rate_pct": round(risk_free_annual, 4),
            "risk_free_source": "Root (SN0) Validator APY",
            "win_rate_pct": round(win_rate, 2),
            "best_day_pct": round(best_day, 4),
            "worst_day_pct": round(worst_day, 4),
            "benchmarks": benchmarks,
            "daily_returns": daily_series,
        }

    async def _compute_benchmarks(
        self,
        db: AsyncSession,
        records: list,
        risk_free_annual: float,
        risk_free_daily: float,
        portfolio_annualized: float,
        n: int,
    ) -> List[Dict[str, Any]]:
        """Compute benchmark comparisons.

        Benchmarks:
          1. Root-Only: What if all TAO was staked in Root (SN0)?
             Return = root_apy (compounding), vol ≈ 0 (deterministic yield)
          2. Hold TAO: No staking – return is 0% in TAO terms
             (TAO-denominated portfolio, holding TAO = 0% return)
        """
        benchmarks = []

        # Benchmark 1: Root-Only (risk-free yield)
        # Annualized return = Root APY, volatility ≈ 0
        root_return = risk_free_annual
        root_sharpe = 0.0  # No excess return over itself
        root_alpha = portfolio_annualized - root_return

        benchmarks.append({
            "id": "root_only",
            "name": "Root-Only Staking",
            "description": "100% staked in Root (SN0). Deterministic yield, zero alpha risk.",
            "annualized_return_pct": round(root_return, 4),
            "annualized_volatility_pct": 0.0,
            "sharpe_ratio": root_sharpe,
            "alpha_pct": round(root_alpha, 4),
        })

        # Benchmark 2: Hold TAO (no staking)
        # In TAO terms, holding TAO = 0% return
        hold_return = 0.0
        hold_alpha = portfolio_annualized - hold_return

        benchmarks.append({
            "id": "hold_tao",
            "name": "Hold TAO (Unstaked)",
            "description": "Hold TAO without staking. 0% return in TAO terms.",
            "annualized_return_pct": 0.0,
            "annualized_volatility_pct": 0.0,
            "sharpe_ratio": 0.0,
            "alpha_pct": round(hold_alpha, 4),
        })

        # Benchmark 3: High-Emission Concentrated
        # Simulate: top 3 subnets by emission_share, equally weighted
        # Use average APY of top-emission subnets as return proxy
        top_emission_stmt = (
            select(Subnet)
            .where(Subnet.is_eligible == True)
            .order_by(Subnet.emission_share.desc())
            .limit(3)
        )
        top_result = await db.execute(top_emission_stmt)
        top_subnets = top_result.scalars().all()

        if top_subnets:
            avg_apy = sum(float(s.validator_apy or 0) for s in top_subnets) / len(top_subnets)
            # Concentrated portfolio has higher volatility estimate
            # Approximate: single-asset vol ≈ 2× diversified portfolio vol
            emission_alpha = portfolio_annualized - avg_apy

            benchmarks.append({
                "id": "high_emission",
                "name": "High-Emission Top 3",
                "description": f"Equal-weight top 3 emission subnets: {', '.join(s.name or f'SN{s.netuid}' for s in top_subnets)}.",
                "annualized_return_pct": round(avg_apy, 4),
                "annualized_volatility_pct": None,  # Would need historical data
                "sharpe_ratio": None,
                "alpha_pct": round(emission_alpha, 4),
            })

        return benchmarks

    def _empty_result(self, days: int) -> Dict[str, Any]:
        now = datetime.now(timezone.utc)
        return {
            "period_days": 0,
            "start": (now - timedelta(days=days)).isoformat(),
            "end": now.isoformat(),
            "annualized_return_pct": 0.0,
            "annualized_volatility_pct": 0.0,
            "downside_deviation_pct": 0.0,
            "sharpe_ratio": 0.0,
            "sortino_ratio": 0.0,
            "calmar_ratio": 0.0,
            "max_drawdown_pct": 0.0,
            "max_drawdown_tao": 0.0,
            "risk_free_rate_pct": 0.0,
            "risk_free_source": "Root (SN0) Validator APY",
            "win_rate_pct": 0.0,
            "best_day_pct": 0.0,
            "worst_day_pct": 0.0,
            "benchmarks": [],
            "daily_returns": [],
        }


# Lazy singleton
_risk_metrics_service: Optional[RiskMetricsService] = None


def get_risk_metrics_service() -> RiskMetricsService:
    global _risk_metrics_service
    if _risk_metrics_service is None:
        _risk_metrics_service = RiskMetricsService()
    return _risk_metrics_service
