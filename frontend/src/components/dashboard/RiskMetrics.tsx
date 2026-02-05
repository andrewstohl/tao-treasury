import { useState } from 'react'
import { useQuery } from '@tanstack/react-query'
import {
  Activity,
  Target,
  TrendingDown,
  TrendingUp,
  Award,
  Info,
} from 'lucide-react'
import { api } from '../../services/api'
import type { RiskMetrics as RiskMetricsType, BenchmarkComparison } from '../../types'
import { formatPercent, formatTao, safeFloat } from '../../utils/format'

const PERIOD_OPTIONS = [
  { days: 30, label: '30d' },
  { days: 60, label: '60d' },
  { days: 90, label: '90d' },
]

export default function RiskMetricsPanel() {
  const [days, setDays] = useState(90)

  const { data: metrics, isLoading } = useQuery<RiskMetricsType>({
    queryKey: ['risk-metrics', days],
    queryFn: () => api.getRiskMetrics(days),
    refetchInterval: 120000,
  })

  if (isLoading) {
    return (
      <div className="bg-gray-800 rounded-lg border border-gray-700 p-6 animate-pulse h-64" />
    )
  }

  if (!metrics || metrics.period_days === 0) {
    return (
      <div className="bg-gray-800 rounded-lg border border-gray-700 p-6">
        <div className="text-sm text-gray-500 text-center py-8">
          Insufficient data for risk metrics. More daily NAV history is needed.
        </div>
      </div>
    )
  }

  return (
    <div className="space-y-4">
      {/* Section header with period selector */}
      <div className="flex items-center justify-between">
        <h3 className="text-lg font-semibold flex items-center gap-2">
          <Activity className="w-5 h-5" />
          Risk-Adjusted Returns
        </h3>
        <div className="flex gap-1">
          {PERIOD_OPTIONS.map((opt) => (
            <button
              key={opt.days}
              onClick={() => setDays(opt.days)}
              className={`px-3 py-1 rounded text-xs font-medium transition-colors ${
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

      {/* Ratio Scorecard */}
      <div className="grid grid-cols-2 md:grid-cols-4 gap-4">
        <RatioCard
          label="Sharpe Ratio"
          value={safeFloat(metrics.sharpe_ratio)}
          format="ratio"
          icon={<Target className="w-4 h-4" />}
          tooltip="Excess return per unit of total risk. >1.0 is good, >2.0 is excellent."
          thresholds={[0, 0.5, 1.0, 2.0]}
        />
        <RatioCard
          label="Sortino Ratio"
          value={safeFloat(metrics.sortino_ratio)}
          format="ratio"
          icon={<TrendingUp className="w-4 h-4" />}
          tooltip="Excess return per unit of downside risk. Higher = better downside protection."
          thresholds={[0, 0.5, 1.0, 2.0]}
        />
        <RatioCard
          label="Calmar Ratio"
          value={safeFloat(metrics.calmar_ratio)}
          format="ratio"
          icon={<TrendingDown className="w-4 h-4" />}
          tooltip="Annualized return / max drawdown. >1.0 means return exceeds worst drawdown."
          thresholds={[0, 0.3, 0.5, 1.0]}
        />
        <RatioCard
          label="Win Rate"
          value={safeFloat(metrics.win_rate_pct)}
          format="percent"
          icon={<Award className="w-4 h-4" />}
          tooltip="Percentage of days with positive returns."
          thresholds={[30, 40, 50, 60]}
        />
      </div>

      <div className="grid grid-cols-1 lg:grid-cols-3 gap-4">
        {/* Volatility & Return Stats */}
        <div className="lg:col-span-2 bg-gray-800 rounded-lg border border-gray-700 p-6">
          <div className="text-sm text-gray-400 mb-4">Return & Risk Profile</div>
          <ReturnRiskProfile metrics={metrics} />
        </div>

        {/* Daily Return Distribution Mini Chart */}
        <div className="bg-gray-800 rounded-lg border border-gray-700 p-6">
          <div className="text-sm text-gray-400 mb-4">Return Distribution</div>
          <ReturnDistribution dailyReturns={metrics.daily_returns} />
        </div>
      </div>

      {/* Benchmark Comparison */}
      {metrics.benchmarks.length > 0 && (
        <div className="bg-gray-800 rounded-lg border border-gray-700 overflow-hidden">
          <div className="px-6 py-4 border-b border-gray-700 flex items-center justify-between">
            <div className="text-sm text-gray-400">Benchmark Comparison</div>
            <div className="text-xs text-gray-500">
              Risk-free: {safeFloat(metrics.risk_free_rate_pct).toFixed(2)}% ({metrics.risk_free_source})
            </div>
          </div>
          <BenchmarkTable
            benchmarks={metrics.benchmarks}
            portfolioReturn={safeFloat(metrics.annualized_return_pct)}
            portfolioSharpe={safeFloat(metrics.sharpe_ratio)}
            portfolioVol={safeFloat(metrics.annualized_volatility_pct)}
          />
        </div>
      )}
    </div>
  )
}

// ---------------------------------------------------------------------------
// Sub-components
// ---------------------------------------------------------------------------

function RatioCard({
  label,
  value,
  format,
  icon,
  tooltip,
  thresholds,
}: {
  label: string
  value: number
  format: 'ratio' | 'percent'
  icon: React.ReactNode
  tooltip: string
  thresholds: number[] // [bad, poor, ok, good]
}) {
  // Color based on thresholds
  let color = 'text-red-400'
  if (value >= thresholds[3]) color = 'text-green-400'
  else if (value >= thresholds[2]) color = 'text-emerald-400'
  else if (value >= thresholds[1]) color = 'text-yellow-400'

  const displayValue = format === 'percent'
    ? `${value.toFixed(1)}%`
    : value.toFixed(2)

  return (
    <div className="bg-gray-800 rounded-lg border border-gray-700 p-4 group relative">
      <div className="flex items-center gap-1.5 text-xs text-gray-500 mb-2">
        {icon}
        {label}
        <Info className="w-3 h-3 ml-auto opacity-0 group-hover:opacity-100 transition-opacity" />
      </div>
      <div className={`text-2xl font-bold tabular-nums ${color}`}>
        {displayValue}
      </div>
      {/* Tooltip on hover */}
      <div className="absolute bottom-full left-1/2 -translate-x-1/2 mb-2 px-3 py-2 bg-gray-900 border border-gray-600 rounded-lg text-xs text-gray-300 opacity-0 group-hover:opacity-100 transition-opacity pointer-events-none w-56 z-10 text-center">
        {tooltip}
      </div>
    </div>
  )
}

function ReturnRiskProfile({ metrics }: { metrics: RiskMetricsType }) {
  const annReturn = safeFloat(metrics.annualized_return_pct)
  const annVol = safeFloat(metrics.annualized_volatility_pct)
  const downsideDev = safeFloat(metrics.downside_deviation_pct)
  const maxDD = safeFloat(metrics.max_drawdown_pct)
  const riskFree = safeFloat(metrics.risk_free_rate_pct)
  const bestDay = safeFloat(metrics.best_day_pct)
  const worstDay = safeFloat(metrics.worst_day_pct)

  return (
    <div className="grid grid-cols-2 gap-x-8 gap-y-3">
      <StatRow
        label="Annualized Return"
        value={formatPercent(annReturn)}
        color={annReturn >= 0 ? 'text-green-400' : 'text-red-400'}
      />
      <StatRow
        label="Risk-Free Rate"
        value={`${riskFree.toFixed(2)}%`}
        color="text-blue-400"
      />
      <StatRow
        label="Annualized Volatility"
        value={`${annVol.toFixed(2)}%`}
        color={annVol < 20 ? 'text-green-400' : annVol < 40 ? 'text-yellow-400' : 'text-red-400'}
      />
      <StatRow
        label="Downside Deviation"
        value={`${downsideDev.toFixed(2)}%`}
        color={downsideDev < 15 ? 'text-green-400' : downsideDev < 30 ? 'text-yellow-400' : 'text-red-400'}
      />
      <StatRow
        label="Max Drawdown"
        value={`-${maxDD.toFixed(2)}%`}
        color={maxDD < 5 ? 'text-green-400' : maxDD < 15 ? 'text-yellow-400' : 'text-red-400'}
      />
      <StatRow
        label="Drawdown (TAO)"
        value={`${formatTao(metrics.max_drawdown_tao)} τ`}
        color="text-gray-300"
      />
      <StatRow
        label="Best Day"
        value={formatPercent(bestDay)}
        color="text-green-400"
      />
      <StatRow
        label="Worst Day"
        value={formatPercent(worstDay)}
        color="text-red-400"
      />
    </div>
  )
}

function StatRow({
  label,
  value,
  color,
}: {
  label: string
  value: string
  color: string
}) {
  return (
    <div className="flex justify-between items-center">
      <span className="text-sm text-gray-400">{label}</span>
      <span className={`tabular-nums text-sm font-medium ${color}`}>{value}</span>
    </div>
  )
}

function ReturnDistribution({
  dailyReturns,
}: {
  dailyReturns: { date: string; return_pct: string; nav_tao: string }[]
}) {
  if (dailyReturns.length === 0) {
    return <div className="text-xs text-gray-600 text-center py-8">No data</div>
  }

  // Build histogram bins
  const returns = dailyReturns.map((d) => safeFloat(d.return_pct))
  const min = Math.min(...returns)
  const max = Math.max(...returns)
  const range = max - min || 1
  const binCount = 12
  const binWidth = range / binCount

  const bins: number[] = new Array(binCount).fill(0)
  for (const r of returns) {
    const idx = Math.min(Math.floor((r - min) / binWidth), binCount - 1)
    bins[idx]++
  }
  const maxBin = Math.max(...bins, 1)

  // Find which bin contains 0
  const zeroBin = Math.min(Math.floor((0 - min) / binWidth), binCount - 1)

  return (
    <div className="space-y-2">
      {/* Histogram bars */}
      <div className="flex items-end gap-0.5 h-24">
        {bins.map((count, idx) => {
          const height = (count / maxBin) * 100
          const isNegative = idx < zeroBin
          const isZero = idx === zeroBin
          const barColor = isNegative
            ? 'bg-red-500/60'
            : isZero
              ? 'bg-gray-500/60'
              : 'bg-green-500/60'

          return (
            <div
              key={idx}
              className="flex-1 flex flex-col justify-end"
              title={`${(min + idx * binWidth).toFixed(2)}% to ${(min + (idx + 1) * binWidth).toFixed(2)}%: ${count} days`}
            >
              <div
                className={`${barColor} rounded-t-sm transition-all`}
                style={{ height: `${Math.max(height, 2)}%` }}
              />
            </div>
          )
        })}
      </div>

      {/* X-axis labels */}
      <div className="flex justify-between text-xs text-gray-600 tabular-nums">
        <span>{min.toFixed(1)}%</span>
        <span>0%</span>
        <span>{max.toFixed(1)}%</span>
      </div>

      {/* Summary stats */}
      <div className="grid grid-cols-2 gap-2 text-xs pt-2 border-t border-gray-700">
        <div className="flex justify-between">
          <span className="text-gray-500">Days</span>
          <span className="text-gray-300 tabular-nums">{returns.length}</span>
        </div>
        <div className="flex justify-between">
          <span className="text-gray-500">Median</span>
          <span className="text-gray-300 tabular-nums">
            {[...returns].sort((a, b) => a - b)[Math.floor(returns.length / 2)]?.toFixed(2)}%
          </span>
        </div>
      </div>
    </div>
  )
}

function BenchmarkTable({
  benchmarks,
  portfolioReturn,
  portfolioSharpe,
  portfolioVol,
}: {
  benchmarks: BenchmarkComparison[]
  portfolioReturn: number
  portfolioSharpe: number
  portfolioVol: number
}) {
  return (
    <div className="overflow-x-auto">
      <table className="w-full">
        <thead className="bg-gray-900/50">
          <tr className="text-xs text-gray-500 uppercase tracking-wider">
            <th className="px-4 py-2 text-left">Strategy</th>
            <th className="px-4 py-2 text-right">Ann. Return</th>
            <th className="px-4 py-2 text-right">Volatility</th>
            <th className="px-4 py-2 text-right">Sharpe</th>
            <th className="px-4 py-2 text-right">Alpha vs Portfolio</th>
          </tr>
        </thead>
        <tbody className="divide-y divide-gray-700">
          {/* Portfolio row (highlighted) */}
          <tr className="bg-tao-600/10 font-semibold">
            <td className="px-4 py-2.5">
              <div className="text-sm text-tao-400">Your Portfolio</div>
            </td>
            <td className="px-4 py-2.5 text-right">
              <span className={`tabular-nums text-sm ${portfolioReturn >= 0 ? 'text-green-400' : 'text-red-400'}`}>
                {formatPercent(portfolioReturn)}
              </span>
            </td>
            <td className="px-4 py-2.5 text-right tabular-nums text-sm text-gray-300">
              {portfolioVol.toFixed(2)}%
            </td>
            <td className="px-4 py-2.5 text-right tabular-nums text-sm text-gray-300">
              {portfolioSharpe.toFixed(2)}
            </td>
            <td className="px-4 py-2.5 text-right tabular-nums text-sm text-gray-500">
              --
            </td>
          </tr>

          {/* Benchmark rows */}
          {benchmarks.map((b) => {
            const ret = safeFloat(b.annualized_return_pct)
            const alpha = safeFloat(b.alpha_pct)
            const vol = b.annualized_volatility_pct != null ? safeFloat(b.annualized_volatility_pct) : null
            const sharpe = b.sharpe_ratio != null ? safeFloat(b.sharpe_ratio) : null

            return (
              <tr key={b.id} className="hover:bg-gray-700/20 group">
                <td className="px-4 py-2.5">
                  <div className="text-sm text-gray-300">{b.name}</div>
                  <div className="text-xs text-gray-600 hidden group-hover:block max-w-xs">
                    {b.description}
                  </div>
                </td>
                <td className="px-4 py-2.5 text-right">
                  <span className={`tabular-nums text-sm ${ret >= 0 ? 'text-green-400' : 'text-red-400'}`}>
                    {formatPercent(ret)}
                  </span>
                </td>
                <td className="px-4 py-2.5 text-right tabular-nums text-sm text-gray-400">
                  {vol != null ? `${vol.toFixed(2)}%` : '--'}
                </td>
                <td className="px-4 py-2.5 text-right tabular-nums text-sm text-gray-400">
                  {sharpe != null ? sharpe.toFixed(2) : '--'}
                </td>
                <td className="px-4 py-2.5 text-right">
                  <span className={`tabular-nums text-sm font-medium ${alpha >= 0 ? 'text-green-400' : 'text-red-400'}`}>
                    {alpha >= 0 ? '+' : ''}{alpha.toFixed(2)}%
                  </span>
                </td>
              </tr>
            )
          })}
        </tbody>
      </table>
    </div>
  )
}
