import { useMemo } from 'react'
import { useParams, Link } from 'react-router-dom'
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
  AreaChart,
  Area,
} from 'recharts'
import {
  ArrowLeft,
  TrendingUp,
  TrendingDown,
  Activity,
  Calendar,
  Target,
  PieChart,
  BarChart3,
  ChevronRight,
} from 'lucide-react'
import { format, parseISO } from 'date-fns'
import { supabaseQueries, type StrategyLedger } from '../services/supabase'

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

// Calculate Sharpe ratio from returns
function calculateSharpe(returns: number[]): number {
  if (returns.length < 2) return 0
  const avg = returns.reduce((a, b) => a + b, 0) / returns.length
  const variance = returns.reduce((sum, r) => sum + Math.pow(r - avg, 2), 0) / (returns.length - 1)
  const stdDev = Math.sqrt(variance)
  return stdDev === 0 ? 0 : (avg / stdDev) * Math.sqrt(365) // Annualized
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

export default function StrategyDetail() {
  const { strategyId } = useParams<{ strategyId: string }>()

  // Fetch strategy detail data
  const { data: ledgerData, isLoading: isLoadingLedger } = useQuery({
    queryKey: ['supabase-strategy-detail', strategyId],
    queryFn: () => supabaseQueries.getStrategyDetail(strategyId!),
    enabled: !!strategyId,
    refetchInterval: 60000,
  })

  // Calculate metrics
  const metrics = useMemo(() => {
    if (!ledgerData || ledgerData.length === 0) return null

    const first = ledgerData[0]
    const latest = ledgerData[ledgerData.length - 1]

    // Total return
    const totalReturn = first.nav > 0 ? ((latest.nav - first.nav) / first.nav) * 100 : 0

    // Daily returns for Sharpe
    const dailyReturns: number[] = []
    for (let i = 1; i < ledgerData.length; i++) {
      const prev = ledgerData[i - 1]
      const curr = ledgerData[i]
      if (prev.nav > 0) {
        dailyReturns.push((curr.nav - prev.nav) / prev.nav)
      }
    }

    // Max drawdown
    let maxDrawdown = 0
    let peak = first.nav
    ledgerData.forEach((d) => {
      if (d.nav > peak) peak = d.nav
      const drawdown = peak > 0 ? ((peak - d.nav) / peak) * 100 : 0
      if (drawdown > maxDrawdown) maxDrawdown = drawdown
    })

    // Win rate
    const winningDays = ledgerData.filter((d) => (d.daily_return_pct || 0) > 0).length
    const winRate = ledgerData.length > 0 ? (winningDays / ledgerData.length) * 100 : 0

    // Average positions held
    let totalPositions = 0
    let daysWithPositions = 0
    ledgerData.forEach((d) => {
      const pos = parsePositions(d.notes)
      if (pos) {
        totalPositions += pos.positionCount
        daysWithPositions++
      }
    })
    const avgPositions = daysWithPositions > 0 ? totalPositions / daysWithPositions : 0

    // Best and worst day
    const returns = ledgerData.map((d) => d.daily_return_pct || 0)
    const bestDay = Math.max(...returns)
    const worstDay = Math.min(...returns)

    return {
      totalReturn,
      maxDrawdown,
      sharpeRatio: calculateSharpe(dailyReturns),
      winRate,
      avgPositions,
      bestDay,
      worstDay,
      dataPoints: ledgerData.length,
      latestNAV: latest.nav,
      latestSN88: latest.sn88_score,
      latestDailyReturn: latest.daily_return_pct,
    }
  }, [ledgerData])

  // Prepare equity curve data
  const equityData = useMemo(() => {
    if (!ledgerData) return []
    return ledgerData.map((d) => ({
      date: d.date,
      nav: d.nav,
      dailyReturn: d.daily_return_pct || 0,
    }))
  }, [ledgerData])

  // Prepare SN88 components data
  const sn88Data = useMemo(() => {
    if (!ledgerData) return []
    return ledgerData
      .filter((d) => d.sn88_score !== null)
      .map((d) => ({
        date: d.date,
        sn88: d.sn88_score || 0,
        mar: d.sn88_mar || 0,
        lsr: d.sn88_lsr || 0,
        odds: d.sn88_odds || 0,
        daily: d.sn88_daily || 0,
      }))
  }, [ledgerData])

  // Prepare daily ledger with positions
  const dailyLedger = useMemo(() => {
    if (!ledgerData) return []
    return ledgerData
      .slice()
      .reverse()
      .map((d) => {
        const positions = parsePositions(d.notes)
        // Calculate daily P&L per position (estimated based on weights)
        const positionDetails = positions
          ? Object.entries(positions.positions).map(([netuid, weight]) => ({
              netuid: parseInt(netuid),
              weight,
              estimatedPnL: ((d.daily_return_pct || 0) * weight) / 100,
            }))
          : []

        return {
          ...d,
          positions,
          positionDetails,
        }
      })
  }, [ledgerData])

  const displayName = STRATEGY_DISPLAY_NAMES[strategyId || ''] || strategyId

  if (!strategyId) {
    return (
      <div className="flex flex-col items-center justify-center h-[60vh] text-[#6b7280]">
        <p>Strategy not found</p>
        <Link to="/tournament" className="text-[#2a3ded] hover:underline mt-4">
          Back to Tournament
        </Link>
      </div>
    )
  }

  return (
    <div className="space-y-6">
      {/* Header */}
      <div className="flex items-center justify-between">
        <div className="flex items-center gap-4">
          <Link
            to="/tournament"
            className="flex items-center gap-2 text-[#6b7280] hover:text-white transition-colors"
          >
            <ArrowLeft className="w-5 h-5" />
            <span className="text-sm">Back</span>
          </Link>
          <div>
            <h1 className="text-2xl font-bold text-white flex items-center gap-2">
              <Target className="w-6 h-6 text-[#2a3ded]" />
              {displayName}
            </h1>
            <p className="text-sm text-[#8a8f98] mt-1">
              Strategy ID: <span className="font-mono">{strategyId}</span>
            </p>
          </div>
        </div>

        {metrics && (
          <div className="flex items-center gap-4">
            <div className="text-right">
              <p className="text-xs text-[#6b7280]">Latest NAV</p>
              <p className="text-xl font-bold text-white tabular-nums">
                {formatNum(metrics.latestNAV, 4)} τ
              </p>
            </div>
            <div className="text-right">
              <p className="text-xs text-[#6b7280]">SN88 Score</p>
              <p
                className={`text-xl font-bold tabular-nums ${
                  (metrics.latestSN88 || 0) >= 70
                    ? 'text-green-400'
                    : (metrics.latestSN88 || 0) >= 50
                    ? 'text-yellow-400'
                    : 'text-red-400'
                }`}
              >
                {formatNum(metrics.latestSN88, 1)}
              </p>
            </div>
          </div>
        )}
      </div>

      {/* Summary Stats Cards */}
      {metrics && (
        <div className="grid grid-cols-2 md:grid-cols-4 lg:grid-cols-6 gap-4">
          <div className="bg-[#16181d] rounded-lg border border-[#2a2f38] p-4">
            <div className="flex items-center gap-2 mb-2">
              <TrendingUp className="w-4 h-4 text-[#2a3ded]" />
              <span className="text-xs text-[#6b7280]">Total Return</span>
            </div>
            <div
              className={`text-lg font-bold tabular-nums ${
                metrics.totalReturn >= 0 ? 'text-green-400' : 'text-red-400'
              }`}
            >
              {metrics.totalReturn >= 0 ? '+' : ''}
              {formatPct(metrics.totalReturn)}
            </div>
          </div>

          <div className="bg-[#16181d] rounded-lg border border-[#2a2f38] p-4">
            <div className="flex items-center gap-2 mb-2">
              <TrendingDown className="w-4 h-4 text-[#2a3ded]" />
              <span className="text-xs text-[#6b7280]">Max Drawdown</span>
            </div>
            <div className="text-lg font-bold text-red-400 tabular-nums">
              {formatPct(metrics.maxDrawdown)}
            </div>
          </div>

          <div className="bg-[#16181d] rounded-lg border border-[#2a2f38] p-4">
            <div className="flex items-center gap-2 mb-2">
              <Activity className="w-4 h-4 text-[#2a3ded]" />
              <span className="text-xs text-[#6b7280]">Win Rate</span>
            </div>
            <div className="text-lg font-bold text-white tabular-nums">
              {formatPct(metrics.winRate)}
            </div>
          </div>

          <div className="bg-[#16181d] rounded-lg border border-[#2a2f38] p-4">
            <div className="flex items-center gap-2 mb-2">
              <PieChart className="w-4 h-4 text-[#2a3ded]" />
              <span className="text-xs text-[#6b7280]">Avg Positions</span>
            </div>
            <div className="text-lg font-bold text-white tabular-nums">
              {metrics.avgPositions.toFixed(1)}
            </div>
          </div>

          <div className="bg-[#16181d] rounded-lg border border-[#2a2f38] p-4">
            <div className="flex items-center gap-2 mb-2">
              <BarChart3 className="w-4 h-4 text-[#2a3ded]" />
              <span className="text-xs text-[#6b7280]">Sharpe Ratio</span>
            </div>
            <div className="text-lg font-bold text-white tabular-nums">
              {formatNum(metrics.sharpeRatio, 2)}
            </div>
          </div>

          <div className="bg-[#16181d] rounded-lg border border-[#2a2f38] p-4">
            <div className="flex items-center gap-2 mb-2">
              <Calendar className="w-4 h-4 text-[#2a3ded]" />
              <span className="text-xs text-[#6b7280]">Trading Days</span>
            </div>
            <div className="text-lg font-bold text-white tabular-nums">
              {metrics.dataPoints}
            </div>
          </div>
        </div>
      )}

      {/* Equity Curve Chart */}
      <div className="bg-[#16181d] rounded-lg border border-[#2a2f38] p-5">
        <div className="flex items-center justify-between mb-4">
          <div className="flex items-center gap-2">
            <Activity className="w-5 h-5 text-[#2a3ded]" />
            <h3 className="font-semibold text-white">Equity Curve (NAV)</h3>
          </div>
        </div>

        {isLoadingLedger ? (
          <div className="h-[300px] flex items-center justify-center">
            <div className="animate-spin rounded-full h-8 w-8 border-b-2 border-[#2a3ded]" />
          </div>
        ) : equityData.length > 0 ? (
          <div className="h-[300px]">
            <ResponsiveContainer width="100%" height="100%">
              <AreaChart data={equityData} margin={{ top: 5, right: 30, left: 20, bottom: 5 }}>
                <defs>
                  <linearGradient id="navGradient" x1="0" y1="0" x2="0" y2="1">
                    <stop offset="5%" stopColor="#2a3ded" stopOpacity={0.3} />
                    <stop offset="95%" stopColor="#2a3ded" stopOpacity={0} />
                  </linearGradient>
                </defs>
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
                  tickFormatter={(val) => val.toFixed(2)}
                />
                <Tooltip
                  contentStyle={{
                    backgroundColor: '#16181d',
                    border: '1px solid #2a2f38',
                    borderRadius: '8px',
                  }}
                  labelStyle={{ color: '#9ca3af' }}
                  itemStyle={{ color: '#fff' }}
                  formatter={(value: number) => [value?.toFixed(4), 'NAV']}
                  labelFormatter={(date) => format(parseISO(date as string), 'MMM d, yyyy')}
                />
                <Area
                  type="monotone"
                  dataKey="nav"
                  stroke="#2a3ded"
                  fillOpacity={1}
                  fill="url(#navGradient)"
                  strokeWidth={2}
                />
              </AreaChart>
            </ResponsiveContainer>
          </div>
        ) : (
          <div className="h-[300px] flex items-center justify-center text-[#6b7280]">
            No equity data available
          </div>
        )}
      </div>

      {/* SN88 Score Components */}
      {sn88Data.length > 0 && (
        <div className="bg-[#16181d] rounded-lg border border-[#2a2f38] p-5">
          <div class="flex items-center justify-between mb-4">
            <div className="flex items-center gap-2">
              <BarChart3 className="w-5 h-5 text-[#2a3ded]" />
              <h3 className="font-semibold text-white">SN88 Score Components</h3>
            </div>
          </div>

          <div className="h-[250px]">
            <ResponsiveContainer width="100%" height="100%">
              <LineChart data={sn88Data} margin={{ top: 5, right: 30, left: 20, bottom: 5 }}>
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
                  domain={[0, 100]}
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
                  formatter={(value: number, name: string) => [value?.toFixed(1), name]}
                  labelFormatter={(date) => format(parseISO(date as string), 'MMM d, yyyy')}
                />
                <Legend wrapperStyle={{ color: '#9ca3af' }} />
                <Line
                  type="monotone"
                  dataKey="sn88"
                  stroke="#2a3ded"
                  strokeWidth={2}
                  dot={false}
                  name="SN88"
                />
                <Line
                  type="monotone"
                  dataKey="mar"
                  stroke="#10b981"
                  strokeWidth={1.5}
                  dot={false}
                  name="MAR"
                />
                <Line
                  type="monotone"
                  dataKey="lsr"
                  stroke="#f59e0b"
                  strokeWidth={1.5}
                  dot={false}
                  name="LSR"
                />
                <Line
                  type="monotone"
                  dataKey="odds"
                  stroke="#8b5cf6"
                  strokeWidth={1.5}
                  dot={false}
                  name="Odds%"
                />
                <Line
                  type="monotone"
                  dataKey="daily"
                  stroke="#06b6d4"
                  strokeWidth={1.5}
                  dot={false}
                  name="Daily%"
                />
              </LineChart>
            </ResponsiveContainer>
          </div>
        </div>
      )}

      {/* Daily Ledger Table */}
      <div className="bg-[#16181d] rounded-lg border border-[#2a2f38] overflow-hidden">
        <div className="px-5 py-4 border-b border-[#2a2f38]">
          <div className="flex items-center justify-between">
            <div className="flex items-center gap-2">
              <Calendar className="w-5 h-5 text-[#2a3ded]" />
              <h3 className="font-semibold text-white">Daily Ledger</h3>
            </div>
            <span className="text-sm text-[#6b7280]">
              {dailyLedger.length} entries
            </span>
          </div>
        </div>

        {isLoadingLedger ? (
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
                    Date
                  </th>
                  <th className="px-4 py-3 text-right text-xs font-semibold text-[#6b7280] uppercase tracking-wider">
                    NAV
                  </th>
                  <th className="px-4 py-3 text-right text-xs font-semibold text-[#6b7280] uppercase tracking-wider">
                    Daily Return
                  </th>
                  <th className="px-4 py-3 text-right text-xs font-semibold text-[#6b7280] uppercase tracking-wider">
                    Cumulative Return
                  </th>
                  <th className="px-4 py-3 text-right text-xs font-semibold text-[#6b7280] uppercase tracking-wider">
                    Max Drawdown
                  </th>
                  <th className="px-4 py-3 text-right text-xs font-semibold text-[#6b7280] uppercase tracking-wider">
                    SN88
                  </th>
                  <th className="px-4 py-3 text-left text-xs font-semibold text-[#6b7280] uppercase tracking-wider">
                    Positions
                  </th>
                  <th className="px-4 py-3 text-right text-xs font-semibold text-[#6b7280] uppercase tracking-wider">
                    # Pos
                  </th>
                </tr>
              </thead>
              <tbody className="divide-y divide-[#2a2f38]">
                {dailyLedger.slice(0, 50).map((day, index) => (
                  <tr
                    key={day.date}
                    className={index % 2 === 0 ? 'bg-[#0d1117]' : 'bg-[#16181d]'}
                  >
                    <td className="px-4 py-3">
                      <span className="text-sm text-white">
                        {format(parseISO(day.date), 'MMM d, yyyy')}
                      </span>
                    </td>
                    <td className="px-4 py-3 text-right">
                      <span className="text-sm text-white tabular-nums">
                        {formatNum(day.nav, 4)} τ
                      </span>
                    </td>
                    <td className="px-4 py-3 text-right">
                      <span
                        className={`text-sm tabular-nums ${
                          (day.daily_return_pct || 0) >= 0 ? 'text-green-400' : 'text-red-400'
                        }`}
                      >
                        {(day.daily_return_pct || 0) >= 0 ? '+' : ''}
                        {formatPct(day.daily_return_pct)}
                      </span>
                    </td>
                    <td className="px-4 py-3 text-right">
                      <span
                        className={`text-sm tabular-nums ${
                          (day.cumulative_return_pct || 0) >= 0 ? 'text-green-400' : 'text-red-400'
                        }`}
                      >
                        {(day.cumulative_return_pct || 0) >= 0 ? '+' : ''}
                        {formatPct(day.cumulative_return_pct)}
                      </span>
                    </td>
                    <td className="px-4 py-3 text-right">
                      <span className="text-sm text-red-400 tabular-nums">
                        {formatPct(day.max_drawdown_pct)}
                      </span>
                    </td>
                    <td className="px-4 py-3 text-right">
                      <span
                        className={`text-sm font-medium tabular-nums ${
                          (day.sn88_score || 0) >= 70
                            ? 'text-green-400'
                            : (day.sn88_score || 0) >= 50
                            ? 'text-yellow-400'
                            : 'text-red-400'
                        }`}
                      >
                        {formatNum(day.sn88_score, 1)}
                      </span>
                    </td>
                    <td className="px-4 py-3">
                      {day.positions ? (
                        <div className="flex flex-wrap gap-1">
                          {Object.entries(day.positions.positions)
                            .slice(0, 5)
                            .map(([netuid, weight]) => (
                              <span
                                key={netuid}
                                className="inline-flex items-center px-2 py-0.5 rounded text-xs bg-[#2a3ded]/20 text-[#2a3ded]"
                              >
                                SN{netuid}: {(weight * 100).toFixed(0)}%
                              </span>
                            ))}
                          {Object.keys(day.positions.positions).length > 5 && (
                            <span className="text-xs text-[#6b7280]">
                              +{Object.keys(day.positions.positions).length - 5} more
                            </span>
                          )}
                        </div>
                      ) : (
                        <span className="text-sm text-[#6b7280]">No data</span>
                      )}
                    </td>
                    <td className="px-4 py-3 text-right">
                      <span className="text-sm text-[#6b7280] tabular-nums">
                        {day.positions?.positionCount || 0}
                      </span>
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
            {dailyLedger.length === 0 && (
              <div className="text-center py-8 text-[#6b7280]">
                No ledger data available
              </div>
            )}
            {dailyLedger.length > 50 && (
              <div className="px-4 py-3 text-center text-sm text-[#6b7280]">
                Showing first 50 of {dailyLedger.length} entries
              </div>
            )}
          </div>
        )}
      </div>

      {/* Compare CTA */}
      <div className="bg-[#16181d] rounded-lg border border-[#2a2f38] p-6">
        <div className="flex items-center justify-between">
          <div>
            <h3 className="font-semibold text-white">Compare with Your Portfolio</h3>
            <p className="text-sm text-[#6b7280] mt-1">
              See how this strategy compares to your current holdings
            </p>
          </div>
          <Link
            to="/compare"
            className="flex items-center gap-2 px-4 py-2 bg-[#2a3ded] text-white rounded-lg hover:bg-[#2a3ded]/80 transition-colors"
          >
            <span>Compare</span>
            <ChevronRight className="w-4 h-4" />
          </Link>
        </div>
      </div>
    </div>
  )
}