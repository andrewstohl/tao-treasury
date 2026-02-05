import { useState } from 'react'
import { useQuery } from '@tanstack/react-query'
import { api } from '../../services/api'
import type { Attribution, PortfolioOverview, RiskMetrics as RiskMetricsType } from '../../types'
import { formatTaoShort, formatPercent, formatUsd, safeFloat } from '../../utils/format'

const PERIOD_OPTIONS = [
  { days: 1, label: '24h' },
  { days: 7, label: '7d' },
  { days: 30, label: '30d' },
]

export default function PerformanceRisk() {
  const [days, setDays] = useState(7)

  const { data: attr, isLoading: attrLoading } = useQuery<Attribution>({
    queryKey: ['attribution', days],
    queryFn: () => api.getAttribution(days),
    refetchInterval: 60000,
  })

  const { data: overview } = useQuery<PortfolioOverview>({
    queryKey: ['portfolio-overview'],
    queryFn: api.getPortfolioOverview,
    refetchInterval: 30000,
  })

  const { data: risk } = useQuery<RiskMetricsType>({
    queryKey: ['risk-metrics', 90],
    queryFn: () => api.getRiskMetrics(90),
    refetchInterval: 120000,
  })

  if (attrLoading) {
    return (
      <div className="bg-gray-800 rounded-lg p-6 border border-gray-700 animate-pulse h-64" />
    )
  }

  if (!attr) {
    return (
      <div className="bg-gray-800 rounded-lg p-6 border border-gray-700">
        <div className="text-sm text-gray-500 text-center py-8">
          Performance data unavailable.
        </div>
      </div>
    )
  }

  // Attribution factors (TAO-denominated)
  const yieldTao = safeFloat(attr.yield_income_tao)
  const alphaTao = safeFloat(attr.price_effect_tao)
  const netTao = yieldTao + alphaTao

  // FX: TAO/USD price change for the period
  let fxChangePct: number | null = null
  let taoCurrentPrice: number | null = null
  let taoPriceStart: number | null = null

  if (overview?.tao_price) {
    taoCurrentPrice = safeFloat(overview.tao_price.price_usd)
    if (days === 1 && overview.tao_price.change_24h_pct) {
      fxChangePct = safeFloat(overview.tao_price.change_24h_pct)
    } else if (days === 7 && overview.tao_price.change_7d_pct) {
      fxChangePct = safeFloat(overview.tao_price.change_7d_pct)
    }
    if (fxChangePct !== null && taoCurrentPrice) {
      taoPriceStart = taoCurrentPrice / (1 + fxChangePct / 100)
    }
  }

  // Risk: Drawdown from ATH
  const drawdownPct = overview ? safeFloat(overview.drawdown_from_ath_pct) : null
  const navAthTao = overview ? safeFloat(overview.nav_ath_tao) : null
  const currentNavTao = overview ? safeFloat(overview.nav_mid.tao) : null
  const drawdownTao =
    navAthTao != null && currentNavTao != null ? currentNavTao - navAthTao : null

  // Risk: VaR from daily returns (parametric 95th percentile)
  let var95Tao: number | null = null
  let worstDayPct: number | null = null

  if (risk && risk.daily_returns && risk.daily_returns.length >= 5) {
    const returns = risk.daily_returns
      .map((d) => safeFloat(d.return_pct))
      .sort((a, b) => a - b)
    const idx5 = Math.max(Math.floor(returns.length * 0.05), 0)
    const var95Pct = returns[idx5] ?? returns[0]
    if (currentNavTao && var95Pct < 0) {
      var95Tao = (var95Pct / 100) * currentNavTao
    }
    worstDayPct = safeFloat(risk.worst_day_pct)
  }

  // Bar scaling: max absolute value among yield/alpha
  const maxBar = Math.max(Math.abs(yieldTao), Math.abs(alphaTao), 0.001)

  return (
    <div className="bg-gray-800 rounded-lg p-6 border border-gray-700">
      {/* Header with period selector */}
      <div className="flex items-center justify-between mb-4">
        <h3 className="text-lg font-semibold">Performance & Risk</h3>
        <div className="flex gap-1">
          {PERIOD_OPTIONS.map((opt) => (
            <button
              key={opt.days}
              onClick={() => setDays(opt.days)}
              className={`px-2.5 py-1 rounded text-xs font-medium transition-colors ${
                days === opt.days
                  ? 'bg-gray-600 text-white'
                  : 'text-gray-500 hover:text-gray-300'
              }`}
            >
              {opt.label}
            </button>
          ))}
        </div>
      </div>

      {/* Period Return headline */}
      <div className="flex items-center justify-between mb-3">
        <span className="text-sm text-gray-400">Period Return</span>
        <span
          className={`text-lg font-bold tabular-nums ${
            netTao >= 0 ? 'text-green-400' : 'text-red-400'
          }`}
        >
          {netTao >= 0 ? '+' : ''}
          {formatTaoShort(netTao)} τ
        </span>
      </div>

      {/* Attribution bars: Yield & Alpha */}
      <div className="space-y-2 mb-4">
        <AttributionRow label="Yield" value={yieldTao} maxVal={maxBar} />
        <AttributionRow label="Alpha" value={alphaTao} maxVal={maxBar} />
      </div>

      {/* FX (TAO/USD) */}
      <div className="border-t border-gray-700 pt-3 mb-3">
        <div className="flex items-center justify-between">
          <span className="text-sm text-gray-400">FX (TAO/USD)</span>
          {fxChangePct !== null ? (
            <div className="text-right">
              <span
                className={`tabular-nums text-sm font-medium ${
                  fxChangePct >= 0 ? 'text-green-400' : 'text-red-400'
                }`}
              >
                {fxChangePct >= 0 ? '+' : ''}
                {fxChangePct.toFixed(1)}%
              </span>
              {taoPriceStart !== null && taoCurrentPrice !== null && (
                <div className="text-xs text-gray-500 tabular-nums">
                  {formatUsd(taoPriceStart)} → {formatUsd(taoCurrentPrice)}
                </div>
              )}
            </div>
          ) : (
            <span className="text-sm text-gray-600 tabular-nums">--</span>
          )}
        </div>
      </div>

      {/* Risk section */}
      <div className="border-t border-gray-700 pt-3">
        <div className="text-xs text-gray-500 uppercase tracking-wider mb-2">
          Risk
        </div>
        <div className="space-y-2">
          {/* Drawdown from ATH */}
          {drawdownPct !== null && (
            <div className="flex justify-between items-center">
              <span className="text-sm text-gray-400">ATH Drawdown</span>
              <div className="text-right flex items-baseline gap-1.5">
                <span
                  className={`tabular-nums text-sm ${
                    Math.abs(drawdownPct) < 5
                      ? 'text-green-400'
                      : Math.abs(drawdownPct) < 15
                        ? 'text-yellow-400'
                        : 'text-red-400'
                  }`}
                >
                  {drawdownPct === 0
                    ? 'ATH'
                    : `-${Math.abs(drawdownPct).toFixed(1)}%`}
                </span>
                {drawdownTao !== null && drawdownPct !== 0 && (
                  <span className="text-xs text-gray-500 tabular-nums">
                    {formatTaoShort(drawdownTao)} τ
                  </span>
                )}
              </div>
            </div>
          )}

          {/* Daily VaR */}
          <div className="flex justify-between items-center">
            <span className="text-sm text-gray-400">Daily VaR (95%)</span>
            {var95Tao !== null ? (
              <span className="tabular-nums text-sm text-red-400">
                {formatTaoShort(var95Tao)} τ
              </span>
            ) : (
              <span className="text-xs text-gray-600">Insufficient history</span>
            )}
          </div>

          {/* Worst Day */}
          <div className="flex justify-between items-center">
            <span className="text-sm text-gray-400">Worst Day</span>
            {worstDayPct !== null ? (
              <span className="tabular-nums text-sm text-red-400">
                {formatPercent(worstDayPct)}
              </span>
            ) : (
              <span className="text-xs text-gray-600">--</span>
            )}
          </div>
        </div>
      </div>
    </div>
  )
}

function AttributionRow({
  label,
  value,
  maxVal,
}: {
  label: string
  value: number
  maxVal: number
}) {
  const isPositive = value >= 0
  const barWidth = Math.min((Math.abs(value) / maxVal) * 100, 100)

  return (
    <div className="flex items-center gap-3">
      <div className="w-12 text-sm text-gray-400 text-right flex-shrink-0">
        {label}
      </div>
      <div className="flex-1 relative h-6">
        <div
          className={`absolute inset-y-0 left-0 rounded ${
            isPositive ? 'bg-green-600/40' : 'bg-red-600/40'
          }`}
          style={{ width: `${barWidth}%` }}
        />
        <span
          className={`absolute inset-y-0 flex items-center px-2 text-xs tabular-nums z-10 ${
            isPositive ? 'text-green-400' : 'text-red-400'
          }`}
        >
          {isPositive ? '+' : ''}
          {formatTaoShort(value)} τ
        </span>
      </div>
    </div>
  )
}
