import { useState, useMemo } from 'react'
import { useQuery } from '@tanstack/react-query'
import {
  GitCompare,
  Wallet,
  Target,
  TrendingUp,
  TrendingDown,
  AlertCircle,
  ChevronRight,
  ArrowRightLeft,
  Plus,
  Minus,
} from 'lucide-react'
import { supabaseQueries } from '../services/supabase'

// Strategy display names
const STRATEGY_DISPLAY_NAMES: Record<string, string> = {
  bedrock: 'Bedrock',
  yield_hunter: 'Sharpe Hunter',
  contrarian: 'Vol-Targeted',
  bedrock_v2: 'Bedrock V2',
  sharpe_hunter_v2: 'Sharpe Hunter V2',
  vol_targeted_v2: 'Vol-Targeted V2',
  sharpe_rolling: 'Sharpe Rolling',
  sharpe_top5: 'Sharpe Top 5',
  bedrock_tight_21d: 'Bedrock Tight 21D',
}

// Parse positions from notes JSON
interface PositionData {
  positions: Record<string, number>
  positionCount: number
}

function parsePositions(notes: string | null): PositionData | null {
  if (!notes) return null
  try {
    const parsed = JSON.parse(notes)
    if (parsed.positions && typeof parsed.positionCount === 'number') {
      return parsed as PositionData
    }
    return null
  } catch {
    return null
  }
}

// Format percentage
function formatPct(value: number | null | undefined): string {
  if (value === null || value === undefined) return 'N/A'
  return `${value.toFixed(2)}%`
}

// Format number
function formatNum(value: number | null | undefined, decimals = 4): string {
  if (value === null || value === undefined) return 'N/A'
  return value.toFixed(decimals)
}

interface PortfolioPosition {
  netuid: number
  subnet_name?: string
  weight_pct?: number
  tao_value?: number
}

interface ComparisonRow {
  netuid: number
  subnetName: string
  portfolioWeight: number
  strategyWeight: number
  diff: number
  action: 'buy' | 'sell' | 'hold' | 'new'
}

