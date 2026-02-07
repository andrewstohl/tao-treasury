import { useState, useEffect } from 'react'
import { useQuery } from '@tanstack/react-query'
import {
  ArrowUp,
  ArrowDown,
  LogOut,
  RefreshCw,
  AlertTriangle,
  CheckCircle,
  Clock,
  Settings,
  Info,
} from 'lucide-react'
import { Link } from 'react-router-dom'
import { api } from '../services/api'
import {
  loadRebalanceConfig,
  getDaysUntilRebalance,
  isRebalanceDue,
  updateLastRebalanceDate,
  type RebalanceConfig,
} from '../services/settingsStore'
import type { ComputeTargetResponse, PositionSnapshot, TradeRecommendation } from '../types'

function formatTao(value: number): string {
  if (Math.abs(value) >= 1000) {
    return value.toLocaleString(undefined, { minimumFractionDigits: 0, maximumFractionDigits: 0 })
  }
  return value.toLocaleString(undefined, { minimumFractionDigits: 2, maximumFractionDigits: 2 })
}

function ScheduleStatus({ config }: { config: RebalanceConfig }) {
  const daysUntil = getDaysUntilRebalance()
  const isDue = isRebalanceDue()

  return (
    <div className={`flex items-center gap-2 px-3 py-1.5 rounded-lg text-sm ${
      isDue ? 'bg-yellow-900/30 text-yellow-400' : 'bg-[#1a2d42] text-[#6f87a0]'
    }`}>
      <Clock size={14} />
      {isDue ? (
        <span>Rebalance due</span>
      ) : daysUntil !== null ? (
        <span>{daysUntil}d until rebalance</span>
      ) : (
        <span>Every {config.rebalanceIntervalDays}d</span>
      )}
    </div>
  )
}

