import { useQuery } from '@tanstack/react-query'
import { Link } from 'react-router-dom'
import {
  Activity,
  TrendingUp,
  TrendingDown,
  Database,
  Clock,
  AlertCircle,
  CheckCircle,
  XCircle,
  Wallet,
  BarChart3,
  ArrowRight,
} from 'lucide-react'
import { supabase } from '../services/supabase'
import type { StrategyLedger, DataFreshness, SubnetProfile } from '../services/supabase'

// Types for raw API data
interface PortfolioPosition {
  netuid: number
  stake: number
  token_symbol?: string
  name?: string
  daily_change_pct?: number
  value_tao?: number
}

interface PortfolioData {
  positions?: PortfolioPosition[]
  total_stake?: number
  total_value_tao?: number
  daily_pnl_pct?: number
  daily_pnl_tao?: number
  position_count?: number
}

// Query functions
const fetchPortfolioData = async (): Promise<{ data: PortfolioData; fetchedAt: string } | null> => {
  const { data, error } = await supabase
    .from('raw_api_data')
    .select('response, fetched_at')
    .eq('source', 'portfolio_current')
    .order('fetched_at', { ascending: false })
    .limit(1)
    .single()

  if (error) {
    console.error('Error fetching portfolio data:', error)
    return null
  }

  return {
    data: data?.response || {},
    fetchedAt: data?.fetched_at,
  }
}

const fetchLatestStrategyData = async (): Promise<StrategyLedger[]> => {
  const { data, error } = await supabase
    .from('strategy_ledger')
    .select('*')
    .order('date', { ascending: false })

  if (error) {
    console.error('Error fetching strategy data:', error)
    return []
  }

  // Get latest entry for each strategy
  const latestByStrategy = new Map<string, StrategyLedger>()
  data?.forEach((row) => {
    if (!latestByStrategy.has(row.strategy_id)) {
      latestByStrategy.set(row.strategy_id, row as StrategyLedger)
    }
  })

  return Array.from(latestByStrategy.values())
}

const fetchDataFreshness = async (): Promise<DataFreshness[]> => {
  const { data, error } = await supabase
    .from('data_freshness')
    .select('*')
    .order('source', { ascending: true })

  if (error) {
    console.error('Error fetching data freshness:', error)
    return []
  }

  return (data || []) as DataFreshness[]
}

const fetchSubnetProfiles = async (): Promise<Map<number, SubnetProfile>> => {
  const { data, error } = await supabase
    .from('subnet_profiles')
    .select('*')

  if (error) {
    console.error('Error fetching subnet profiles:', error)
    return new Map()
  }

  const profiles = new Map<number, SubnetProfile>()
  data?.forEach((row) => {
    profiles.set(row.netuid, row as SubnetProfile)
  })

  return profiles
}

// Helper functions
function formatTao(value: number): string {
  return value?.toLocaleString(undefined, { minimumFractionDigits: 2, maximumFractionDigits: 2 }) || '0.00'
}

function formatPercent(value: number): string {
  const sign = value >= 0 ? '+' : ''
  return `${sign}${value?.toFixed(2) || '0.00'}%`
}

function getTimeSince(dateString: string): string {
  const date = new Date(dateString)
  const now = new Date()
  const diffMs = now.getTime() - date.getTime()
  const diffHours = Math.floor(diffMs / (1000 * 60 * 60))
  const diffMins = Math.floor(diffMs / (1000 * 60))

  if (diffHours > 0) {
    return `${diffHours}h ago`
  }
  return `${diffMins}m ago`
}

function getFreshnessColor(minutes: number): string {
  if (minutes < 60) return 'text-green-400'
  if (minutes < 240) return 'text-yellow-400'
  return 'text-red-400'
}

function getFreshnessBgColor(minutes: number): string {
  if (minutes < 60) return 'bg-green-600/20 border-green-600'
  if (minutes < 240) return 'bg-yellow-600/20 border-yellow-600'
  return 'bg-red-600/20 border-red-600'
}

