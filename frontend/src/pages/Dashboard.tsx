import { useState, useMemo } from 'react'
import { useQuery } from '@tanstack/react-query'
import { TrendingUp, TrendingDown, AlertTriangle, ArrowRightLeft, Coins, DollarSign, Activity, CheckCircle, XCircle, ChevronUp, ChevronDown, ChevronsUpDown } from 'lucide-react'
import { api } from '../services/api'
import { Dashboard as DashboardType } from '../types'

type SortDirection = 'asc' | 'desc' | null
type SortKey = 'subnet_name' | 'tao_value_mid' | 'weight_pct' | 'current_apy' | 'daily_yield_tao' | 'unrealized_pnl_pct' | 'health_status' | null

interface SortableHeaderProps {
  label: string
  sortKey: SortKey
  currentSortKey: SortKey
  currentDirection: SortDirection
  onSort: (key: SortKey) => void
  align?: 'left' | 'right'
}

function SortableHeader({ label, sortKey, currentSortKey, currentDirection, onSort, align = 'left' }: SortableHeaderProps) {
  const isActive = currentSortKey === sortKey

  return (
    <th
      className={`px-4 py-3 text-xs font-medium text-gray-400 uppercase tracking-wider cursor-pointer hover:bg-gray-700/50 select-none ${align === 'right' ? 'text-right' : 'text-left'}`}
      onClick={() => onSort(sortKey)}
    >
      <div className={`flex items-center gap-1 ${align === 'right' ? 'justify-end' : ''}`}>
        <span>{label}</span>
        <span className="text-gray-500">
          {isActive ? (
            currentDirection === 'asc' ? <ChevronUp className="w-3 h-3" /> : <ChevronDown className="w-3 h-3" />
          ) : (
            <ChevronsUpDown className="w-3 h-3 opacity-50" />
          )}
        </span>
      </div>
    </th>
  )
}

function formatTao(value: string | number): string {
  const num = typeof value === 'string' ? parseFloat(value) : value
  return num.toLocaleString(undefined, { minimumFractionDigits: 2, maximumFractionDigits: 4 })
}

function formatTaoShort(value: string | number): string {
  const num = typeof value === 'string' ? parseFloat(value) : value
  return num.toLocaleString(undefined, { minimumFractionDigits: 2, maximumFractionDigits: 2 })
}

function formatPercent(value: string | number): string {
  const num = typeof value === 'string' ? parseFloat(value) : value
  return `${num >= 0 ? '+' : ''}${num.toFixed(2)}%`
}

function formatApy(value: string | number): string {
  const num = typeof value === 'string' ? parseFloat(value) : value
  return `${num.toFixed(1)}%`
}

function formatUsd(value: string | number): string {
  const num = typeof value === 'string' ? parseFloat(value) : value
  return `$${num.toLocaleString(undefined, { minimumFractionDigits: 2, maximumFractionDigits: 2 })}`
}