function PortfolioColumn({
  title,
  subtitle,
  positions,
  totalValue,
  emptyMessage,
  showScore = false,
  alignToNetuids,
  otherPortfolioNetuids,
  isCurrentPortfolio = false,
}: {
  title: string
  subtitle?: string
  positions: PositionSnapshot[]
  totalValue: number
  emptyMessage: string
  showScore?: boolean
  alignToNetuids?: number[]  // Order to sort by (from target portfolio)
  otherPortfolioNetuids?: Set<number>  // Netuids in the other portfolio
  isCurrentPortfolio?: boolean
}) {
  // Sort positions to align with target portfolio order
  const sortedPositions = [...positions].sort((a, b) => {
    if (alignToNetuids) {
      const aIdx = alignToNetuids.indexOf(a.netuid)
      const bIdx = alignToNetuids.indexOf(b.netuid)
      // Items in alignToNetuids come first, sorted by their order
      // Items not in alignToNetuids go to the end, sorted by weight
      if (aIdx >= 0 && bIdx >= 0) return aIdx - bIdx
      if (aIdx >= 0) return -1
      if (bIdx >= 0) return 1
      return b.weight_pct - a.weight_pct
    }
    // Default: sort by weight descending
    return b.weight_pct - a.weight_pct
  })

  return (
    <div className="bg-[#121f2d] rounded-lg border border-[#1e3a5f] flex flex-col h-full">
      <div className="p-4 border-b border-[#1e3a5f]">
        <h3 className="font-semibold text-white">{title}</h3>
        {subtitle && <p className="text-xs text-[#5a7a94] mt-0.5">{subtitle}</p>}
        <div className="mt-2 text-sm text-[#6f87a0]">
          Total: <span className="text-white tabular-nums">{formatTao(totalValue)} τ</span>
          <span className="text-[#5a7a94] ml-2">({positions.length} positions)</span>
        </div>
      </div>

      <div className="flex-1 overflow-auto p-2">
        {sortedPositions.length === 0 ? (
          <div className="flex items-center justify-center h-32 text-[#5a7a94] text-sm">
            {emptyMessage}
          </div>
        ) : (
          <div className="space-y-1">
            {sortedPositions.map((pos) => {
              // Check if this position is in the other portfolio
              const inOtherPortfolio = otherPortfolioNetuids?.has(pos.netuid) ?? true
              const isToExit = isCurrentPortfolio && !inOtherPortfolio
              const isNewBuy = !isCurrentPortfolio && otherPortfolioNetuids && !otherPortfolioNetuids.has(pos.netuid)

              return (
                <div
                  key={pos.netuid}
                  className={`flex items-center justify-between p-2 rounded ${
                    isToExit ? 'bg-red-900/20 border border-red-900/30' :
                    isNewBuy ? 'bg-green-900/20 border border-green-900/30' :
                    'bg-[#0a1520] hover:bg-[#0d1825]'
                  }`}
                >
                  <div className="flex-1 min-w-0">
                    <div className="flex items-center gap-2">
                      <span className="text-xs text-[#5a7a94]">SN{pos.netuid}</span>
                      <span className={`text-sm truncate ${isToExit ? 'text-red-300' : isNewBuy ? 'text-green-300' : 'text-white'}`}>
                        {pos.name}
                      </span>
                      {isToExit && (
                        <span className="text-[10px] px-1.5 py-0.5 rounded bg-red-900/40 text-red-400">EXIT</span>
                      )}
                      {isNewBuy && (
                        <span className="text-[10px] px-1.5 py-0.5 rounded bg-green-900/40 text-green-400">NEW</span>
                      )}
                    </div>
                    <div className="text-xs text-[#5a7a94] mt-0.5">
                      {formatTao(pos.tao_value)} τ
                    </div>
                  </div>
                  <div className="text-right">
                    <div className={`text-sm tabular-nums ${isToExit ? 'text-red-300' : isNewBuy ? 'text-green-300' : 'text-white'}`}>
                      {pos.weight_pct.toFixed(1)}%
                    </div>
                    {showScore && pos.viability_score !== undefined && (
                      <div className="text-xs text-tao-400 tabular-nums">
                        Score: {pos.viability_score.toFixed(0)}
                      </div>
                    )}
                  </div>
                </div>
              )
            })}
          </div>
        )}
      </div>
    </div>
  )
}

