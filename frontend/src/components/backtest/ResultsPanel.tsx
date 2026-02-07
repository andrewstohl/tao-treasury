import { useState } from 'react'
import { Info, ChevronDown, ChevronRight, TrendingUp, TrendingDown } from 'lucide-react'
import EquityCurveChart from './EquityCurveChart'
import MetricsSummary from './MetricsSummary'

interface Holding {
  netuid: number
  name: string
  weight: number
  return_pct: number
  tier?: string
  score?: number
}

interface Period {
  date: string
  portfolio_value: number
  period_return: number
  cumulative_return: number
  holdings: Holding[]
  in_root: boolean
  num_holdings: number
}

interface BacktestResults {
  strategy: 'equal_weight' | 'fai_weighted'
  start_date: string
  end_date: string
  initial_capital: number
  final_value: number
  total_return: number
  sharpe_ratio: number
  max_drawdown: number
  win_rate: number
  avg_holdings: number
  num_periods: number
  equity_curve: { date: string; value: number; in_root: boolean; num_holdings: number }[]
  periods: Period[]
  comparison?: {
    strategy: 'equal_weight'
    total_return: number
    sharpe_ratio: number
    equity_curve: { date: string; value: number }[]
  }
}

interface ResultsPanelProps {
  results: BacktestResults | null
  isLoading: boolean
}