export default function Dashboard() {
  const [sortKey, setSortKey] = useState<SortKey>('tao_value_mid')
  const [sortDirection, setSortDirection] = useState<SortDirection>('desc')

  const { data, isLoading, error } = useQuery<DashboardType>({
    queryKey: ['dashboard'],
    queryFn: api.getDashboard,
    refetchInterval: 30000,
  })

  const handleSort = (key: SortKey) => {
    if (sortKey === key) {
      if (sortDirection === 'desc') {
        setSortDirection('asc')
      } else if (sortDirection === 'asc') {
        setSortKey(null)
        setSortDirection(null)
      }
    } else {
      setSortKey(key)
      setSortDirection('desc')
    }
  }

  const sortedPositions = useMemo(() => {
    const positions = data?.top_positions || []
    if (!sortKey || !sortDirection) return positions

    return [...positions].sort((a, b) => {
      let aVal: number | string
      let bVal: number | string

      switch (sortKey) {
        case 'subnet_name':
          aVal = a.subnet_name || `SN${a.netuid}`
          bVal = b.subnet_name || `SN${b.netuid}`
          break
        case 'tao_value_mid':
          aVal = parseFloat(a.tao_value_mid)
          bVal = parseFloat(b.tao_value_mid)
          break
        case 'weight_pct':
          aVal = parseFloat(a.weight_pct)
          bVal = parseFloat(b.weight_pct)
          break
        case 'current_apy':
          aVal = parseFloat(a.current_apy || '0')
          bVal = parseFloat(b.current_apy || '0')
          break
        case 'daily_yield_tao':
          aVal = parseFloat(a.daily_yield_tao || '0')
          bVal = parseFloat(b.daily_yield_tao || '0')
          break
        case 'unrealized_pnl_pct':
          aVal = parseFloat(a.unrealized_pnl_pct)
          bVal = parseFloat(b.unrealized_pnl_pct)
          break
        case 'health_status':
          const statusOrder = { red: 0, yellow: 1, green: 2 }
          aVal = statusOrder[a.health_status as keyof typeof statusOrder] ?? 2
          bVal = statusOrder[b.health_status as keyof typeof statusOrder] ?? 2
          break
        default:
          return 0
      }

      if (typeof aVal === 'string' && typeof bVal === 'string') {
        return sortDirection === 'asc'
          ? aVal.localeCompare(bVal)
          : bVal.localeCompare(aVal)
      }

      return sortDirection === 'asc'
        ? (aVal as number) - (bVal as number)
        : (bVal as number) - (aVal as number)
    })
  }, [data?.top_positions, sortKey, sortDirection])

  if (isLoading) {
    return (
      <div className="flex items-center justify-center h-64">
        <div className="animate-spin rounded-full h-8 w-8 border-b-2 border-tao-400"></div>
      </div>
    )
  }

  if (error || !data) {
    return (
      <div className="bg-red-900/20 border border-red-700 rounded-lg p-4">
        <p className="text-red-400">Failed to load dashboard data. Make sure the backend is running and data has been synced.</p>
      </div>
    )
  }

  const { portfolio, alerts, portfolio_health, action_items } = data

  return (
    <div className="space-y-6">
      <div className="flex items-center justify-between">
        <h1 className="text-2xl font-bold">Dashboard</h1>
        <div className="text-sm text-gray-500">
          Last updated: {new Date(data.generated_at).toLocaleTimeString()}
        </div>
      </div>

      {/* Portfolio Health Banner */}
      {portfolio_health && (
        <div className={`rounded-lg p-4 border flex items-center justify-between ${
          portfolio_health.status === 'red' ? 'bg-red-900/20 border-red-700' :
          portfolio_health.status === 'yellow' ? 'bg-yellow-900/20 border-yellow-700' :
          'bg-green-900/20 border-green-700'
        }`}>
          <div className="flex items-center gap-4">
            <div className={`p-3 rounded-full ${
              portfolio_health.status === 'red' ? 'bg-red-600/30' :
              portfolio_health.status === 'yellow' ? 'bg-yellow-600/30' :
              'bg-green-600/30'
            }`}>
              {portfolio_health.status === 'red' ? <XCircle className="text-red-400 w-8 h-8" /> :
               portfolio_health.status === 'yellow' ? <AlertTriangle className="text-yellow-400 w-8 h-8" /> :
               <CheckCircle className="text-green-400 w-8 h-8" />}
            </div>
            <div>
              <div className="text-lg font-semibold">
                Portfolio Health: <span className={
                  portfolio_health.status === 'red' ? 'text-red-400' :
                  portfolio_health.status === 'yellow' ? 'text-yellow-400' :
                  'text-green-400'
                }>{portfolio_health.status === 'red' ? 'ACTION REQUIRED' :
                   portfolio_health.status === 'yellow' ? 'NEEDS ATTENTION' : 'GOOD'}</span>
              </div>
              {portfolio_health.top_issue && (
                <div className="text-sm text-gray-400">{portfolio_health.top_issue}</div>
              )}
            </div>
          </div>
          <div className="text-right">
            <div className="text-3xl font-bold">{portfolio_health.score}</div>
            <div className="text-xs text-gray-500">Health Score</div>
          </div>
        </div>
      )}

      {/* Action Items */}
      {action_items && action_items.length > 0 && (
        <div className="bg-gray-800 rounded-lg border border-gray-700">
          <div className="px-6 py-4 border-b border-gray-700 flex items-center justify-between">
            <h3 className="text-lg font-semibold flex items-center gap-2">
              <Activity className="w-5 h-5" />
              Action Items
            </h3>
            <span className="text-sm text-gray-500">{action_items.length} items</span>
          </div>
          <div className="divide-y divide-gray-700">
            {action_items.slice(0, 5).map((item, idx) => (
              <div key={idx} className="px-6 py-4 flex items-start gap-4">
                <div className={`px-2 py-1 rounded text-xs font-semibold ${
                  item.priority === 'high' ? 'bg-red-600/20 text-red-400' :
                  item.priority === 'medium' ? 'bg-yellow-600/20 text-yellow-400' :
                  'bg-blue-600/20 text-blue-400'
                }`}>
                  {item.priority.toUpperCase()}
                </div>
                <div className="flex-1">
                  <div className="font-medium">{item.title}</div>
                  <div className="text-sm text-gray-400">{item.description}</div>
                </div>
                {item.potential_gain_tao && (
                  <div className="text-right text-sm">
                    <div className="text-green-400">+{parseFloat(item.potential_gain_tao).toFixed(2)} τ</div>
                    <div className="text-xs text-gray-500">potential</div>
                  </div>
                )}
              </div>
            ))}
          </div>
        </div>
      )}

      {/* NAV Cards */}
      <div className="grid grid-cols-1 md:grid-cols-4 gap-4">
        <div className="bg-gray-800 rounded-lg p-6 border border-gray-700">
          <div className="text-sm text-gray-400 mb-1">Total NAV (TAO)</div>
          <div className="text-3xl font-bold text-white">{formatTao(portfolio.nav_mid)}</div>
          <div className="text-sm text-gray-500 mt-1">{formatUsd(portfolio.nav_usd)} USD</div>
        </div>

        <div className="bg-gray-800 rounded-lg p-6 border border-gray-700">
          <div className="flex items-center gap-2 text-sm text-gray-400 mb-1">
            <Coins className="w-4 h-4" />
            <span>Daily Yield</span>
          </div>
          <div className="text-2xl font-bold text-green-400">+{formatTaoShort(portfolio.yield_summary?.daily_yield_tao || 0)} τ</div>
          <div className="text-sm text-gray-500 mt-1">APY: {formatApy(portfolio.yield_summary?.portfolio_apy || 0)}</div>
        </div>

        <div className="bg-gray-800 rounded-lg p-6 border border-gray-700">
          <div className="flex items-center gap-2 text-sm text-gray-400 mb-1">
            <DollarSign className="w-4 h-4" />
            <span>Unrealized P&L</span>
          </div>
          <div className={`text-2xl font-bold ${parseFloat(portfolio.pnl_summary?.total_unrealized_pnl_tao || '0') >= 0 ? 'text-green-400' : 'text-red-400'}`}>
            {formatPercent(portfolio.pnl_summary?.unrealized_pnl_pct || 0)}
          </div>
          <div className="text-sm text-gray-500 mt-1">
            {parseFloat(portfolio.pnl_summary?.total_unrealized_pnl_tao || '0') >= 0 ? '+' : ''}{formatTaoShort(portfolio.pnl_summary?.total_unrealized_pnl_tao || 0)} τ
          </div>
        </div>

        <div className="bg-gray-800 rounded-lg p-6 border border-gray-700">
          <div className="text-sm text-gray-400 mb-1">Weekly Yield</div>
          <div className="text-2xl font-bold text-green-400">+{formatTaoShort(portfolio.yield_summary?.weekly_yield_tao || 0)} τ</div>
          <div className="text-sm text-gray-500 mt-1">~{formatTaoShort(portfolio.yield_summary?.monthly_yield_tao || 0)} τ/month</div>
        </div>
      </div>

      {/* Risk and Regime */}
      <div className="grid grid-cols-1 md:grid-cols-2 gap-4">
        <div className="bg-gray-800 rounded-lg p-6 border border-gray-700">
          <h3 className="text-lg font-semibold mb-4">Risk Metrics</h3>
          <div className="space-y-3">
            <div className="flex justify-between items-center">
              <span className="text-gray-400">Executable Drawdown</span>
              <span className={`font-mono ${parseFloat(portfolio.executable_drawdown_pct) > 10 ? 'text-red-400' : 'text-green-400'}`}>
                {formatPercent(portfolio.executable_drawdown_pct)}
              </span>
            </div>
            <div className="flex justify-between items-center">
              <span className="text-gray-400">Drawdown from ATH</span>
              <span className="font-mono text-yellow-400">
                {formatPercent(portfolio.drawdown_from_ath_pct)}
              </span>
            </div>
            <div className="flex justify-between items-center">
              <span className="text-gray-400">Daily Turnover</span>
              <span className="font-mono">{formatPercent(portfolio.daily_turnover_pct)}</span>
            </div>
            <div className="flex justify-between items-center">
              <span className="text-gray-400">Weekly Turnover</span>
              <span className="font-mono">{formatPercent(portfolio.weekly_turnover_pct)}</span>
            </div>
          </div>
        </div>

        <div className="bg-gray-800 rounded-lg p-6 border border-gray-700">
          <h3 className="text-lg font-semibold mb-4">Allocation</h3>
          <div className="space-y-3">
            <div>
              <div className="flex justify-between text-sm mb-1">
                <span className="text-gray-400">Root (SN0)</span>
                <span>{formatTao(portfolio.allocation.root_tao)} ({parseFloat(portfolio.allocation.root_pct).toFixed(1)}%)</span>
              </div>
              <div className="w-full bg-gray-700 rounded-full h-2">
                <div
                  className="bg-blue-500 h-2 rounded-full"
                  style={{ width: `${Math.min(parseFloat(portfolio.allocation.root_pct), 100)}%` }}
                ></div>
              </div>
            </div>
            <div>
              <div className="flex justify-between text-sm mb-1">
                <span className="text-gray-400">dTAO Sleeve</span>
                <span>{formatTao(portfolio.allocation.dtao_tao)} ({parseFloat(portfolio.allocation.dtao_pct).toFixed(1)}%)</span>
              </div>
              <div className="w-full bg-gray-700 rounded-full h-2">
                <div
                  className="bg-tao-500 h-2 rounded-full"
                  style={{ width: `${Math.min(parseFloat(portfolio.allocation.dtao_pct), 100)}%` }}
                ></div>
              </div>
            </div>
            <div>
              <div className="flex justify-between text-sm mb-1">
                <span className="text-gray-400">Unstaked Buffer</span>
                <span>{formatTao(portfolio.allocation.unstaked_tao)} ({parseFloat(portfolio.allocation.unstaked_pct).toFixed(1)}%)</span>
              </div>
              <div className="w-full bg-gray-700 rounded-full h-2">
                <div
                  className="bg-green-500 h-2 rounded-full"
                  style={{ width: `${Math.min(parseFloat(portfolio.allocation.unstaked_pct), 100)}%` }}
                ></div>
              </div>
            </div>
          </div>
        </div>
      </div>

      {/* Alerts and Actions Summary */}
      <div className="grid grid-cols-1 md:grid-cols-3 gap-4">
        <div className="bg-gray-800 rounded-lg p-6 border border-gray-700">
          <div className="flex items-center gap-3 mb-4">
            <div className={`p-2 rounded-lg ${portfolio.overall_regime === 'risk_on' ? 'bg-green-600/20' : portfolio.overall_regime === 'risk_off' ? 'bg-red-600/20' : 'bg-yellow-600/20'}`}>
              {portfolio.overall_regime === 'risk_on' ? <TrendingUp className="text-green-400" /> :
               portfolio.overall_regime === 'risk_off' ? <TrendingDown className="text-red-400" /> :
               <TrendingUp className="text-yellow-400" />}
            </div>
            <div>
              <div className="text-sm text-gray-400">Overall Regime</div>
              <div className="font-semibold capitalize">{portfolio.overall_regime.replace('_', ' ')}</div>
            </div>
          </div>
          <div className="text-sm text-gray-500">
            {portfolio.active_positions} positions across {portfolio.eligible_subnets} eligible subnets
          </div>
        </div>

        <div className="bg-gray-800 rounded-lg p-6 border border-gray-700">
          <div className="flex items-center gap-3 mb-4">
            <div className={`p-2 rounded-lg ${alerts.critical > 0 ? 'bg-red-600/20' : alerts.warning > 0 ? 'bg-yellow-600/20' : 'bg-green-600/20'}`}>
              <AlertTriangle className={alerts.critical > 0 ? 'text-red-400' : alerts.warning > 0 ? 'text-yellow-400' : 'text-green-400'} />
            </div>
            <div>
              <div className="text-sm text-gray-400">Active Alerts</div>
              <div className="font-semibold">{alerts.critical + alerts.warning + alerts.info}</div>
            </div>
          </div>
          <div className="flex gap-4 text-sm">
            {alerts.critical > 0 && <span className="text-red-400">{alerts.critical} critical</span>}
            {alerts.warning > 0 && <span className="text-yellow-400">{alerts.warning} warning</span>}
            {alerts.info > 0 && <span className="text-blue-400">{alerts.info} info</span>}
            {alerts.critical + alerts.warning + alerts.info === 0 && <span className="text-green-400">All clear</span>}
          </div>
        </div>

        <div className="bg-gray-800 rounded-lg p-6 border border-gray-700">
          <div className="flex items-center gap-3 mb-4">
            <div className={`p-2 rounded-lg ${data.urgent_recommendations > 0 ? 'bg-red-600/20' : 'bg-gray-700'}`}>
              <ArrowRightLeft className={data.urgent_recommendations > 0 ? 'text-red-400' : 'text-gray-400'} />
            </div>
            <div>
              <div className="text-sm text-gray-400">Pending Trades</div>
              <div className="font-semibold">{data.pending_recommendations}</div>
            </div>
          </div>
          <div className="text-sm text-gray-500">
            {data.urgent_recommendations > 0 ? (
              <span className="text-red-400">{data.urgent_recommendations} urgent</span>
            ) : (
              'No urgent actions needed'
            )}
          </div>
        </div>
      </div>

      {/* All Positions Table */}
      {sortedPositions.length > 0 && (
        <div className="bg-gray-800 rounded-lg border border-gray-700 overflow-hidden">
          <div className="px-6 py-4 border-b border-gray-700 flex items-center justify-between">
            <h3 className="text-lg font-semibold">All Positions</h3>
            <span className="text-sm text-gray-500">{sortedPositions.length} positions</span>
          </div>
          <div className="overflow-x-auto">
            <table className="w-full">
              <thead className="bg-gray-900/50">
                <tr>
                  <th className="px-4 py-3 text-left text-xs font-medium text-gray-400 uppercase tracking-wider"></th>
                  <SortableHeader
                    label="Subnet"
                    sortKey="subnet_name"
                    currentSortKey={sortKey}
                    currentDirection={sortDirection}
                    onSort={handleSort}
                  />
                  <SortableHeader
                    label="Value (τ)"
                    sortKey="tao_value_mid"
                    currentSortKey={sortKey}
                    currentDirection={sortDirection}
                    onSort={handleSort}
                    align="right"
                  />
                  <SortableHeader
                    label="Weight"
                    sortKey="weight_pct"
                    currentSortKey={sortKey}
                    currentDirection={sortDirection}
                    onSort={handleSort}
                    align="right"
                  />
                  <SortableHeader
                    label="APY"
                    sortKey="current_apy"
                    currentSortKey={sortKey}
                    currentDirection={sortDirection}
                    onSort={handleSort}
                    align="right"
                  />
                  <SortableHeader
                    label="Daily Yield"
                    sortKey="daily_yield_tao"
                    currentSortKey={sortKey}
                    currentDirection={sortDirection}
                    onSort={handleSort}
                    align="right"
                  />
                  <SortableHeader
                    label="P&L"
                    sortKey="unrealized_pnl_pct"
                    currentSortKey={sortKey}
                    currentDirection={sortDirection}
                    onSort={handleSort}
                    align="right"
                  />
                  <SortableHeader
                    label="Status"
                    sortKey="health_status"
                    currentSortKey={sortKey}
                    currentDirection={sortDirection}
                    onSort={handleSort}
                  />
                </tr>
              </thead>
              <tbody className="divide-y divide-gray-700">
                {sortedPositions.map((position) => (
                  <tr key={position.netuid} className={`hover:bg-gray-700/30 ${
                    position.health_status === 'red' ? 'bg-red-600/5' :
                    position.health_status === 'yellow' ? 'bg-yellow-600/5' : ''
                  }`}>
                    <td className="px-4 py-3">
                      <div
                        className={`w-3 h-3 rounded-full ${
                          position.health_status === 'red' ? 'bg-red-500' :
                          position.health_status === 'yellow' ? 'bg-yellow-500' : 'bg-green-500'
                        }`}
                        title={position.health_reason || 'Healthy'}
                      />
                    </td>
                    <td className="px-4 py-3">
                      <div className="flex items-center">
                        <span className="text-xs text-gray-500 mr-2">SN{position.netuid}</span>
                        <span className="font-medium text-white">{position.subnet_name}</span>
                      </div>
                    </td>
                    <td className="px-4 py-3 text-right font-mono">
                      {formatTaoShort(position.tao_value_mid)}
                    </td>
                    <td className="px-4 py-3 text-right font-mono text-gray-400">
                      {parseFloat(position.weight_pct).toFixed(1)}%
                    </td>
                    <td className="px-4 py-3 text-right font-mono text-green-400">
                      {formatApy(position.current_apy)}
                    </td>
                    <td className="px-4 py-3 text-right font-mono text-green-400">
                      +{formatTaoShort(position.daily_yield_tao)} τ
                    </td>
                    <td className="px-4 py-3 text-right">
                      <span className={`font-mono ${parseFloat(position.unrealized_pnl_pct) >= 0 ? 'text-green-400' : 'text-red-400'}`}>
                        {formatPercent(position.unrealized_pnl_pct)}
                      </span>
                    </td>
                    <td className="px-4 py-3">
                      {position.health_reason ? (
                        <span className="text-xs text-gray-400" title={position.health_reason}>
                          {position.health_reason.length > 30 ? position.health_reason.substring(0, 30) + '...' : position.health_reason}
                        </span>
                      ) : (
                        <span className="text-xs text-green-400">Healthy</span>
                      )}
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        </div>
      )}
    </div>
  )
}