function TradesColumn({
  trades,
  onExecuteAll,
  isExecuting,
  currentCount,
  targetCount,
}: {
  trades: TradeRecommendation[]
  onExecuteAll: () => void
  isExecuting: boolean
  currentCount: number
  targetCount: number
}) {
  const exits = trades.filter((t) => t.action === 'exit')
  const sells = trades.filter((t) => t.action === 'sell')
  const buys = trades.filter((t) => t.action === 'buy')

  const totalSell = trades.filter(t => t.action !== 'buy').reduce((sum, t) => sum + t.tao_amount, 0)
  const totalBuy = trades.filter(t => t.action === 'buy').reduce((sum, t) => sum + t.tao_amount, 0)

  const renderTrade = (trade: TradeRecommendation) => {
    const actionColors = {
      exit: 'bg-red-900/30 text-red-400',
      sell: 'bg-orange-900/30 text-orange-400',
      buy: 'bg-green-900/30 text-green-400',
    }
    const ActionIcon = trade.action === 'buy' ? ArrowUp : trade.action === 'exit' ? LogOut : ArrowDown

    return (
      <div
        key={`${trade.netuid}-${trade.action}`}
        className="flex items-start justify-between p-3 rounded bg-[#0a1520] hover:bg-[#0d1825]"
      >
        <div className="flex items-start gap-3">
          <div className={`p-1.5 rounded ${actionColors[trade.action]}`}>
            <ActionIcon size={14} />
          </div>
          <div>
            <div className="flex items-center gap-2">
              <span className="text-sm font-medium capitalize text-white">{trade.action}</span>
              <span className="text-xs text-[#5a7a94]">SN{trade.netuid}</span>
            </div>
            <div className="text-xs text-[#6f87a0] mt-0.5">{trade.name}</div>
            <div className="text-xs text-[#5a7a94] mt-1">{trade.reason}</div>
          </div>
        </div>
        <div className="text-right">
          <div className="text-sm text-white tabular-nums">{formatTao(trade.tao_amount)} τ</div>
          <div className="text-xs text-[#5a7a94] tabular-nums">
            {trade.current_weight_pct.toFixed(1)}% → {trade.target_weight_pct.toFixed(1)}%
          </div>
        </div>
      </div>
    )
  }

  return (
    <div className="bg-[#121f2d] rounded-lg border border-[#1e3a5f] flex flex-col h-full">
      <div className="p-4 border-b border-[#1e3a5f]">
        <div className="flex items-center justify-between">
          <div>
            <h3 className="font-semibold text-white">Required Trades</h3>
            <p className="text-xs text-[#5a7a94] mt-0.5">Execute in order shown</p>
          </div>
          {trades.length > 0 && (
            <button
              onClick={onExecuteAll}
              disabled={isExecuting}
              className="flex items-center gap-2 px-3 py-1.5 bg-tao-600 hover:bg-tao-500 rounded text-white text-sm disabled:opacity-50"
            >
              <CheckCircle size={14} />
              {isExecuting ? 'Marking...' : 'Mark All Done'}
            </button>
          )}
        </div>
        <div className="flex items-center gap-4 mt-2 text-sm">
          <span className="text-red-400">Sell: {formatTao(totalSell)} τ</span>
          <span className="text-green-400">Buy: {formatTao(totalBuy)} τ</span>
        </div>
      </div>

      <div className="flex-1 overflow-auto p-2">
        {trades.length === 0 ? (
          <div className="flex flex-col items-center justify-center h-32 text-[#5a7a94] text-sm">
            <CheckCircle size={24} className="text-green-400 mb-2" />
            <span>Portfolio is balanced</span>
          </div>
        ) : (
          <div className="space-y-3">
            {/* Exits first */}
            {exits.length > 0 && (
              <div>
                <div className="text-xs font-medium text-red-400 px-2 py-1">
                  1. Exit Positions ({exits.length})
                </div>
                <div className="space-y-1">{exits.map(renderTrade)}</div>
              </div>
            )}

            {/* Sells */}
            {sells.length > 0 && (
              <div>
                <div className="text-xs font-medium text-orange-400 px-2 py-1">
                  2. Reduce Positions ({sells.length})
                </div>
                <div className="space-y-1">{sells.map(renderTrade)}</div>
              </div>
            )}

            {/* Buys */}
            {buys.length > 0 && (
              <div>
                <div className="text-xs font-medium text-green-400 px-2 py-1">
                  3. Increase Positions ({buys.length})
                </div>
                <div className="space-y-1">{buys.map(renderTrade)}</div>
              </div>
            )}

            {/* Info when no buys but there should be new positions */}
            {buys.length === 0 && targetCount > currentCount && (
              <div className="mt-2 p-2 bg-[#0a1520] rounded text-xs text-[#5a7a94]">
                <span className="text-tao-400">Note:</span> New position additions may be below the position threshold
              </div>
            )}
          </div>
        )}
      </div>
    </div>
  )
}

