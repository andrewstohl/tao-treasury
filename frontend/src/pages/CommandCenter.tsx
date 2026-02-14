import { useMemo } from 'react'
import { useQuery } from '@tanstack/react-query'
import {
  Activity,
  AlertTriangle,
  TrendingUp,
  TrendingDown,
  Database,
  Server,
  Clock,
  Shield,
  ChevronRight,
  Zap,
  BarChart3,
  Layers,
  ArrowUpRight,
  ArrowDownRight,
} from 'lucide-react'
import { format } from 'date-fns'
import { supabaseQueries, type StrategyLedger, type AgentHeartbeat, type DataFreshness, type Escalation, type SubnetProfile } from '../services/supabase'

// Format relative time
function formatRelativeTime(dateString: string | null): string {
  if (!dateString) return 'Never'
  const date = new Date(dateString)
  const now = new Date()
  const diffMs = now.getTime() - date.getTime()
  const diffMins = Math.floor(diffMs / 60000)

  if (diffMins < 1) return 'Just now'
  if (diffMins === 1) return '1 min ago'
  if (diffMins < 60) return `${diffMins} mins ago`

  const diffHours = Math.floor(diffMins / 60)
  if (diffHours === 1) return '1 hour ago'
  if (diffHours < 24) return `${diffHours} hours ago`

  const diffDays = Math.floor(diffHours / 24)
  if (diffDays === 1) return '1 day ago'
  if (diffDays < 7) return `${diffDays} days ago`

  return format(date, 'MMM d, yyyy')
}

// Format staleness
function formatStaleness(minutes: number): { text: string; color: string } {
  if (minutes < 5) return { text: 'Fresh', color: 'text-green-400' }
  if (minutes < 15) return { text: 'Recent', color: 'text-blue-400' }
  if (minutes < 60) return { text: `${minutes}m stale`, color: 'text-yellow-400' }
  if (minutes < 1440) return { text: `${Math.floor(minutes / 60)}h stale`, color: 'text-orange-400' }
  return { text: `${Math.floor(minutes / 1440)}d stale`, color: 'text-red-400' }
}

// Get status color
function getStatusColor(status: string): string {
  switch (status.toLowerCase()) {
    case 'healthy':
      return 'bg-green-500'
    case 'degraded':
      return 'bg-yellow-500'
    case 'error':
      return 'bg-red-500'
    case 'stopped':
      return 'bg-gray-500'
    default:
      return 'bg-blue-500'
  }
}

// Strategy display names
const STRATEGY_DISPLAY_NAMES: Record<string, string> = {
  bedrock: 'Bedrock',
  yield_hunter: 'Sharpe Hunter',
  contrarian: 'Vol-Targeted',
}

// Get severity styles
function getSeverityStyles(severity: string): { bg: string; text: string; border: string } {
  switch (severity.toLowerCase()) {
    case 'critical':
      return { bg: 'bg-red-900/30', text: 'text-red-400', border: 'border-red-700' }
    case 'high':
      return { bg: 'bg-orange-900/30', text: 'text-orange-400', border: 'border-orange-700' }
    case 'medium':
      return { bg: 'bg-yellow-900/30', text: 'text-yellow-400', border: 'border-yellow-700' }
    default:
      return { bg: 'bg-blue-900/30', text: 'text-blue-400', border: 'border-blue-700' }
  }
}