export default function Compare() {
  const [selectedStrategy, setSelectedStrategy] = useState<string>('bedrock')

  // Fetch all strategy IDs
  const { data: strategyIds } = useQuery({
    queryKey: ['supabase-strategy-ids'],
    queryFn: supabaseQueries.getStrategyIds,
    refetchInterval: 300000,
  })

  // Fetch latest strategy positions
  const { data: strategyData, isLoading: isLoadingStrategy } = useQuery({
    queryKey: ['supabase-strategy-positions', selectedStrategy],
    queryFn: () => supabaseQueries.getLatestStrategyPositions(selectedStrategy),
    enabled: !!selectedStrategy,
    refetchInterval: 60000,
  })

  // Fetch portfolio positions
  const { data: portfolioData, isLoading: isLoadingPortfolio } = useQuery({
    queryKey: ['supabase-portfolio-positions'],
    queryFn: supabaseQueries.getPortfolioPositions,
    refetchInterval: 60000,
  })

  // Parse strategy positions
  const strategyPositions = useMemo(() => {
    if (!strategyData) return null
    return parsePositions(strategyData.notes)
  }, [strategyData])

  // Parse portfolio positions
  const portfolioPositions = useMemo(() => {
    if (!portfolioData || portfolioData.length === 0) return []
    return portfolioData as PortfolioPosition[]
  }, [portfolioData])

  // Build comparison table
  const comparisonRows = useMemo((): ComparisonRow[] => {
    const rows: ComparisonRow[] = []
    const allNetuids = new Set<number>()

    // Add portfolio positions
    portfolioPositions.forEach((pos) => {
      allNetuids.add(pos.netuid)
    })

    // Add strategy positions
    if (strategyPositions) {
      Object.keys(strategyPositions.positions).forEach((netuid) => {
        allNetuids.add(parseInt(netuid))
      })
    }

    // Build rows
    allNetuids.forEach((netuid) => {
      const portfolioPos = portfolioPositions.find((p) => p.netuid === netuid)
      const strategyWeight = strategyPositions?.positions[netuid.toString()] || 0
      const portfolioWeight = portfolioPos?.weight_pct || 0
      const diff = strategyWeight - portfolioWeight

      let action: 'buy' | 'sell' | 'hold' | 'new' = 'hold'
      if (portfolioWeight === 0 && strategyWeight > 0) {
        action = 'new'
      } else if (diff > 0.05) {
        action = 'buy'
      } else if (diff < -0.05) {
        action = 'sell'
      }

      rows.push({
        netuid,
        subnetName: portfolioPos?.subnet_name || `Subnet ${netuid}`,
        portfolioWeight,
        strategyWeight,
        diff,
        action,
      })
    })

    // Sort by absolute difference (largest first)
    return rows.sort((a, b) => Math.abs(b.diff) - Math.abs(a.diff))
  }, [portfolioPositions, strategyPositions])

  // Calculate summary stats
  const summary = useMemo(() => {
    const totalBuyDiff = comparisonRows
      .filter((r) => r.diff > 0)
      .reduce((sum, r) => sum + r.diff, 0)
    const totalSellDiff = comparisonRows
      .filter((r) => r.diff < 0)
      .reduce((sum, r) => sum + Math.abs(r.diff), 0)
    const newPositions = comparisonRows.filter((r) => r.action === 'new').length
    const sellPositions = comparisonRows.filter((r) => r.action === 'sell').length
    const matchingPositions = comparisonRows.filter((r) => r.action === 'hold').length

    return {
      totalBuyDiff,
      totalSellDiff,
      newPositions,
      sellPositions,
      matchingPositions,
      totalPositions: comparisonRows.length,
    }
  }, [comparisonRows])

  // Expected SN88 comparison
  const sn88Comparison = useMemo(() => {
    if (!strategyData) return null
    // Portfolio SN88 would come from the API - for now we show strategy only
    return {
      strategy: strategyData.sn88_score,
      portfolio: null, // Would come from portfolio data
    }
  }, [strategyData])

  const isLoading = isLoadingStrategy || isLoadingPortfolio

  return (
    <div className="space-y-6">
      {/* Header */}
      <div className="flex items-center justify-between">
        <div>
          <h1 className="text-2xl font-bold text-white flex items-center gap-2">
            <GitCompare className="w-6 h-6 text-[#2a3ded]" />
            Portfolio Comparison
          </h1>
          <p className="text-sm text-[#8a8f98] mt-1">
            Compare your current holdings against a strategy
          </p>
        </div>
      </div>

      {/* Strategy Selector */}
      <div className="bg-[#16181d] rounded-lg border border-[#2a2f38] p-4">
        <div className="flex items-center gap-4">
          <span className="text-sm text-[#9ca3af]">Select Strategy:</span>
          <select
            value={selectedStrategy}
            onChange={(e) => setSelectedStrategy(e.target.value)}
            className="bg-[#0d1117] border border-[#2a2f38] rounded-lg px-4 py-2 text-white text-sm focus:outline-none focus:border-[#2a3ded]"
          >
            {(strategyIds || []).map((id) => (
              <option key={id} value={id}>
                {STRATEGY_DISPLAY_NAMES[id] || id}
              </option>
            ))}
          </select>

          {strategyData && (
            <div className="flex items-center gap-4 ml-auto">
              <div className="text-right">
                <p className="text-xs text-[#6b7280]">Strategy NAV</p>
                <p className="text-sm font-bold text-white tabular-nums">
                  {formatNum(strategyData.nav, 4)} τ
                </p>
              </div>
              <div className="text-right">
                <p className="text-xs text-[#6b7280]">SN88 Score</p>
                <p
                  className={`text-sm font-bold tabular-nums ${
                    (strategyData.sn88_score || 0) >= 70
                      ? 'text-green-400'
                      : (strategyData.sn88_score || 0) >= 50
                      ? 'text-yellow-400'
                      : 'text-red-400'
                  }`}
                >
                  {formatNum(strategyData.sn88_score, 1)}
                </p>
              </div>
            </div>
          )}
        </div>
      </div>

      {/* Summary Cards */}
      <div className="grid grid-cols-2 md:grid-cols-4 gap-4">
        <div className="bg-[#16181d] rounded-lg border border-[#2a2f38] p-4">
          <div className="flex items-center gap-2 mb-2">
            <Plus className="w-4 h-4 text-green-400" />
            <span className="text-xs text-[#6b7280]">To Buy</span>
          </div>
          <div className="text-lg font-bold text-green-400 tabular-nums">
            {formatPct(summary.totalBuyDiff * 100)}
          </div>
          <div className="text-xs text-[#6b7280]">{summary.newPositions} new positions</div>
        </div>

        <div className="bg-[#16181d] rounded-lg border border-[#2a2f38] p-4">
          <div className="flex items-center gap-2 mb-2">
            <Minus className="w-4 h-4 text-red-400" />
            <span className="text-xs text-[#6b7280]">To Sell</span>
          </div>
          <div className="text-lg font-bold text-red-400 tabular-nums">
            {formatPct(summary.totalSellDiff * 100)}
          </div>
          <div className="text-xs text-[#6b7280]">{summary.sellPositions} to reduce</div>
        </div>

        <div className="bg-[#16181d] rounded-lg border border-[#2a2f38] p-4">
          <div className="flex items-center gap-2 mb-2">
            <ArrowRightLeft className="w-4 h-4 text-[#2a3ded]" />
            <span className="text-xs text-[#6b7280]">Matching</span>
          </div>
          <div className="text-lg font-bold text-white tabular-nums">
            {summary.matchingPositions}
          </div>
          <div className="text-xs text-[#6b7280]">positions aligned</div>
        </div>

        <div className="bg-[#16181d] rounded-lg border border-[#2a2f38] p-4">
          <div className="flex items-center gap-2 mb-2">
            <Target className="w-4 h-4 text-[#2a3ded]" />
            <span className="text-xs text-[#6b7280]">Total Turnover</span>
          </div>
          <div className="text-lg font-bold text-white tabular-nums">
            {formatPct((summary.totalBuyDiff + summary.totalSellDiff) * 100)}
          </div>
          <div className="text-xs text-[#6b7280]">estimated</div>
        </div>
      </div>

      {/* SN88 Score Comparison */}
      {sn88Comparison && (
        <div className="bg-[#16181d] rounded-lg border border-[#2a2f38] p-5">
          <div className="flex items-center gap-2 mb-4">
            <TrendingUp className="w-5 h-5 text-[#2a3ded]" />
            <h3 className="font-semibold text-white">SN88 Score Comparison</h3>
          </div>

          <div className="grid grid-cols-1 md:grid-cols-2 gap-6">
            {/* Your Portfolio */}
            <div className="bg-[#0d1117] rounded-lg p-4">
              <div className="flex items-center gap-2 mb-3">
                <Wallet className="w-4 h-4 text-[#6b7280]" />
                <span className="text-sm text-[#9ca3af]">Your Portfolio</span>
              </div>
              <div className="text-3xl font-bold text-[#6b7280]">--</div>
              <p className="text-xs text-[#6b7280] mt-1">
                Portfolio scoring coming soon
              </p>
            </div>

            {/* Strategy */}
            <div className="bg-[#0d1117] rounded-lg p-4">
              <div className="flex items-center gap-2 mb-3">
                <Target className="w-4 h-4 text-[#2a3ded]" />
                <span className="text-sm text-[#9ca3af]">
                  {STRATEGY_DISPLAY_NAMES[selectedStrategy] || selectedStrategy}
                </span>
              </div>
              <div
                className={`text-3xl font-bold ${
                  (sn88Comparison.strategy || 0) >= 70
                    ? 'text-green-400'
                    : (sn88Comparison.strategy || 0) >= 50
                    ? 'text-yellow-400'
                    : 'text-red-400'
                }`}
              >
                {formatNum(sn88Comparison.strategy, 1)}
              </div>
              <p className="text-xs text-[#6b7280] mt-1">
                Based on historical performance
              </p>
            </div>
          </div>
        </div>
      )}

      {/* Comparison Table */}
      <div className="bg-[#16181d] rounded-lg border border-[#2a2f38] overflow-hidden">
        <div className="px-5 py-4 border-b border-[#2a2f38]">
          <div className="flex items-center justify-between">
            <div className="flex items-center gap-2">
              <GitCompare className="w-5 h-5 text-[#2a3ded]" />
              <h3 className="font-semibold text-white">Position Comparison</h3>
            </div>
            <span className="text-sm text-[#6b7280]">
              {comparisonRows.length} positions
            </span>
          </div>
        </div>

        {isLoading ? (
          <div className="p-8">
            <div className="space-y-2">
              {[1, 2, 3, 4, 5].map((i) => (
                <div key={i} className="h-12 bg-[#1e2128] rounded animate-pulse" />
              ))}
            </div>
          </div>
        ) : (
          <div className="overflow-x-auto">
            <table className="w-full">
              <thead>
                <tr className="bg-[#0d0f12]">
                  <th className="px-4 py-3 text-left text-xs font-semibold text-[#6b7280] uppercase tracking-wider">
                    Subnet
                  </th>
                  <th className="px-4 py-3 text-right text-xs font-semibold text-[#6b7280] uppercase tracking-wider">
                    Your Portfolio
                  </th>
                  <th className="px-4 py-3 text-right text-xs font-semibold text-[#6b7280] uppercase tracking-wider">
                    Strategy
                  </th>
                  <th className="px-4 py-3 text-right text-xs font-semibold text-[#6b7280] uppercase tracking-wider">
                    Difference
                  </th>
                  <th className="px-4 py-3 text-center text-xs font-semibold text-[#6b7280] uppercase tracking-wider">
                    Action
                  </th>
                </tr>
              </thead>
              <tbody className="divide-y divide-[#2a2f38]">
                {comparisonRows.map((row, index) => (
                  <tr
                    key={row.netuid}
                    className={index % 2 === 0 ? 'bg-[#0d1117]' : 'bg-[#16181d]'}
                  >
                    <td className="px-4 py-3">
                      <div className="flex items-center gap-2">
                        <span className="text-sm font-medium text-white">
                          {row.subnetName}
                        </span>
                        <span className="text-xs text-[#6b7280]">
                          (SN{row.netuid})
                        </span>
                      </div>
                    </td>
                    <td className="px-4 py-3 text-right">
                      <span className="text-sm text-white tabular-nums">
                        {formatPct(row.portfolioWeight * 100)}
                      </span>
                    </td>
                    <td className="px-4 py-3 text-right">
                      <span className="text-sm text-[#2a3ded] tabular-nums">
                        {formatPct(row.strategyWeight * 100)}
                      </span>
                    </td>
                    <td className="px-4 py-3 text-right">
                      <span
                        className={`text-sm font-medium tabular-nums ${
                          row.diff > 0 ? 'text-green-400' : row.diff < 0 ? 'text-red-400' : 'text-[#6b7280]'
                        }`}
                      >
                        {row.diff > 0 ? '+' : ''}
                        {formatPct(row.diff * 100)}
                      </span>
                    </td>
                    <td className="px-4 py-3 text-center">
                      {row.action === 'new' && (
                        <span className="inline-flex items-center gap-1 px-2 py-1 rounded-full text-xs bg-green-400/20 text-green-400">
                          <Plus className="w-3 h-3" />
                          Buy New
                        </span>
                      )}
                      {row.action === 'buy' && (
                        <span className="inline-flex items-center gap-1 px-2 py-1 rounded-full text-xs bg-green-400/20 text-green-400">
                          <TrendingUp className="w-3 h-3" />
                          Increase
                        </span>
                      )}
                      {row.action === 'sell' && (
                        <span className="inline-flex items-center gap-1 px-2 py-1 rounded-full text-xs bg-red-400/20 text-red-400">
                          <TrendingDown className="w-3 h-3" />
                          Reduce
                        </span>
                      )}
                      {row.action === 'hold' && (
                        <span className="inline-flex items-center gap-1 px-2 py-1 rounded-full text-xs bg-[#2a3ded]/20 text-[#2a3ded]">
                          <ArrowRightLeft className="w-3 h-3" />
                          Hold
                        </span>
                      )}
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
            {comparisonRows.length === 0 && (
              <div className="text-center py-8 text-[#6b7280]">
                No positions to compare
              </div>
            )}
          </div>
        )}
      </div>

      {/* Empty Portfolio Warning */}
      {portfolioPositions.length === 0 && !isLoadingPortfolio && (
        <div className="bg-yellow-400/10 border border-yellow-400/30 rounded-lg p-4">
          <div className="flex items-start gap-3">
            <AlertCircle className="w-5 h-5 text-yellow-400 mt-0.5" />
            <div>
              <p className="text-sm font-medium text-yellow-400">
                Portfolio Data Not Available
              </p>
              <p className="text-sm text-[#9ca3af] mt-1">
                We couldn&apos;t retrieve your current portfolio positions. The comparison
                is showing strategy allocations only. Make sure your wallet is connected
                and the portfolio_positions table exists.
              </p>
            </div>
          </div>
        </div>
      )}

      {/* Implementation Notes */}
      <div className="bg-[#16181d] rounded-lg border border-[#2a2f38] p-5">
        <h3 className="font-semibold text-white mb-3">Implementation Notes</h3>
        <ul className="space-y-2 text-sm text-[#9ca3af]">
          <li className="flex items-start gap-2">
            <ChevronRight className="w-4 h-4 text-[#2a3ded] mt-0.5" />
            <span>
              Positions marked <strong className="text-green-400">&quot;Buy New&quot;</strong> are held
              by the strategy but not in your portfolio.
            </span>
          </li>
          <li className="flex items-start gap-2">
            <ChevronRight className="w-4 h-4 text-[#2a3ded] mt-0.5" />
            <span>
              Positions marked <strong className="text-red-400">&quot;Reduce&quot;</strong> exceed the
              strategy&apos;s allocation by more than 5%.
            </span>
          </li>
          <li className="flex items-start gap-2">
            <ChevronRight className="w-4 h-4 text-[#2a3ded] mt-0.5" />
            <span>
              Consider transaction costs and slippage when rebalancing to match the
              strategy.
            </span>
          </li>
          <li className="flex items-start gap-2">
            <ChevronRight className="w-4 h-4 text-[#2a3ded] mt-0.5" />
            <span>
              Historical SN88 scores don&apos;t guarantee future performance.
            </span>
          </li>
        </ul>
      </div>
    </div>
  )
}