export default function Recommendations() {
  const [config, setConfig] = useState<RebalanceConfig>(loadRebalanceConfig)
  const [isComputing, setIsComputing] = useState(false)
  const [computeError, setComputeError] = useState<string | null>(null)

  // Reload config when settings change
  useEffect(() => {
    const handleStorageChange = () => {
      setConfig(loadRebalanceConfig())
    }
    window.addEventListener('storage', handleStorageChange)
    return () => window.removeEventListener('storage', handleStorageChange)
  }, [])

  // Compute target portfolio
  const { data, isLoading, error, refetch } = useQuery<ComputeTargetResponse>({
    queryKey: ['rebalance-target', config],
    queryFn: async () => {
      setIsComputing(true)
      setComputeError(null)
      try {
        const response = await api.computeTargetPortfolio({
          strategy: config.strategy,
          top_percentile: config.topPercentile,
          max_position_pct: config.maxPositionPct,
          position_threshold_pct: config.positionThresholdPct,
          portfolio_threshold_pct: config.portfolioThresholdPct,
          use_backend_viability_config: config.useBackendViabilityConfig,
          viability_config: config.useBackendViabilityConfig
            ? undefined
            : {
                min_age_days: config.minAgeDays,
                min_reserve_tao: config.minReserveTao,
                max_outflow_7d_pct: config.maxOutflow7dPct,
                max_drawdown_pct: config.maxDrawdownPct,
                fai_weight: config.faiWeight,
                reserve_weight: config.reserveWeight,
                emission_weight: config.emissionWeight,
                stability_weight: config.stabilityWeight,
              },
        })
        return response
      } catch (e) {
        const msg = e instanceof Error ? e.message : 'Failed to compute target'
        setComputeError(msg)
        throw e
      } finally {
        setIsComputing(false)
      }
    },
    staleTime: 60000, // 1 minute
    refetchOnWindowFocus: false,
  })

  const handleMarkAllDone = () => {
    updateLastRebalanceDate()
    setConfig(loadRebalanceConfig())
    refetch()
  }

  const currentPortfolio = data?.current_portfolio || []
  const targetPortfolio = data?.target_portfolio || []
  const trades = data?.trades || []
  const summary = data?.summary

  const portfolioValue = summary?.current_portfolio_value || 0

  if (isLoading && !data) {
    return (
      <div className="flex items-center justify-center h-64">
        <div className="flex flex-col items-center gap-3">
          <div className="animate-spin rounded-full h-8 w-8 border-b-2 border-tao-400"></div>
          <span className="text-[#6f87a0] text-sm">Computing target portfolio...</span>
        </div>
      </div>
    )
  }

  return (
    <div className="space-y-6 w-full">
      {/* Header */}
      <div className="flex items-center justify-between">
        <div>
          <h1 className="text-2xl font-bold">Rebalance Advisor</h1>
          <p className="text-sm text-[#6f87a0] mt-1">
            Compare current portfolio to optimal target allocation
          </p>
        </div>
        <div className="flex items-center gap-3">
          <ScheduleStatus config={config} />
          <Link
            to="/settings"
            className="flex items-center gap-2 px-3 py-1.5 bg-[#1a2d42] hover:bg-[#243a52] rounded text-sm text-[#8faabe]"
          >
            <Settings size={14} />
            Settings
          </Link>
          <button
            onClick={() => refetch()}
            disabled={isComputing}
            className="flex items-center gap-2 px-3 py-1.5 bg-[#1a2d42] hover:bg-[#243a52] rounded text-sm text-[#8faabe] disabled:opacity-50"
          >
            <RefreshCw size={14} className={isComputing ? 'animate-spin' : ''} />
            Refresh
          </button>
        </div>
      </div>

      {/* Error Display */}
      {(error || computeError) && (
        <div className="bg-red-900/20 border border-red-700 rounded-lg p-4 flex items-center gap-3">
          <AlertTriangle className="text-red-400" size={20} />
          <div>
            <p className="text-red-400 font-medium">Failed to compute target portfolio</p>
            <p className="text-red-300 text-sm">{computeError || 'Unknown error'}</p>
          </div>
        </div>
      )}

      {/* Summary Banner */}
      {summary && (
        <div
          className={`rounded-lg p-4 border ${
            summary.needs_rebalance
              ? 'bg-yellow-900/20 border-yellow-700'
              : 'bg-green-900/20 border-green-700'
          }`}
        >
          <div className="flex items-center justify-between">
            <div className="flex items-center gap-3">
              {summary.needs_rebalance ? (
                <AlertTriangle className="text-yellow-400" size={20} />
              ) : (
                <CheckCircle className="text-green-400" size={20} />
              )}
              <div>
                <span
                  className={`font-medium ${
                    summary.needs_rebalance ? 'text-yellow-400' : 'text-green-400'
                  }`}
                >
                  {summary.needs_rebalance
                    ? `Rebalance recommended (${summary.total_drift_pct.toFixed(1)}% drift)`
                    : 'Portfolio is within tolerance'}
                </span>
                <p className="text-sm text-[#6f87a0]">
                  {summary.trades_count} trades | Turnover: {summary.net_turnover_pct.toFixed(1)}%
                </p>
              </div>
            </div>
            <div className="flex items-center gap-4 text-sm">
              <div className="text-center">
                <div className="text-[#5a7a94]">Strategy</div>
                <div className="text-white capitalize">{config.strategy.replace('_', ' ')}</div>
              </div>
              <div className="text-center">
                <div className="text-[#5a7a94]">Top %</div>
                <div className="text-white">{config.topPercentile}%</div>
              </div>
              <div className="text-center">
                <div className="text-[#5a7a94]">Viable</div>
                <div className="text-white">{data?.viable_subnets_count || 0}</div>
              </div>
            </div>
          </div>
        </div>
      )}

      {/* Info Note */}
      <div className="flex items-start gap-2 text-xs text-[#5a7a94] bg-[#0a1520] rounded p-3 border border-[#1e3a5f]/50">
        <Info className="w-4 h-4 mt-0.5 flex-shrink-0 text-tao-400" />
        <div>
          <span className="text-[#a8c4d9] font-medium">Manual Execution: </span>
          Execute trades in order shown (exits → sells → buys). After completing all trades,
          click "Mark All Done" to update the rebalance schedule.
        </div>
      </div>

      {/* 3-Column Layout */}
      <div className="grid grid-cols-1 lg:grid-cols-3 gap-4" style={{ minHeight: '500px' }}>
        <PortfolioColumn
          title="Current Portfolio"
          subtitle="Your existing positions"
          positions={currentPortfolio}
          totalValue={portfolioValue}
          emptyMessage="No positions found"
          alignToNetuids={targetPortfolio.map(p => p.netuid)}
          otherPortfolioNetuids={new Set(targetPortfolio.map(p => p.netuid))}
          isCurrentPortfolio={true}
        />

        <PortfolioColumn
          title="Target Portfolio"
          subtitle={`Top ${config.topPercentile}% viable subnets`}
          positions={targetPortfolio}
          totalValue={portfolioValue}
          emptyMessage="No viable subnets"
          showScore
          otherPortfolioNetuids={new Set(currentPortfolio.map(p => p.netuid))}
        />

        <TradesColumn
          trades={trades}
          onExecuteAll={handleMarkAllDone}
          isExecuting={false}
          currentCount={currentPortfolio.length}
          targetCount={targetPortfolio.length}
        />
      </div>

      {/* Config Summary Footer */}
      <div className="bg-[#0a1520] rounded-lg p-4 border border-[#1e3a5f]/50">
        <div className="flex items-center justify-between text-xs text-[#5a7a94]">
          <div className="flex items-center gap-4">
            <span>
              Position threshold: <span className="text-[#6f87a0]">{config.positionThresholdPct}%</span>
            </span>
            <span>
              Portfolio threshold: <span className="text-[#6f87a0]">{config.portfolioThresholdPct}%</span>
            </span>
            <span>
              Max position: <span className="text-[#6f87a0]">{config.maxPositionPct}%</span>
            </span>
          </div>
          <span>
            Last computed: {data?.computed_at ? new Date(data.computed_at).toLocaleTimeString() : '-'}
          </span>
        </div>
      </div>
    </div>
  )
}