export default function CommandCenter() {
  // Fetch data using TanStack Query
  const { data: latestNavData, isLoading: isLoadingNav } = useQuery({
    queryKey: ['supabase-latest-nav'],
    queryFn: supabaseQueries.getLatestNAVByStrategy,
    refetchInterval: 60000,
  })

  const { data: agentHeartbeats, isLoading: isLoadingAgents } = useQuery({
    queryKey: ['supabase-agent-heartbeats'],
    queryFn: supabaseQueries.getAgentHeartbeats,
    refetchInterval: 30000,
  })

  const { data: dataFreshness, isLoading: isLoadingFreshness } = useQuery({
    queryKey: ['supabase-data-freshness'],
    queryFn: supabaseQueries.getDataFreshness,
    refetchInterval: 60000,
  })

  const { data: escalations, isLoading: isLoadingEscalations } = useQuery({
    queryKey: ['supabase-escalations'],
    queryFn: () => supabaseQueries.getRecentEscalations(10),
    refetchInterval: 30000,
  })

  const { data: subnetProfiles, isLoading: isLoadingSubnets } = useQuery({
    queryKey: ['supabase-subnet-profiles'],
    queryFn: supabaseQueries.getSubnetProfiles,
    refetchInterval: 60000,
  })

  // Calculate total NAV
  const totalNav = useMemo(() => {
    if (!latestNavData) return 0
    return latestNavData.reduce((sum, item) => sum + (item.nav || 0), 0)
  }, [latestNavData])

  // Calculate avg daily return (values are already in percentage form)
  const avgDailyReturn = useMemo(() => {
    if (!latestNavData || latestNavData.length === 0) return 0
    const sum = latestNavData.reduce((acc, item) => acc + (item.daily_return_pct || 0), 0)
    return sum / latestNavData.length
  }, [latestNavData])

  // Calculate daily P&L
  const dailyPnL = useMemo(() => {
    if (!latestNavData || latestNavData.length === 0) return 0
    const totalNav = latestNavData.reduce((sum, item) => sum + (item.nav || 0), 0)
    const weightedReturn = latestNavData.reduce((sum, item) => {
      const weight = totalNav > 0 ? (item.nav || 0) / totalNav : 0
      return sum + weight * (item.daily_return_pct || 0)
    }, 0)
    return (weightedReturn / 100) * totalNav // Convert % to absolute τ
  }, [latestNavData])

  // Count positions (from latest ledger entries with notes containing positions)
  const positionsCount = useMemo(() => {
    // This would ideally come from strategy_ledger with position data
    // For now, we'll estimate based on subnet profiles or return 0
    return 0
  }, [latestNavData])

  // Best and worst performing subnets today
  const subnetPerformance = useMemo(() => {
    if (!subnetProfiles || subnetProfiles.length === 0) return { best: null, worst: null }
    
    const sorted = [...subnetProfiles]
      .filter(s => s.daily_return_pct !== null)
      .sort((a, b) => (b.daily_return_pct || 0) - (a.daily_return_pct || 0))
    
    return {
      best: sorted[0] || null,
      worst: sorted[sorted.length - 1] || null,
    }
  }, [subnetProfiles])

  return (
    <div className="space-y-6">
      {/* Header */}
      <div className="flex items-center justify-between">
        <div>
          <h1 className="text-2xl font-bold text-[#2a3ded] flex items-center gap-2">
            <Shield className="w-6 h-6" />
            Command Center
          </h1>
          <p className="text-sm text-[#8a8f98] mt-1">
            Fund operations dashboard — real-time health monitoring and NAV tracking
          </p>
        </div>
        <div className="flex items-center gap-2">
          <div className="w-2 h-2 rounded-full bg-green-500 animate-pulse" />
          <span className="text-xs text-[#6b7280]">Live</span>
        </div>
      </div>

      {/* Quick Stats Row */}
      <div className="grid grid-cols-2 md:grid-cols-4 gap-4">
        <div className="bg-[#16181d] rounded-lg border border-[#2a2f38] p-4">
          <div className="flex items-center gap-2 mb-2">
            <BarChart3 className="w-4 h-4 text-[#2a3ded]" />
            <span className="text-xs text-[#6b7280]">Total NAV</span>
          </div>
          {isLoadingNav ? (
            <div className="h-6 bg-[#1e2128] rounded animate-pulse" />
          ) : (
            <div className="text-xl font-bold text-white tabular-nums">
              {totalNav.toLocaleString(undefined, { minimumFractionDigits: 2, maximumFractionDigits: 2 })} τ
            </div>
          )}
        </div>

        <div className="bg-[#16181d] rounded-lg border border-[#2a2f38] p-4">
          <div className="flex items-center gap-2 mb-2">
            <Zap className="w-4 h-4 text-[#2a3ded]" />
            <span className="text-xs text-[#6b7280]">Daily P&L</span>
          </div>
          {isLoadingNav ? (
            <div className="h-6 bg-[#1e2128] rounded animate-pulse" />
          ) : (
            <div className={`text-xl font-bold tabular-nums ${dailyPnL >= 0 ? 'text-green-400' : 'text-red-400'}`}>
              {dailyPnL >= 0 ? '+' : ''}{dailyPnL.toFixed(4)} τ
            </div>
          )}
        </div>

        <div className="bg-[#16181d] rounded-lg border border-[#2a2f38] p-4">
          <div className="flex items-center gap-2 mb-2">
            <Layers className="w-4 h-4 text-[#2a3ded]" />
            <span className="text-xs text-[#6b7280]">Strategies</span>
          </div>
          {isLoadingNav ? (
            <div className="h-6 bg-[#1e2128] rounded animate-pulse" />
          ) : (
            <div className="text-xl font-bold text-white tabular-nums">
              {latestNavData?.length || 0}
            </div>
          )}
        </div>

        <div className="bg-[#16181d] rounded-lg border border-[#2a2f38] p-4">
          <div className="flex items-center gap-2 mb-2">
            <TrendingUp className="w-4 h-4 text-[#2a3ded]" />
            <span className="text-xs text-[#6b7280]">Avg Return</span>
          </div>
          {isLoadingNav ? (
            <div className="h-6 bg-[#1e2128] rounded animate-pulse" />
          ) : (
            <div className={`text-xl font-bold tabular-nums ${avgDailyReturn >= 0 ? 'text-green-400' : 'text-red-400'}`}>
              {avgDailyReturn >= 0 ? '+' : ''}{avgDailyReturn.toFixed(2)}%
            </div>
          )}
        </div>
      </div>

      {/* Top Row: Portfolio + Agent Health + Data Freshness */}
      <div className="grid grid-cols-1 lg:grid-cols-3 gap-4">
        {/* Portfolio NAV Card with Subnet Performance */}
        <div className="bg-[#16181d] rounded-lg border border-[#2a2f38] p-5">
          <div className="flex items-center justify-between mb-4">
            <div className="flex items-center gap-2">
              <TrendingUp className="w-5 h-5 text-[#2a3ded]" />
              <h3 className="font-semibold text-white">Portfolio</h3>
            </div>
            <span className="text-xs text-[#6b7280]">Real-time</span>
          </div>
          
          {isLoadingNav ? (
            <div className="animate-pulse space-y-2">
              <div className="h-10 bg-[#1e2128] rounded w-32" />
              <div className="h-4 bg-[#1e2128] rounded w-24" />
            </div>
          ) : (
            <>
              <div className="text-3xl font-bold text-white tabular-nums">
                {totalNav.toLocaleString(undefined, { minimumFractionDigits: 2, maximumFractionDigits: 2 })} τ
              </div>
              <div className="flex items-center gap-2 mt-1">
                <span className={`text-sm ${avgDailyReturn >= 0 ? 'text-green-400' : 'text-red-400'}`}>
                  {avgDailyReturn >= 0 ? '+' : ''}{avgDailyReturn.toFixed(2)}%
                </span>
                <span className="text-xs text-[#6b7280]">24h</span>
              </div>
            </>
          )}

          {/* Best/Worst Subnets */}
          <div className="mt-4 pt-4 border-t border-[#2a2f38]">
            <div className="text-xs text-[#6b7280] mb-3">Subnet Performance Today</div>
            
            {isLoadingSubnets ? (
              <div className="space-y-2">
                <div className="h-8 bg-[#1e2128] rounded animate-pulse" />
                <div className="h-8 bg-[#1e2128] rounded animate-pulse" />
              </div>
            ) : (
              <div className="space-y-2">
                {/* Best Performer */}
                {subnetPerformance.best && (
                  <div className="flex items-center justify-between p-2 bg-green-500/10 rounded border border-green-500/20">
                    <div className="flex items-center gap-2">
                      <ArrowUpRight className="w-4 h-4 text-green-400" />
                      <div>
                        <span className="text-sm text-white">SN{subnetPerformance.best.netuid}</span>
                        <span className="text-xs text-[#6b7280] ml-2">
                          {subnetPerformance.best.subnet_name || 'Unknown'}
                        </span>
                      </div>
                    </div>
                    <span className="text-sm font-medium text-green-400 tabular-nums">
                      +{(subnetPerformance.best.daily_return_pct || 0).toFixed(2)}%
                    </span>
                  </div>
                )}
                
                {/* Worst Performer */}
                {subnetPerformance.worst && (
                  <div className="flex items-center justify-between p-2 bg-red-500/10 rounded border border-red-500/20">
                    <div className="flex items-center gap-2">
                      <ArrowDownRight className="w-4 h-4 text-red-400" />
                      <div>
                        <span className="text-sm text-white">SN{subnetPerformance.worst.netuid}</span>
                        <span className="text-xs text-[#6b7280] ml-2">
                          {subnetPerformance.worst.subnet_name || 'Unknown'}
                        </span>
                      </div>
                    </div>
                    <span className="text-sm font-medium text-red-400 tabular-nums">
                      {(subnetPerformance.worst.daily_return_pct || 0).toFixed(2)}%
                    </span>
                  </div>
                )}
                
                {!subnetPerformance.best && !subnetPerformance.worst && (
                  <span className="text-xs text-[#6b7280]">No subnet data available</span>
                )}
              </div>
            )}
          </div>

          {/* Strategy breakdown */}
          <div className="mt-4 pt-4 border-t border-[#2a2f38]">
            <div className="text-xs text-[#6b7280] mb-2">Strategies</div>
            <div className="space-y-2">
              {latestNavData?.slice(0, 5).map((item) => (
                <div key={item.strategy_id} className="flex items-center justify-between text-sm">
                  <span className="text-[#9ca3af] truncate max-w-[120px]">
                    {STRATEGY_DISPLAY_NAMES[item.strategy_id] || item.strategy_id}
                  </span>
                  <span className="text-white tabular-nums">{item.nav?.toFixed(2)} τ</span>
                </div>
              ))}
              {(!latestNavData || latestNavData.length === 0) && !isLoadingNav && (
                <span className="text-xs text-[#6b7280]">No data available</span>
              )}
            </div>
          </div>
        </div>

        {/* Agent Health Panel */}
        <div className="bg-[#16181d] rounded-lg border border-[#2a2f38] p-5">
          <div className="flex items-center justify-between mb-4">
            <div className="flex items-center gap-2">
              <Server className="w-5 h-5 text-[#2a3ded]" />
              <h3 className="font-semibold text-white">Agent Health</h3>
            </div>
            <span className="text-xs text-[#6b7280]">{agentHeartbeats?.length || 0} agents</span>
          </div>

          {isLoadingAgents ? (
            <div className="space-y-2">
              {[1, 2, 3].map((i) => (
                <div key={i} className="h-12 bg-[#1e2128] rounded animate-pulse" />
              ))}
            </div>
          ) : (
            <div className="space-y-2 max-h-[200px] overflow-y-auto">
              {agentHeartbeats?.map((agent) => (
                <div key={agent.agent_id} className="flex items-center justify-between p-2 bg-[#0d0f12] rounded">
                  <div className="flex items-center gap-2">
                    <div className={`w-2 h-2 rounded-full ${getStatusColor(agent.status)}`} />
                    <span className="text-sm text-[#9ca3af] truncate max-w-[100px]">{agent.agent_id}</span>
                  </div>
                  <div className="text-right">
                    <span className={`text-xs px-2 py-0.5 rounded ${
                      agent.status === 'healthy' ? 'bg-green-900/30 text-green-400' :
                      agent.status === 'degraded' ? 'bg-yellow-900/30 text-yellow-400' :
                      agent.status === 'error' ? 'bg-red-900/30 text-red-400' :
                      'bg-gray-900/30 text-gray-400'
                    }`}>
                      {agent.status}
                    </span>
                    <div className="text-xs text-[#6b7280] mt-0.5">
                      {formatRelativeTime(agent.last_run)}
                    </div>
                  </div>
                </div>
              ))}
              {(!agentHeartbeats || agentHeartbeats.length === 0) && !isLoadingAgents && (
                <div className="text-center py-4 text-xs text-[#6b7280]">No agents registered</div>
              )}
            </div>
          )}
        </div>

        {/* Data Freshness Panel */}
        <div className="bg-[#16181d] rounded-lg border border-[#2a2f38] p-5">
          <div className="flex items-center justify-between mb-4">
            <div className="flex items-center gap-2">
              <Database className="w-5 h-5 text-[#2a3ded]" />
              <h3 className="font-semibold text-white">Data Freshness</h3>
            </div>
            <Clock className="w-4 h-4 text-[#6b7280]" />
          </div>

          {isLoadingFreshness ? (
            <div className="space-y-2">
              {[1, 2, 3, 4].map((i) => (
                <div key={i} className="h-10 bg-[#1e2128] rounded animate-pulse" />
              ))}
            </div>
          ) : (
            <div className="space-y-2 max-h-[200px] overflow-y-auto">
              {dataFreshness?.map((source) => {
                const minutesAgo = Math.floor((Date.now() - new Date(source.last_updated).getTime()) / 60000)
                const staleness = formatStaleness(minutesAgo)
                const isStale = minutesAgo > source.threshold_minutes
                
                return (
                  <div key={source.source} className="flex items-center justify-between p-2 bg-[#0d0f12] rounded">
                    <div>
                      <span className="text-sm text-[#9ca3af]">{source.source}</span>
                      <div className="text-xs text-[#6b7280]">
                        {source.record_count.toLocaleString()} records
                      </div>
                    </div>
                    <div className="text-right">
                      <span className={`text-xs font-medium ${staleness.color}`}>
                        {staleness.text}
                      </span>
                      {isStale && (
                        <div className="text-xs text-red-400">Threshold exceeded</div>
                      )}
                    </div>
                  </div>
                )
              })}
              {(!dataFreshness || dataFreshness.length === 0) && !isLoadingFreshness && (
                <div className="text-center py-4 text-xs text-[#6b7280]">No data sources tracked</div>
              )}
            </div>
          )}
        </div>
      </div>

      {/* Bottom Row: Recent Escalations + Strategy Scores */}
      <div className="grid grid-cols-1 lg:grid-cols-2 gap-4">
        {/* Recent Escalations */}
        <div className="bg-[#16181d] rounded-lg border border-[#2a2f38] p-5">
          <div className="flex items-center justify-between mb-4">
            <div className="flex items-center gap-2">
              <AlertTriangle className="w-5 h-5 text-[#2a3ded]" />
              <h3 className="font-semibold text-white">Recent Escalations</h3>
            </div>
            <span className="text-xs text-[#6b7280]">Last 10</span>
          </div>

          {isLoadingEscalations ? (
            <div className="space-y-2">
              {[1, 2, 3].map((i) => (
                <div key={i} className="h-16 bg-[#1e2128] rounded animate-pulse" />
              ))}
            </div>
          ) : (
            <div className="space-y-2 max-h-[300px] overflow-y-auto">
              {escalations?.map((esc) => {
                const styles = getSeverityStyles(esc.severity)
                return (
                  <div key={`${esc.agent_id}-${esc.created_at}`} className={`p-3 rounded border ${styles.border} ${styles.bg}`}>
                    <div className="flex items-start justify-between gap-2">
                      <div>
                        <div className="flex items-center gap-2">
                          <span className={`text-xs font-semibold uppercase ${styles.text}`}>
                            {esc.severity}
                          </span>
                          <span className="text-xs text-[#6b7280]">
                            {formatRelativeTime(esc.created_at)}
                          </span>
                        </div>
                        <div className="text-sm font-medium text-white mt-1">{esc.title}</div>
                        <div className="text-xs text-[#9ca3af] mt-0.5">{esc.agent_id}</div>
                      </div>
                    </div>
                    {esc.details && (
                      <div className="text-xs text-[#8a8f98] mt-2 line-clamp-2">{esc.details}</div>
                    )}
                  </div>
                )
              })}
              {(!escalations || escalations.length === 0) && !isLoadingEscalations && (
                <div className="flex items-center justify-center py-8 text-[#6b7280]">
                  <Activity className="w-5 h-5 mr-2" />
                  <span className="text-sm">No recent escalations</span>
                </div>
              )}
            </div>
          )}
        </div>

        {/* Strategy Scores Summary */}
        <div className="bg-[#16181d] rounded-lg border border-[#2a2f38] p-5">
          <div className="flex items-center justify-between mb-4">
            <div className="flex items-center gap-2">
              <Activity className="w-5 h-5 text-[#2a3ded]" />
              <h3 className="font-semibold text-white">Strategy SN88 Scores</h3>
            </div>
            <span className="text-xs text-[#6b7280]">Latest estimates</span>
          </div>

          {isLoadingNav ? (
            <div className="space-y-2">
              {[1, 2, 3, 4].map((i) => (
                <div key={i} className="h-12 bg-[#1e2128] rounded animate-pulse" />
              ))}
            </div>
          ) : (
            <div className="space-y-2">
              {latestNavData?.map((item) => {
                const score = item.sn88_score || 0
                let scoreColor = 'text-red-400'
                if (score >= 70) scoreColor = 'text-green-400'
                else if (score >= 50) scoreColor = 'text-yellow-400'
                else if (score >= 30) scoreColor = 'text-orange-400'

                return (
                  <div key={item.strategy_id} className="flex items-center justify-between p-3 bg-[#0d0f12] rounded">
                    <div className="flex items-center gap-3">
                      <div className="w-8 h-8 rounded-full bg-[#1e2128] flex items-center justify-center text-xs font-bold text-[#9ca3af]">
                        {item.strategy_id.slice(0, 2).toUpperCase()}
                      </div>
                      <div>
                        <div className="text-sm font-medium text-white">
                          {STRATEGY_DISPLAY_NAMES[item.strategy_id] || item.strategy_id}
                        </div>
                        <div className="text-xs text-[#6b7280]">
                          Return: {(item.daily_return_pct || 0).toFixed(2)}% | DD: {(item.max_drawdown_pct || 0).toFixed(2)}%
                        </div>
                      </div>
                    </div>
                    <div className="text-right">
                      <div className={`text-lg font-bold tabular-nums ${scoreColor}`}>
                        {score.toFixed(1)}
                      </div>
                      <div className="text-xs text-[#6b7280]">SN88 Score</div>
                    </div>
                  </div>
                )
              })}
              {(!latestNavData || latestNavData.length === 0) && !isLoadingNav && (
                <div className="text-center py-8 text-[#6b7280]">
                  <Activity className="w-5 h-5 mx-auto mb-2" />
                  <span className="text-sm">No strategy data available</span>
                </div>
              )}
            </div>
          )}

          <div className="mt-4 pt-4 border-t border-[#2a2f38]">
            <div className="flex items-center justify-between text-xs text-[#6b7280]">
              <span>Score Range</span>
              <span>0-100 (higher is better)</span>
            </div>
            <div className="flex gap-1 mt-2">
              <div className="flex-1 h-1 bg-red-500 rounded-l" />
              <div className="flex-1 h-1 bg-orange-500" />
              <div className="flex-1 h-1 bg-yellow-500" />
              <div className="flex-1 h-1 bg-green-500 rounded-r" />
            </div>
            <div className="flex justify-between text-xs text-[#6b7280] mt-1">
              <span>0</span>
              <span>50</span>
              <span>100</span>
            </div>
          </div>
        </div>
      </div>
    </div>
  )
}