// Strategy display names and colors
const strategyConfig: Record<string, { name: string; color: string }> = {
  smart_money_mimic: { name: 'Smart Money Mimic', color: 'bg-blue-600/20 text-blue-400 border-blue-600' },
  multi_factor_hybrid: { name: 'Multi-Factor Hybrid', color: 'bg-purple-600/20 text-purple-400 border-purple-600' },
  broad_quality_basket: { name: 'Broad Quality Basket', color: 'bg-emerald-600/20 text-emerald-400 border-emerald-600' },
  bedrock: { name: 'Bedrock', color: 'bg-orange-600/20 text-orange-400 border-orange-600' },
  yield_hunter: { name: 'Yield Hunter', color: 'bg-pink-600/20 text-pink-400 border-pink-600' },
  contrarian: { name: 'Contrarian', color: 'bg-cyan-600/20 text-cyan-400 border-cyan-600' },
}

export default function Track() {
  // Fetch all data
  const { data: portfolioResult, isLoading: portfolioLoading } = useQuery({
    queryKey: ['track-portfolio'],
    queryFn: fetchPortfolioData,
    refetchInterval: 120000,
  })

  const { data: strategies, isLoading: strategiesLoading } = useQuery({
    queryKey: ['track-strategies'],
    queryFn: fetchLatestStrategyData,
    refetchInterval: 120000,
  })

  const { data: freshnessData, isLoading: freshnessLoading } = useQuery({
    queryKey: ['track-freshness'],
    queryFn: fetchDataFreshness,
    refetchInterval: 60000,
  })

  const { data: subnetProfiles, isLoading: profilesLoading } = useQuery({
    queryKey: ['track-subnet-profiles'],
    queryFn: fetchSubnetProfiles,
    refetchInterval: 300000,
  })

  const portfolio = portfolioResult?.data || {}
  const positions: PortfolioPosition[] = portfolio.positions || []

  // Calculate totals if not provided
  const totalTao = portfolio.total_value_tao || portfolio.total_stake || 
    positions.reduce((sum, p) => sum + (p.value_tao || p.stake || 0), 0)
  
  const positionCount = portfolio.position_count || positions.length

  // Parse positions and merge with subnet profiles
  const enrichedPositions = positions.map((pos) => {
    const profile = subnetProfiles?.get(pos.netuid)
    return {
      ...pos,
      name: profile?.subnet_name || pos.name || `Subnet ${pos.netuid}`,
      daily_change_pct: pos.daily_change_pct || profile?.daily_return_pct || 0,
      value_tao: pos.value_tao || pos.stake || 0,
    }
  }).sort((a, b) => (b.value_tao || 0) - (a.value_tao || 0))

  // Calculate daily P&L
  const dailyPnl = portfolio.daily_pnl_tao || 
    enrichedPositions.reduce((sum, p) => {
      const change = p.daily_change_pct || 0
      const value = p.value_tao || 0
      return sum + (value * change / 100)
    }, 0)

  const dailyPnlPct = portfolio.daily_pnl_pct || 
    (totalTao > 0 ? (dailyPnl / totalTao) * 100 : 0)

  const isLoading = portfolioLoading || strategiesLoading || freshnessLoading || profilesLoading

  if (isLoading) {
    return (
      <div className="flex items-center justify-center h-64">
        <div className="animate-spin rounded-full h-8 w-8 border-b-2 border-blue-400"></div>
      </div>
    )
  }

  return (
    <div className="space-y-4 md:space-y-6">
      {/* Header */}
      <div className="flex flex-col sm:flex-row sm:items-center sm:justify-between gap-2">
        <div className="flex items-center gap-3">
          <Activity className="w-6 h-6 md:w-7 md:h-7 text-blue-400" />
          <h1 className="text-xl md:text-2xl font-bold text-white">Track</h1>
        </div>
        <div className="text-xs md:text-sm text-[#6f87a0]">
          Real-time portfolio & strategy tracking
        </div>
      </div>

      {/* Portfolio Overview Card */}
      <div className="bg-[#121f2d] rounded-lg p-4 md:p-6 border border-[#1e3a5f]">
        <div className="flex flex-col sm:flex-row sm:items-center sm:justify-between gap-2 mb-4">
          <div className="flex items-center gap-2">
            <Wallet className="w-5 h-5 text-blue-400" />
            <h2 className="text-base md:text-lg font-semibold text-white">Portfolio Overview</h2>
          </div>
          {portfolioResult?.fetchedAt && (
            <div className="text-xs text-[#6f87a0]">
              Updated {getTimeSince(portfolioResult.fetchedAt)}
            </div>
          )}
        </div>

        <div className="grid grid-cols-1 sm:grid-cols-3 gap-3 md:gap-4">
          <div className="bg-[#0d1117] rounded-lg p-3 md:p-4 border border-[#1e3a5f]/50">
            <div className="text-xs md:text-sm text-[#6f87a0] mb-1">Total TAO</div>
            <div className="text-2xl md:text-3xl font-bold text-white tabular-nums">
              {formatTao(totalTao)}
            </div>
            <div className="text-xs md:text-sm text-[#5a7a94]">τ</div>
          </div>

          <div className="bg-[#0d1117] rounded-lg p-3 md:p-4 border border-[#1e3a5f]/50">
            <div className="text-xs md:text-sm text-[#6f87a0] mb-1">Positions</div>
            <div className="text-2xl md:text-3xl font-bold text-white tabular-nums">
              {positionCount}
            </div>
            <div className="text-xs md:text-sm text-[#5a7a94]">active subnets</div>
          </div>

          <div className="bg-[#0d1117] rounded-lg p-3 md:p-4 border border-[#1e3a5f]/50">
            <div className="text-xs md:text-sm text-[#6f87a0] mb-1">24h P&L</div>
            <div className={`text-2xl md:text-3xl font-bold tabular-nums ${dailyPnl >= 0 ? 'text-green-400' : 'text-red-400'}`}>
              {dailyPnl >= 0 ? '+' : ''}{formatTao(dailyPnl)}
            </div>
            <div className={`text-xs md:text-sm ${dailyPnlPct >= 0 ? 'text-green-400' : 'text-red-400'}`}>
              {formatPercent(dailyPnlPct)}
            </div>
          </div>
        </div>
      </div>

      {/* Current Positions Table */}
      <div className="bg-[#121f2d] rounded-lg p-4 md:p-6 border border-[#1e3a5f]">
        <div className="flex flex-col sm:flex-row sm:items-center sm:justify-between gap-2 mb-4">
          <div className="flex items-center gap-2">
            <BarChart3 className="w-5 h-5 text-blue-400" />
            <h2 className="text-base md:text-lg font-semibold text-white">Current Positions</h2>
          </div>
          <span className="text-xs md:text-sm text-[#6f87a0]">{enrichedPositions.length} positions</span>
        </div>

        {enrichedPositions.length === 0 ? (
          <div className="text-center py-8 text-[#6f87a0]">
            No positions found in portfolio data
          </div>
        ) : (
          <div className="overflow-x-auto -mx-4 md:mx-0 px-4 md:px-0">
            <table className="w-full min-w-[500px]">
              <thead>
                <tr className="text-left text-xs md:text-sm text-[#6f87a0] border-b border-[#1e3a5f]">
                  <th className="pb-3 font-medium">SN#</th>
                  <th className="pb-3 font-medium">Name</th>
                  <th className="pb-3 font-medium text-right">TAO Staked</th>
                  <th className="pb-3 font-medium text-right hidden sm:table-cell">% of Portfolio</th>
                  <th className="pb-3 font-medium text-right">24h Change</th>
                </tr>
              </thead>
              <tbody>
                {enrichedPositions.map((pos) => {
                  const pctOfPortfolio = totalTao > 0 ? ((pos.value_tao || 0) / totalTao) * 100 : 0
                  const dailyChange = pos.daily_change_pct || 0

                  return (
                    <tr key={pos.netuid} className="border-b border-[#1e3a5f]/50 last:border-0">
                      <td className="py-3">
                        <span className="inline-flex items-center justify-center w-7 h-7 md:w-8 md:h-8 rounded bg-[#1a2d42] text-[#8faabe] text-xs md:text-sm font-medium">
                          {pos.netuid}
                        </span>
                      </td>
                      <td className="py-3">
                        <div className="font-medium text-[#a8c4d9] text-sm md:text-base truncate max-w-[120px] md:max-w-none">{pos.name}</div>
                        <div className="text-xs text-[#5a7a94]">{pos.token_symbol || 'SN' + pos.netuid}</div>
                      </td>
                      <td className="py-3 text-right">
                        <div className="font-medium text-white tabular-nums text-sm md:text-base">{formatTao(pos.value_tao || pos.stake || 0)}</div>
                        <div className="text-xs text-[#5a7a94]">τ</div>
                      </td>
                      <td className="py-3 text-right hidden sm:table-cell">
                        <div className="font-medium text-[#8faabe] tabular-nums text-sm md:text-base">{pctOfPortfolio.toFixed(1)}%</div>
                        <div className="w-12 md:w-16 h-1 bg-[#1a2d42] rounded-full mt-1 ml-auto">
                          <div
                            className="h-1 bg-blue-500 rounded-full"
                            style={{ width: `${Math.min(pctOfPortfolio, 100)}%` }}
                          />
                        </div>
                      </td>
                      <td className="py-3 text-right">
                        <div className={`flex items-center justify-end gap-1 ${dailyChange >= 0 ? 'text-green-400' : 'text-red-400'}`}>
                          {dailyChange >= 0 ? <TrendingUp className="w-3 h-3 md:w-4 md:h-4" /> : <TrendingDown className="w-3 h-3 md:w-4 md:h-4" />}
                          <span className="tabular-nums font-medium text-sm md:text-base">{formatPercent(dailyChange)}</span>
                        </div>
                      </td>
                    </tr>
                  )
                })}
              </tbody>
            </table>
          </div>
        )}
      </div>

      {/* Strategy Performance Cards */}
      <div className="bg-[#121f2d] rounded-lg p-4 md:p-6 border border-[#1e3a5f]">
        <div className="flex items-center gap-2 mb-4">
          <TrendingUp className="w-5 h-5 text-blue-400" />
          <h2 className="text-base md:text-lg font-semibold text-white">Strategy Performance</h2>
        </div>

        <div className="grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-3 gap-3 md:gap-4">
          {strategies?.map((strategy) => {
            const config = strategyConfig[strategy.strategy_id] || {
              name: strategy.strategy_id.replace(/_/g, ' ').replace(/\b\w/g, l => l.toUpperCase()),
              color: 'bg-[#1a2d42] text-[#8faabe] border-[#2a4a66]'
            }

            // Parse positions count from notes if available
            let positionsCount = 0
            try {
              if (strategy.notes) {
                const notes = JSON.parse(strategy.notes)
                positionsCount = notes.positions?.length || notes.position_count || 0
              }
            } catch {
              // Notes might not be JSON, ignore
            }

            return (
              <Link
                key={strategy.strategy_id}
                to={`/strategy/${strategy.strategy_id}`}
                className={`rounded-lg p-4 border transition-all hover:opacity-90 ${config.color}`}
              >
                <div className="flex items-center justify-between mb-3">
                  <h3 className="font-semibold">{config.name}</h3>
                  <ArrowRight className="w-4 h-4 opacity-50" />
                </div>

                <div className="space-y-2">
                  <div className="flex items-center justify-between">
                    <span className="text-sm opacity-70">Cumulative Return</span>
                    <span className={`font-bold tabular-nums ${(strategy.cumulative_return_pct || 0) >= 0 ? 'text-green-400' : 'text-red-400'}`}>
                      {formatPercent(strategy.cumulative_return_pct || 0)}
                    </span>
                  </div>

                  <div className="flex items-center justify-between">
                    <span className="text-sm opacity-70">Daily Return</span>
                    <span className={`font-medium tabular-nums ${(strategy.daily_return_pct || 0) >= 0 ? 'text-green-400' : 'text-red-400'}`}>
                      {formatPercent(strategy.daily_return_pct || 0)}
                    </span>
                  </div>

                  <div className="flex items-center justify-between">
                    <span className="text-sm opacity-70">NAV</span>
                    <span className="font-medium tabular-nums">
                      {strategy.nav?.toFixed(4) || '0.0000'} τ
                    </span>
                  </div>

                  {positionsCount > 0 && (
                    <div className="flex items-center justify-between">
                      <span className="text-sm opacity-70">Positions</span>
                      <span className="font-medium">{positionsCount}</span>
                    </div>
                  )}

                  {strategy.max_drawdown_pct !== null && (
                    <div className="flex items-center justify-between">
                      <span className="text-sm opacity-70">Max Drawdown</span>
                      <span className="font-medium tabular-nums text-red-400">
                        {(strategy.max_drawdown_pct || 0).toFixed(2)}%
                      </span>
                    </div>
                  )}
                </div>
              </Link>
            )
          })}
        </div>

        {!strategies?.length && (
          <div className="text-center py-8 text-[#6f87a0]">
            No strategy data available
          </div>
        )}
      </div>

      {/* Data Freshness Section */}
      <div className="bg-[#121f2d] rounded-lg p-4 md:p-6 border border-[#1e3a5f]">
        <div className="flex items-center gap-2 mb-4">
          <Database className="w-5 h-5 text-blue-400" />
          <h2 className="text-base md:text-lg font-semibold text-white">Data Freshness</h2>
        </div>

        <div className="grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-3 gap-3">
          {freshnessData?.map((source) => {
            const lastUpdated = new Date(source.last_updated)
            const now = new Date()
            const diffMinutes = Math.floor((now.getTime() - lastUpdated.getTime()) / (1000 * 60))
            const colorClass = getFreshnessColor(diffMinutes)
            const bgColorClass = getFreshnessBgColor(diffMinutes)

            let StatusIcon = CheckCircle
            if (diffMinutes >= 240) StatusIcon = XCircle
            else if (diffMinutes >= 60) StatusIcon = AlertCircle

            return (
              <div
                key={source.source}
                className={`rounded-lg p-3 border ${bgColorClass}`}
              >
                <div className="flex items-center justify-between mb-2">
                  <span className="font-medium text-sm capitalize">
                    {source.source.replace(/_/g, ' ')}
                  </span>
                  <StatusIcon className={`w-4 h-4 ${colorClass}`} />
                </div>

                <div className="flex items-center gap-1 text-xs opacity-70 mb-1">
                  <Clock className="w-3 h-3" />
                  <span>{getTimeSince(source.last_updated)}</span>
                </div>

                <div className="flex items-center justify-between text-xs">
                  <span className="opacity-60">Records:</span>
                  <span className="font-medium">{source.record_count?.toLocaleString() || 'N/A'}</span>
                </div>

                {source.status && (
                  <div className="flex items-center justify-between text-xs mt-1">
                    <span className="opacity-60">Status:</span>
                    <span className={`capitalize font-medium ${colorClass}`}>{source.status}</span>
                  </div>
                )}
              </div>
            )
          })}
        </div>

        {!freshnessData?.length && (
          <div className="text-center py-8 text-[#6f87a0]">
            No data freshness information available
          </div>
        )}

        {/* Legend */}
        <div className="flex flex-wrap gap-3 md:gap-4 mt-4 pt-4 border-t border-[#1e3a5f]/50">
          <div className="flex items-center gap-2 text-xs text-[#6f87a0]">
            <div className="w-2.5 h-2.5 md:w-3 md:h-3 rounded-full bg-green-600"></div>
            <span>&lt; 1 hour</span>
          </div>
          <div className="flex items-center gap-2 text-xs text-[#6f87a0]">
            <div className="w-2.5 h-2.5 md:w-3 md:h-3 rounded-full bg-yellow-600"></div>
            <span>1-4 hours</span>
          </div>
          <div className="flex items-center gap-2 text-xs text-[#6f87a0]">
            <div className="w-2.5 h-2.5 md:w-3 md:h-3 rounded-full bg-red-600"></div>
            <span>&gt; 4 hours</span>
          </div>
        </div>
      </div>
    </div>
  )
}
