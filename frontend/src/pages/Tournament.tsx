import { useState, useMemo } from 'react'
import { useQuery } from '@tanstack/react-query'
import {
  LineChart,
  Line,
  XAxis,
  YAxis,
  Tooltip,
  ResponsiveContainer,
  Legend,
  CartesianGrid,
} from 'recharts'
import {
  Trophy,
  TrendingUp,
  TrendingDown,
  Calendar,
  BarChart3,
  Target,
  Activity,
} from 'lucide-react'
import { format, parseISO, subDays } from 'date-fns'
import { supabaseQueries, type StrategyLedger } from '../services/supabase'

// Color palette for strategies
const STRATEGY_COLORS = [
  '#2a3ded', // Primary blue
  '#10b981', // Emerald
  '#f59e0b', // Amber
  '#ef4444', // Red
  '#8b5cf6', // Violet
  '#06b6d4', // Cyan
  '#ec4899', // Pink
  '#84cc16', // Lime
]

// Calculate Sharpe ratio from returns
function calculateSharpe(returns: number[]): number {
  if (returns.length < 2) return 0
  const avg = returns.reduce((a, b) => a + b, 0) / returns.length
  const variance = returns.reduce((sum, r) => sum + Math.pow(r - avg, 2), 0) / (returns.length - 1)
  const stdDev = Math.sqrt(variance)
  return stdDev === 0 ? 0 : (avg / stdDev) * Math.sqrt(365) // Annualized
}

// Strategy display names
const STRATEGY_DISPLAY_NAMES: Record<string, string> = {
  bedrock: 'Bedrock',
  yield_hunter: 'Sharpe Hunter',
  contrarian: 'Vol-Targeted',
}

// Format percentage (values already in percentage form, e.g., 0.43 means 0.43%)
function formatPct(value: number): string {
  return `${value.toFixed(2)}%`
}

