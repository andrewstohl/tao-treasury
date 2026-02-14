import { useMemo } from 'react'
import { useQuery } from '@tanstack/react-query'
import { Wallet, TrendingUp, TrendingDown, Clock, PieChart, BarChart3 } from 'lucide-react'
import { format } from 'date-fns/format'
import { BarChart, Bar, XAxis, YAxis, CartesianGrid, Tooltip, ResponsiveContainer, Cell } from 'recharts'
import { supabaseQueries } from '../services/supabase'

// Types for portfolio data
interface PortfolioPosition {
  netuid: number
  value_tao: number
  pct_of_portfolio: number
}

interface PortfolioData {
  coldkey: string
  total_tao: number
  total_tao_24h: number
  pnl_24h: number
  positions: PortfolioPosition[]
  timestamp: string
}

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

// Color scale for allocation bars
function getAllocationColor(pct: number): string {
  if (pct >= 50) return 'bg-[#2a3ded]'
  if (pct >= 20) return 'bg-blue-500'
  if (pct >= 10) return 'bg-cyan-500'
  if (pct >= 5) return 'bg-teal-500'
  return 'bg-emerald-500'
}

export default function Portfolio() {
  // Fetch portfolio data with auto-refresh every 60 seconds
  const { data: portfolioData, isLoading, error } = useQuery({
    queryKey: ['portfolio-data'],
    queryFn: supabaseQueries.getPortfolioData,
    refetchInterval: 60000, // Auto-refresh every 60 seconds
  })

  // Parse the portfolio data from the response
  const portfolio: PortfolioData | null = useMemo(() => {
    if (!portfolioData?.response) return null
    try {
      return typeof portfolioData.response === 'string' 
        ? JSON.parse(portfolioData.response) 
        : portfolioData.response
    } catch (e) {
      console.error('Failed to parse portfolio data:', e)
      return null
    }
  }, [portfolioData])

  // Sort positions by value descending
  const sortedPositions = useMemo(() => {
    if (!portfolio?.positions) return []
    return [...portfolio.positions].sort((a, b) => b.value_tao - a.value_tao)
  }, [portfolio])

  // Calculate KPIs
  const kpis = useMemo(() => {
    if (!portfolio) return null
    
    const totalValue = portfolio.total_tao || 0
    const pnl24h = portfolio.pnl_24h || 0
    const pnl24hPercent = portfolio.total_tao_24h > 0 
      ? (pnl24h / portfolio.total_tao_24h) * 100 
      : 0
    const positionCount = portfolio.positions?.length || 0
    const largestPosition = sortedPositions[0] || null

    return {
      totalValue,
      pnl24h,
      pnl24hPercent,
      positionCount,
      largestPosition,
    }
  }, [portfolio, sortedPositions])

  // Prepare chart data
  const chartData = useMemo(() => {
    return sortedPositions.map(pos => ({
      name: `SN${pos.netuid}`,
      netuid: pos.netuid,
      value: pos.value_tao,
      percent: pos.pct_of_portfolio,
    }))
  }, [sortedPositions])

  // Custom tooltip for chart
  const CustomTooltip = ({ active, payload }: { active?: boolean; payload?: any[] }) => {
    if (active && payload && payload.length) {
      const data = payload[0].payload
      return (
        <div className="bg-[#16181d] border border-[#2a2f38] rounded-lg p-3 shadow-lg">
          <p className="text-white font-medium">{data.name}</p>
          <p className="text-[#9ca3af] text-sm">
            Value: <span className="text-white tabular-nums">{data.value.toFixed(4)} τ</span>
          </p>
          <p className="text-[#9ca3af] text-sm">
            Allocation: <span className="text-white tabular-nums">{data.percent.toFixed(1)}%</span>
          </p>
        </div>
      )
    }
    return null
  }

  return (
    <div className="space-y-6">
      {/* Header */}
      <div className="flex items-center justify-between">
        <div>
          <h1 className="text-2xl font-bold text-[#2a3ded] flex items-center gap-2">
            <Wallet className="w-6 h-6" />
            Portfolio
          </h1>
          <p className="text-sm text-[#8a8f98] mt-1">
            Real-time portfolio positions and allocation breakdown
          </p>
        </div>
        <div className="flex items-center gap-4">
          {portfolioData?.fetched_at && (
            <div className="flex items-center gap-2 text-xs text-[#6b7280]">
              <Clock className="w-3 h-3" />
              <span>Updated {formatRelativeTime(portfolioData.fetched_at)}</span>
            </div>
          )}
          <div className="flex items-center gap-2">
            <div className="w-2 h-2 rounded-full bg-green-500 animate-pulse" />
            <span className="text-xs text-[#6b7280]">Live</span>
          </div>
        </div>
      </div>

      {/* Error State */}
      {error && (
        <div className="bg-red-900/30 border border-red-700 rounded-lg p-4">
          <div className="flex items-center gap-2 text-red-400">
            <TrendingDown className="w-5 h-5" />
            <span className="font-medium">Failed to load portfolio data</span>
          </div>
          <p className="text-sm text-red-300/70 mt-1">{error.message}</p>
        </div>
      )}

      {/* KPI Cards */}
      <div className="grid grid-cols-2 md:grid-cols-4 gap-4">
        {/* Total Value */}
        <div className="bg-[#16181d] rounded-lg border border-[#2a2f38] p-4">
          <div className="flex items-center gap-2 mb-2">
            <Wallet className="w-4 h-4 text-[#2a3ded]" />
            <span className="text-xs text-[#6b7280]">Total Value</span>
          </div>
          {isLoading ? (
            <div className="h-6 bg-[#1e2128] rounded animate-pulse" />
          ) : (
            <div className="text-xl font-bold text-white tabular-nums">
              {kpis?.totalValue.toLocaleString(undefined, { minimumFractionDigits: 2, maximumFractionDigits: 2 })} τ
            </div>
          )}
        </div>

        {/* 24h P&L */}
        <div className="bg-[#16181d] rounded-lg border border-[#2a2f38] p-4">
          <div className="flex items-center gap-2 mb-2">
            {kpis && kpis.pnl24h >= 0 ? (
              <TrendingUp className="w-4 h-4 text-green-400" />
            ) : (
              <TrendingDown className="w-4 h-4 text-red-400" />
            )}
            <span className="text-xs text-[#6b7280]">24h P&L</span>
          </div>
          {isLoading ? (
            <div className="h-6 bg-[#1e2128] rounded animate-pulse" />
          ) : (
            <div className="space-y-1">
              <div className={`text-xl font-bold tabular-nums ${kpis && kpis.pnl24h >= 0 ? 'text-green-400' : 'text-red-400'}`}>
                {kpis && kpis.pnl24h >= 0 ? '+' : ''}{kpis?.pnl24h.toFixed(4)} τ
              </div>
              <div className={`text-xs tabular-nums ${kpis && kpis.pnl24hPercent >= 0 ? 'text-green-400/70' : 'text-red-400/70'}`}>
                {kpis && kpis.pnl24hPercent >= 0 ? '+' : ''}{kpis?.pnl24hPercent.toFixed(2)}%
              </div>
            </div>
          )}
        </div>

        {/* # Positions */}
        <div className="bg-[#16181d] rounded-lg border border-[#2a2f38] p-4">
          <div className="flex items-center gap-2 mb-2">
            <BarChart3 className="w-4 h-4 text-[#2a3ded]" />
            <span className="text-xs text-[#6b7280]">Positions</span>
          </div>
          {isLoading ? (
            <div className="h-6 bg-[#1e2128] rounded animate-pulse" />
          ) : (
            <div className="text-xl font-bold text-white tabular-nums">
              {kpis?.positionCount || 0}
            </div>
          )}
        </div>

        {/* Largest Position */}
        <div className="bg-[#16181d] rounded-lg border border-[#2a2f38] p-4">
          <div className="flex items-center gap-2 mb-2">
            <PieChart className="w-4 h-4 text-[#2a3ded]" />
            <span className="text-xs text-[#6b7280]">Largest Position</span>
          </div>
          {isLoading ? (
            <div className="h-6 bg-[#1e2128] rounded animate-pulse" />
          ) : kpis?.largestPosition ? (
            <div className="space-y-1">
              <div className="text-xl font-bold text-white tabular-nums">
                SN{kpis.largestPosition.netuid}
              </div>
              <div className="text-xs text-[#6b7280] tabular-nums">
                {kpis.largestPosition.pct_of_portfolio.toFixed(1)}% of portfolio
              </div>
            </div>
          ) : (
            <div className="text-xl font-bold text-white tabular-nums">—</div>
          )}
        </div>
      </div>

      {/* Main Content: Chart + Positions Table */}
      <div className="grid grid-cols-1 lg:grid-cols-2 gap-6">
        {/* Allocation Chart */}
        <div className="bg-[#16181d] rounded-lg border border-[#2a2f38] p-5">
          <div className="flex items-center justify-between mb-4">
            <div className="flex items-center gap-2">
              <PieChart className="w-5 h-5 text-[#2a3ded]" />
              <h3 className="font-semibold text-white">Allocation</h3>
            </div>
            <span className="text-xs text-[#6b7280]">By Value</span>
          </div>

          {isLoading ? (
            <div className="h-64 bg-[#1e2128] rounded animate-pulse" />
          ) : chartData.length > 0 ? (
            <div className="h-64">
              <ResponsiveContainer width="100%" height="100%">
                <BarChart data={chartData} layout="vertical" margin={{ top: 5, right: 30, left: 40, bottom: 5 }}>
                  <CartesianGrid strokeDasharray="3 3" stroke="#2a2f38" horizontal={false} />
                  <XAxis 
                    type="number" 
                    stroke="#6b7280" 
                    fontSize={11}
                    tickFormatter={(value) => `${value.toFixed(0)} τ`}
                  />
                  <YAxis 
                    type="category" 
                    dataKey="name" 
                    stroke="#9ca3af" 
                    fontSize={12}
                    width={50}
                  />
                  <Tooltip content={<CustomTooltip />} />
                  <Bar dataKey="value" radius={[0, 4, 4, 0]}>
                    {chartData.map((_entry, index) => (
                      <Cell 
                        key={`cell-${index}`} 
                        fill={index === 0 ? '#2a3ded' : index === 1 ? '#3b82f6' : index === 2 ? '#06b6d4' : index === 3 ? '#14b8a6' : '#10b981'}
                      />
                    ))}
                  </Bar>
                </BarChart>
              </ResponsiveContainer>
            </div>
          ) : (
            <div className="h-64 flex items-center justify-center text-[#6b7280]">
              <span>No position data available</span>
            </div>
          )}
        </div>

        {/* Positions Table */}
        <div className="bg-[#16181d] rounded-lg border border-[#2a2f38] p-5">
          <div className="flex items-center justify-between mb-4">
            <div className="flex items-center gap-2">
              <BarChart3 className="w-5 h-5 text-[#2a3ded]" />
              <h3 className="font-semibold text-white">Positions</h3>
            </div>
            <span className="text-xs text-[#6b7280]">Sorted by Value</span>
          </div>

          {isLoading ? (
            <div className="space-y-2">
              {[1, 2, 3, 4, 5].map((i) => (
                <div key={i} className="h-12 bg-[#1e2128] rounded animate-pulse" />
              ))}
            </div>
          ) : sortedPositions.length > 0 ? (
            <div className="space-y-2 max-h-[300px] overflow-y-auto">
              {/* Table Header */}
              <div className="grid grid-cols-12 gap-2 text-xs text-[#6b7280] pb-2 border-b border-[#2a2f38]">
                <div className="col-span-2">Subnet</div>
                <div className="col-span-4">Allocation</div>
                <div className="col-span-3 text-right">Value</div>
                <div className="col-span-3 text-right">%</div>
              </div>

              {/* Table Rows */}
              {sortedPositions.map((position) => (
                <div 
                  key={position.netuid} 
                  className="grid grid-cols-12 gap-2 py-2 items-center hover:bg-[#1e2128] rounded px-1 transition-colors"
                >
                  <div className="col-span-2">
                    <span className="text-sm font-medium text-white">
                      SN{position.netuid}
                    </span>
                  </div>
                  <div className="col-span-4">
                    <div className="flex items-center gap-2">
                      <div className="flex-1 h-2 bg-[#1e2128] rounded-full overflow-hidden">
                        <div 
                          className={`h-full rounded-full ${getAllocationColor(position.pct_of_portfolio)}`}
                          style={{ width: `${Math.min(position.pct_of_portfolio, 100)}%` }}
                        />
                      </div>
                    </div>
                  </div>
                  <div className="col-span-3 text-right">
                    <span className="text-sm text-white tabular-nums">
                      {position.value_tao.toLocaleString(undefined, { minimumFractionDigits: 2, maximumFractionDigits: 4 })}
                    </span>
                    <span className="text-xs text-[#6b7280] ml-1">τ</span>
                  </div>
                  <div className="col-span-3 text-right">
                    <span className={`text-sm font-medium tabular-nums ${
                      position.pct_of_portfolio >= 50 ? 'text-[#2a3ded]' :
                      position.pct_of_portfolio >= 20 ? 'text-blue-400' :
                      position.pct_of_portfolio >= 10 ? 'text-cyan-400' :
                      'text-emerald-400'
                    }`}>
                      {position.pct_of_portfolio.toFixed(1)}%
                    </span>
                  </div>
                </div>
              ))}
            </div>
          ) : (
            <div className="text-center py-8 text-[#6b7280]">
              <BarChart3 className="w-8 h-8 mx-auto mb-2 opacity-50" />
              <span className="text-sm">No positions found</span>
            </div>
          )}

          {/* Coldkey info */}
          {portfolio?.coldkey && (
            <div className="mt-4 pt-4 border-t border-[#2a2f38]">
              <div className="text-xs text-[#6b7280]">Coldkey</div>
              <div className="text-xs text-[#9ca3af] font-mono mt-1 truncate" title={portfolio.coldkey}>
                {portfolio.coldkey}
              </div>
            </div>
          )}
        </div>
      </div>

      {/* Raw Data Timestamp */}
      {portfolio?.timestamp && (
        <div className="text-center text-xs text-[#6b7280]">
          Data sourced at {format(new Date(portfolio.timestamp), 'MMM d, yyyy HH:mm:ss')} UTC
        </div>
      )}
    </div>
  )
}