export default function ResultsPanel({ results, isLoading }: ResultsPanelProps) {
  const [expandedPeriod, setExpandedPeriod] = useState<string | null>(null)
  const [showComparison, setShowComparison] = useState(true)

  if (isLoading) {
    return (
      <div className="bg-[#121f2d] rounded-lg border border-[#1e3a5f] p-5">
        <div className="animate-pulse space-y-4">
          <div className="h-6 bg-[#1a2d42] rounded w-1/3" />
          <div className="grid grid-cols-5 gap-3">
            {[...Array(5)].map((_, i) => (
              <div key={i} className="h-20 bg-[#1a2d42] rounded" />
            ))}
          </div>
          <div className="h-48 bg-[#1a2d42] rounded" />
        </div>
      </div>
    )
  }

  if (!results) {
    return (
      <div className="bg-[#121f2d] rounded-lg border border-[#1e3a5f] p-8 text-center">
        <div className="text-[#5a7a94] mb-2">No backtest results yet</div>
        <p className="text-xs text-[#3a5a74]">Configure parameters and run a backtest to see results</p>
      </div>
    )
  }

  const fmtPct = (v: number) => `${v >= 0 ? '+' : ''}${(v * 100).toFixed(2)}%`
  const hasBetterReturn = results.comparison ? results.total_return > results.comparison.total_return : false
  const hasBetterSharpe = results.comparison ? results.sharpe_ratio > results.comparison.sharpe_ratio : false

  return (
    <div className="bg-[#121f2d] rounded-lg border border-[#1e3a5f] p-5 space-y-5">
      {/* Header */}
      <div className="flex items-center justify-between">
        <div>
          <h2 className="text-lg font-semibold text-white">Backtest Results</h2>
          <p className="text-xs text-[#5a7a94] mt-0.5">
            {results.start_date} to {results.end_date} &middot; {results.num_periods} periods &middot;{' '}
            <span className="capitalize">{results.strategy.replace('_', ' ')}</span>
          </p>
        </div>
        {results.comparison && (
          <label className="flex items-center gap-2 cursor-pointer">
            <input
              type="checkbox"
              checked={showComparison}
              onChange={(e) => setShowComparison(e.target.checked)}
              className="w-4 h-4 rounded border-[#2a4a66] bg-[#1a2d42] text-tao-500"
            />
            <span className="text-xs text-[#6f87a0]">Show Equal Weight comparison</span>
          </label>
        )}
      </div>

      {/* Summary Metrics */}
      <MetricsSummary
        totalReturn={results.total_return}
        sharpeRatio={results.sharpe_ratio}
        maxDrawdown={results.max_drawdown}
        winRate={results.win_rate}
        avgHoldings={results.avg_holdings}
        numPeriods={results.num_periods}
        initialCapital={results.initial_capital}
        finalValue={results.final_value}
        comparisonReturn={showComparison ? results.comparison?.total_return : null}
        comparisonSharpe={showComparison ? results.comparison?.sharpe_ratio : null}
      />

      {/* Strategy Comparison Summary */}
      {results.comparison && showComparison && (
        <div className="bg-[#050d15]/40 rounded-lg p-4 border border-[#1e3a5f]/50">
          <h3 className="text-sm font-medium text-[#a8c4d9] mb-3">Strategy Comparison</h3>
          <div className="grid grid-cols-2 gap-4">
            <div className="flex items-center justify-between">
              <span className="text-xs text-[#6f87a0]">Return Difference</span>
              <div className="flex items-center gap-1">
                <span className={`text-sm tabular-nums font-medium ${hasBetterReturn ? 'text-green-400' : 'text-red-400'}`}>
                  {fmtPct(results.total_return - results.comparison.total_return)}
                </span>
                {hasBetterReturn ? (
                  <TrendingUp className="w-3 h-3 text-green-400" />
                ) : (
                  <TrendingDown className="w-3 h-3 text-red-400" />
                )}
              </div>
            </div>
            <div className="flex items-center justify-between">
              <span className="text-xs text-[#6f87a0]">Sharpe Difference</span>
              <div className="flex items-center gap-1">
                <span className={`text-sm tabular-nums font-medium ${hasBetterSharpe ? 'text-green-400' : 'text-red-400'}`}>
                  {(results.sharpe_ratio - results.comparison.sharpe_ratio).toFixed(2)}
                </span>
                {hasBetterSharpe ? (
                  <TrendingUp className="w-3 h-3 text-green-400" />
                ) : (
                  <TrendingDown className="w-3 h-3 text-red-400" />
                )}
              </div>
            </div>
          </div>
          <div className="mt-3 text-xs text-[#5a7a94]">
            {hasBetterSharpe ? (
              <span className="text-green-400">Your strategy outperforms on risk-adjusted basis</span>
            ) : (
              <span className="text-yellow-400">Equal weight has better risk-adjusted returns</span>
            )}
          </div>
        </div>
      )}

      {/* Equity Curve */}
      <div>
        <h3 className="text-xs font-semibold text-[#6f87a0] uppercase tracking-wider mb-2">
          Equity Curve
        </h3>
        <EquityCurveChart
          data={results.equity_curve}
          initial={results.initial_capital}
          comparison={showComparison ? results.comparison?.equity_curve : null}
        />
      </div>

      {/* Period Details */}
      <div>
        <div className="flex items-center justify-between mb-2">
          <h3 className="text-xs font-semibold text-[#6f87a0] uppercase tracking-wider">
            Period Details
          </h3>
          <button
            onClick={() => setExpandedPeriod(expandedPeriod ? null : results.periods[0]?.date)}
            className="text-xs text-[#5a7a94] hover:text-[#a8c4d9]"
          >
            {expandedPeriod ? 'Collapse All' : 'Expand First'}
          </button>
        </div>
        <div className="max-h-[400px] overflow-y-auto space-y-0.5">
          {results.periods.map((period) => (
            <div key={period.date}>
              <button
                onClick={() => setExpandedPeriod(expandedPeriod === period.date ? null : period.date)}
                className="w-full flex items-center gap-2 text-xs py-2 px-3 rounded hover:bg-[#1a2d42]/50 text-left"
              >
                <span className="text-[#5a7a94]">
                  {expandedPeriod === period.date ? (
                    <ChevronDown className="w-3 h-3" />
                  ) : (
                    <ChevronRight className="w-3 h-3" />
                  )}
                </span>
                <span className="tabular-nums text-[#6f87a0] w-24">{period.date}</span>
                <span className={`tabular-nums w-16 text-right ${period.period_return >= 0 ? 'text-green-400' : 'text-red-400'}`}>
                  {period.in_root ? '--' : fmtPct(period.period_return)}
                </span>
                <span className={`tabular-nums w-16 text-right ${period.cumulative_return >= 0 ? 'text-green-400' : 'text-red-400'}`}>
                  {fmtPct(period.cumulative_return)}
                </span>
                <span className="tabular-nums text-[#6f87a0] w-20 text-right">{period.portfolio_value.toFixed(1)} TAO</span>
                <span className="text-[#3a5a74] flex-1 text-right">
                  {period.in_root ? 'Root (no picks)' : `${period.holdings.length} holdings`}
                </span>
              </button>

              {expandedPeriod === period.date && period.holdings.length > 0 && (
                <div className="ml-8 mb-2 bg-[#050d15]/40 rounded p-3 text-xs space-y-1.5">
                  <div className="flex items-center gap-3 text-[#5a7a94] border-b border-[#1e3a5f] pb-1.5 mb-1.5">
                    <span className="w-12">Subnet</span>
                    <span className="flex-1">Name</span>
                    <span className="w-10 text-center">Tier</span>
                    <span className="w-12 text-right">Score</span>
                    <span className="w-14 text-right">Weight</span>
                    <span className="w-16 text-right">Return</span>
                  </div>
                  {period.holdings.map((h) => (
                    <div key={h.netuid} className="flex items-center gap-3">
                      <span className="text-[#6f87a0] w-12">SN{h.netuid}</span>
                      <span className="text-[#8faabe] flex-1 truncate">{h.name}</span>
                      {h.tier && (
                        <span className={`text-[10px] px-1.5 py-0.5 rounded w-10 text-center ${
                          h.tier === 'tier_1' ? 'bg-emerald-900/40 text-emerald-400' :
                          h.tier === 'tier_2' ? 'bg-green-900/40 text-green-400' :
                          h.tier === 'tier_3' ? 'bg-yellow-900/40 text-yellow-400' :
                          'bg-gray-900/40 text-gray-400'
                        }`}>
                          {h.tier === 'tier_1' ? 'T1' : h.tier === 'tier_2' ? 'T2' : h.tier === 'tier_3' ? 'T3' : '--'}
                        </span>
                      )}
                      <span className="text-[#5a7a94] tabular-nums w-12 text-right">{h.score?.toFixed(0) ?? '--'}</span>
                      <span className="text-[#6f87a0] tabular-nums w-14 text-right">{(h.weight * 100).toFixed(1)}%</span>
                      <span className={`tabular-nums w-16 text-right ${h.return_pct >= 0 ? 'text-green-400' : 'text-red-400'}`}>
                        {fmtPct(h.return_pct)}
                      </span>
                    </div>
                  ))}
                </div>
              )}
            </div>
          ))}
        </div>
      </div>

      {/* Info Note */}
      <div className="flex items-start gap-2 text-xs text-[#5a7a94] pt-3 border-t border-[#1e3a5f]">
        <Info className="w-3 h-3 mt-0.5 flex-shrink-0" />
        <span>
          Backtest uses historical pool data from TaoStats API. Returns are calculated based on alpha price changes
          between rebalancing periods. Subnets are filtered using actual registration dates for accurate age calculation.
        </span>
      </div>
    </div>
  )
}

export type { BacktestResults, Period, Holding }