export default function Tournament() {
  const [dateRange, setDateRange] = useState<'7d' | '30d' | '90d' | '1y' | 'all'>('30d')
  const [selectedStrategies, setSelectedStrategies] = useState<string[]>([])

  // Calculate date range
  const startDate = useMemo(() => {
    const now = new Date()
    switch (dateRange) {
      case '7d':
        return subDays(now, 7)
      case '30d':
        return subDays(now, 30)
      case '90d':
        return subDays(now, 90)
      case '1y':
        return subDays(now, 365)
      default:
        return null
    }
  }, [dateRange])

  // Fetch historical data
  const { data: historyData, isLoading: isLoadingHistory } = useQuery({
    queryKey: ['supabase-strategy-history', dateRange],
    queryFn: () => supabaseQueries.getStrategyHistory(
      undefined,
      startDate?.toISOString().split('T')[0],
      undefined
    ),
    refetchInterval: 60000,
  })

  // Fetch latest comparison data
  const { data: comparisonData, isLoading: isLoadingComparison } = useQuery({
    queryKey: ['supabase-strategy-comparison'],
    queryFn: supabaseQueries.getStrategyComparison,
    refetchInterval: 60000,
  })

  // Get unique strategy IDs
  const strategyIds = useMemo(() => {
    if (!historyData) return []
    return [...new Set(historyData.map((d) => d.strategy_id))]
  }, [historyData])

  // Initialize selected strategies
  useMemo(() => {
    if (strategyIds.length > 0 && selectedStrategies.length === 0) {
      setSelectedStrategies(strategyIds.slice(0, 5)) // Select first 5 by default
    }
  }, [strategyIds])

  // Prepare chart data
  const chartData = useMemo(() => {
    if (!historyData) return []
    
    // Group by date
    const byDate = new Map<string, Record<string, number>>()
    
    historyData.forEach((item) => {
      if (!byDate.has(item.date)) {
        byDate.set(item.date, {})
      }
      byDate.get(item.date)![item.strategy_id] = item.nav
    })

    // Convert to array and normalize to starting value = 100
    const dates = Array.from(byDate.keys()).sort()
    const firstDate = dates[0]
    const firstValues = byDate.get(firstDate) || {}

    return dates.map((date) => {
      const values: Record<string, number | null> = { date }
      
      strategyIds.forEach((strategyId) => {
        const nav = byDate.get(date)?.[strategyId]
        const startNav = firstValues[strategyId]
        if (nav && startNav) {
          values[strategyId] = (nav / startNav) * 100
        } else {
          values[strategyId] = null
        }
      })
      
      return values
    })
  }, [historyData, strategyIds])

  // Calculate metrics for each strategy
  const strategyMetrics = useMemo(() => {
    if (!historyData) return []
    
    const metrics = strategyIds.map((strategyId, index) => {
      const strategyData = historyData
        .filter((d) => d.strategy_id === strategyId)
        .sort((a, b) => new Date(a.date).getTime() - new Date(b.date).getTime())
      
      if (strategyData.length === 0) return null

      const latest = strategyData[strategyData.length - 1]
      const first = strategyData[0]
      
      // Calculate total return
      const totalReturn = first.nav > 0 ? (latest.nav - first.nav) / first.nav : 0
      
      // Calculate daily returns for Sharpe
      const dailyReturns: number[] = []
      for (let i = 1; i < strategyData.length; i++) {
        const prev = strategyData[i - 1]
        const curr = strategyData[i]
        if (prev.nav > 0) {
          dailyReturns.push((curr.nav - prev.nav) / prev.nav)
        }
      }
      
      // Calculate max drawdown
      let maxDrawdown = 0
      let peak = first.nav
      strategyData.forEach((d) => {
        if (d.nav > peak) peak = d.nav
        const drawdown = peak > 0 ? (peak - d.nav) / peak : 0
        if (drawdown > maxDrawdown) maxDrawdown = drawdown
      })

      return {
        strategyId,
        color: STRATEGY_COLORS[index % STRATEGY_COLORS.length],
        nav: latest.nav,
        dailyReturn: latest.daily_return_pct || 0,
        maxDrawdown: maxDrawdown,
        sn88Score: latest.sn88_score,
        totalReturn,
        sharpeRatio: calculateSharpe(dailyReturns),
        dataPoints: strategyData.length,
      }
    })

    return metrics.filter((m): m is NonNullable<typeof m> => m !== null)
  }, [historyData, strategyIds])

  // Sort by SN88 score
  const sortedMetrics = useMemo(() => {
    return [...strategyMetrics].sort((a, b) => (b.sn88Score || 0) - (a.sn88Score || 0))
  }, [strategyMetrics])

  const toggleStrategy = (strategyId: string) => {
    setSelectedStrategies((prev) =>
      prev.includes(strategyId)
        ? prev.filter((id) => id !== strategyId)
        : [...prev, strategyId]
    )
  }

  const isLoading = isLoadingHistory || isLoadingComparison

  return (
    <div className="space-y-6">
      {/* Header */}
      <div className="flex items-center justify-between">
        <div>
          <h1 className="text-2xl font-bold text-[#2a3ded] flex items-center gap-2">
            <Trophy className="w-6 h-6" />
            Strategy Tournament
          </h1>
          <p className="text-sm text-[#8a8f98] mt-1">
            Compare strategies side-by-side with overlaid equity curves
          </p>
        </div>

        {/* Date Range Selector */}
        <div className="flex items-center gap-2 bg-[#16181d] rounded-lg p-1">
          {(['7d', '30d', '90d', '1y', 'all'] as const).map((range) => (
            <button
              key={range}
              onClick={() => setDateRange(range)}
              className={`px-3 py-1.5 rounded text-sm font-medium transition-colors ${
                dateRange === range
                  ? 'bg-[#2a3ded] text-white'
                  : 'text-[#9ca3af] hover:text-white'
              }`}
            >
              {range === '1y' ? '1Y' : range.toUpperCase()}
            </button>
          ))}
        </div>
      </div>

      {/* Strategy Selector */}
      <div className="bg-[#16181d] rounded-lg border border-[#2a2f38] p-4">
        <div className="flex items-center gap-2 mb-3">
          <Target className="w-4 h-4 text-[#6b7280]" />
          <span className="text-sm font-medium text-[#9ca3af]">Select strategies to compare</span>
        </div>
        <div className="flex flex-wrap gap-2">
          {strategyIds.map((strategyId, index) => {
            const isSelected = selectedStrategies.includes(strategyId)
            const color = STRATEGY_COLORS[index % STRATEGY_COLORS.length]
            
            return (
              <button
                key={strategyId}
                onClick={() => toggleStrategy(strategyId)}
                className={`flex items-center gap-2 px-3 py-1.5 rounded-lg text-sm transition-all ${
                  isSelected
                    ? 'bg-[#1e2128] border border-[#2a2f38]'
                    : 'bg-transparent border border-[#2a2f38] opacity-50'
                }`}
              >
                <div
                  className="w-3 h-3 rounded-full"
                  style={{ backgroundColor: color }}
                />
                <span className={isSelected ? 'text-white' : 'text-[#6b7280]'}>
                  {STRATEGY_DISPLAY_NAMES[strategyId] || strategyId}
                </span>
              </button>
            )
          })}
        </div>
      </div>

      {/* Chart */}
      <div className="bg-[#16181d] rounded-lg border border-[#2a2f38] p-5">
        <div className="flex items-center justify-between mb-4">
          <div className="flex items-center gap-2">
            <Activity className="w-5 h-5 text-[#2a3ded]" />
            <h3 className="font-semibold text-white">Equity Curves (Normalized to 100)</h3>
          </div>
        </div>

        {isLoading ? (
          <div className="h-[400px] flex items-center justify-center">
            <div className="animate-spin rounded-full h-8 w-8 border-b-2 border-[#2a3ded]" />
          </div>
        ) : chartData.length > 0 ? (
          <div className="h-[400px]">
            <ResponsiveContainer width="100%" height="100%">
              <LineChart data={chartData} margin={{ top: 5, right: 30, left: 20, bottom: 5 }}>
                <CartesianGrid strokeDasharray="3 3" stroke="#2a2f38" />
                <XAxis
                  dataKey="date"
                  tick={{ fill: '#6b7280', fontSize: 12 }}
                  tickFormatter={(date) => format(parseISO(date), 'MMM d')}
                  stroke="#2a2f38"
                />
                <YAxis
                  tick={{ fill: '#6b7280', fontSize: 12 }}
                  stroke="#2a2f38"
                  domain={['auto', 'auto']}
                  tickFormatter={(val) => val.toFixed(0)}
                />
                <Tooltip
                  contentStyle={{
                    backgroundColor: '#16181d',
                    border: '1px solid #2a2f38',
                    borderRadius: '8px',
                  }}
                  labelStyle={{ color: '#9ca3af' }}
                  itemStyle={{ color: '#fff' }}
                  formatter={(value: number) => [value?.toFixed(2), '']}
                  labelFormatter={(date) => format(parseISO(date as string), 'MMM d, yyyy')}
                />
                <Legend
                  verticalAlign="top"
                  height={36}
                  iconType="line"
                  wrapperStyle={{ color: '#9ca3af' }}
                />
                {selectedStrategies.map((strategyId, index) => {
                  const colorIndex = strategyIds.indexOf(strategyId)
                  return (
                    <Line
                      key={strategyId}
                      type="monotone"
                      dataKey={strategyId}
                      stroke={STRATEGY_COLORS[colorIndex % STRATEGY_COLORS.length]}
                      strokeWidth={2}
                      dot={false}
                      connectNulls
                      name={strategyId}
                    />
                  )
                })}
              </LineChart>
            </ResponsiveContainer>
          </div>
        ) : (
          <div className="h-[400px] flex items-center justify-center text-[#6b7280]">
            No data available for selected range
          </div>
        )}
      </div>

      {/* Comparison Table */}
      <div className="bg-[#16181d] rounded-lg border border-[#2a2f38] overflow-hidden">
        <div className="px-5 py-4 border-b border-[#2a2f38]">
          <div className="flex items-center gap-2">
            <BarChart3 className="w-5 h-5 text-[#2a3ded]" />
            <h3 className="font-semibold text-white">Strategy Comparison</h3>
          </div>
        </div>

        {isLoading ? (
          <div className="p-8">
            <div className="space-y-2">
              {[1, 2, 3, 4].map((i) => (
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
                    Rank
                  </th>
                  <th className="px-4 py-3 text-left text-xs font-semibold text-[#6b7280] uppercase tracking-wider">
                    Strategy
                  </th>
                  <th className="px-4 py-3 text-right text-xs font-semibold text-[#6b7280] uppercase tracking-wider">
                    SN88 Score
                  </th>
                  <th className="px-4 py-3 text-right text-xs font-semibold text-[#6b7280] uppercase tracking-wider">
                    NAV
                  </th>
                  <th className="px-4 py-3 text-right text-xs font-semibold text-[#6b7280] uppercase tracking-wider">
                    Total Return
                  </th>
                  <th className="px-4 py-3 text-right text-xs font-semibold text-[#6b7280] uppercase tracking-wider">
                    Daily Return
                  </th>
                  <th className="px-4 py-3 text-right text-xs font-semibold text-[#6b7280] uppercase tracking-wider">
                    Max Drawdown
                  </th>
                  <th className="px-4 py-3 text-right text-xs font-semibold text-[#6b7280] uppercase tracking-wider">
                    Sharpe Ratio
                  </th>
                </tr>
              </thead>
              <tbody className="divide-y divide-[#2a2f38]">
                {sortedMetrics.map((metric, index) => (
                  <tr
                    key={metric.strategyId}
                    className={index === 0 ? 'bg-[#2a3ded]/10' : 'hover:bg-[#1e2128]/50'}
                  >
                    <td className="px-4 py-3">
                      <div className="flex items-center gap-2">
                        {index === 0 && <Trophy className="w-4 h-4 text-yellow-400" />}
                        {index === 1 && <span className="text-gray-400 font-bold">2</span>}
                        {index === 2 && <span className="text-orange-400 font-bold">3</span>}
                        {index > 2 && <span className="text-[#6b7280]">{index + 1}</span>}
                      </div>
                    </td>
                    <td className="px-4 py-3">
                      <div className="flex items-center gap-2">
                        <div
                          className="w-3 h-3 rounded-full"
                          style={{ backgroundColor: metric.color }}
                        />
                        <span className="text-sm font-medium text-white">
                          {STRATEGY_DISPLAY_NAMES[metric.strategyId] || metric.strategyId}
                        </span>
                      </div>
                    </td>
                    <td className="px-4 py-3 text-right">
                      <span
                        className={`text-sm font-bold tabular-nums ${
                          (metric.sn88Score || 0) >= 70
                            ? 'text-green-400'
                            : (metric.sn88Score || 0) >= 50
                            ? 'text-yellow-400'
                            : 'text-red-400'
                        }`}
                      >
                        {(metric.sn88Score || 0).toFixed(1)}
                      </span>
                    </td>
                    <td className="px-4 py-3 text-right">
                      <span className="text-sm text-white tabular-nums">
                        {metric.nav.toFixed(2)} τ
                      </span>
                    </td>
                    <td className="px-4 py-3 text-right">
                      <span
                        className={`text-sm tabular-nums ${
                          metric.totalReturn >= 0 ? 'text-green-400' : 'text-red-400'
                        }`}
                      >
                        {metric.totalReturn >= 0 ? '+' : ''}
                        {formatPct(metric.totalReturn)}
                      </span>
                    </td>
                    <td className="px-4 py-3 text-right">
                      <span
                        className={`text-sm tabular-nums ${
                          metric.dailyReturn >= 0 ? 'text-green-400' : 'text-red-400'
                        }`}
                      >
                        {metric.dailyReturn >= 0 ? '+' : ''}
                        {formatPct(metric.dailyReturn)}
                      </span>
                    </td>
                    <td className="px-4 py-3 text-right">
                      <span className="text-sm text-red-400 tabular-nums">
                        {formatPct(metric.maxDrawdown)}
                      </span>
                    </td>
                    <td className="px-4 py-3 text-right">
                      <span className="text-sm text-white tabular-nums">
                        {metric.sharpeRatio.toFixed(2)}
                      </span>
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
            {sortedMetrics.length === 0 && (
              <div className="text-center py-8 text-[#6b7280]">
                No strategy data available
              </div>
            )}
          </div>
        )}
      </div>

      {/* Metrics Summary Cards */}
      <div className="grid grid-cols-1 md:grid-cols-4 gap-4">
        <div className="bg-[#16181d] rounded-lg border border-[#2a2f38] p-4">
          <div className="flex items-center gap-2 mb-2">
            <Trophy className="w-4 h-4 text-[#2a3ded]" />
            <span className="text-xs text-[#6b7280]">Best Strategy</span>
          </div>
          <div className="text-lg font-bold text-white">
            {sortedMetrics[0]?.strategyId || 'N/A'}
          </div>
          <div className="text-xs text-green-400">
            SN88: {(sortedMetrics[0]?.sn88Score || 0).toFixed(1)}
          </div>
        </div>

        <div className="bg-[#16181d] rounded-lg border border-[#2a2f38] p-4">
          <div className="flex items-center gap-2 mb-2">
            <TrendingUp className="w-4 h-4 text-[#2a3ded]" />
            <span className="text-xs text-[#6b7280]">Highest Return</span>
          </div>
          <div className="text-lg font-bold text-white">
            {sortedMetrics.length > 0
              ? formatPct(
                  Math.max(...sortedMetrics.map((m) => m.totalReturn))
                )
              : 'N/A'}
          </div>
          <div className="text-xs text-[#6b7280]">Total return</div>
        </div>

        <div className="bg-[#16181d] rounded-lg border border-[#2a2f38] p-4">
          <div className="flex items-center gap-2 mb-2">
            <TrendingDown className="w-4 h-4 text-[#2a3ded]" />
            <span className="text-xs text-[#6b7280]">Lowest Drawdown</span>
          </div>
          <div className="text-lg font-bold text-white">
            {sortedMetrics.length > 0
              ? formatPct(
                  Math.min(...sortedMetrics.map((m) => m.maxDrawdown))
                )
              : 'N/A'}
          </div>
          <div className="text-xs text-[#6b7280]">Max drawdown</div>
        </div>

        <div className="bg-[#16181d] rounded-lg border border-[#2a2f38] p-4">
          <div className="flex items-center gap-2 mb-2">
            <Calendar className="w-4 h-4 text-[#2a3ded]" />
            <span className="text-xs text-[#6b7280]">Data Points</span>
          </div>
          <div className="text-lg font-bold text-white">
            {chartData.length > 0 ? chartData.length : 'N/A'}
          </div>
          <div className="text-xs text-[#6b7280]">Trading days</div>
        </div>
      </div>
    </div>
  )
}
