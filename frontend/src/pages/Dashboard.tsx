import { useQuery } from '@tanstack/react-query'
import { TrendingUp, TrendingDown, AlertTriangle, ArrowRightLeft } from 'lucide-react'
import { api } from '../services/api'
import { Dashboard as DashboardType } from '../types'

function formatTao(value: string | number): string {
  const num = typeof value === 'string' ? parseFloat(value) : value
  return num.toLocaleString(undefined, { minimumFractionDigits: 2, maximumFractionDigits: 4 })
}

function formatPercent(value: string | number): string {
  const num = typeof value === 'string' ? parseFloat(value) : value
  return `${num >= 0 ? '+' : ''}${num.toFixed(2)}%`
}

function formatUsd(value: string | number): string {
  const num = typeof value === 'string' ? parseFloat(value) : value
  return `$${num.toLocaleString(undefined, { minimumFractionDigits: 2, maximumFractionDigits: 2 })}`
}

export default function Dashboard() {
  const { data, isLoading, error } = useQuery<DashboardType>({
    queryKey: ['dashboard'],
    queryFn: api.getDashboard,
    refetchInterval: 30000,
  })

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

  const { portfolio, alerts } = data

  return (
    <div className="space-y-6">
      <div className="flex items-center justify-between">
        <h1 className="text-2xl font-bold">Dashboard</h1>
        <div className="text-sm text-gray-500">
          Last updated: {new Date(data.generated_at).toLocaleTimeString()}
        </div>
      </div>

      {/* NAV Cards */}
      <div className="grid grid-cols-1 md:grid-cols-3 gap-4">
        <div className="bg-gray-800 rounded-lg p-6 border border-gray-700">
          <div className="text-sm text-gray-400 mb-1">Total NAV (TAO)</div>
          <div className="text-3xl font-bold text-white">{formatTao(portfolio.nav_mid)}</div>
          <div className="text-sm text-gray-500 mt-1">{formatUsd(portfolio.nav_usd)} USD</div>
        </div>

        <div className="bg-gray-800 rounded-lg p-6 border border-gray-700">
          <div className="text-sm text-gray-400 mb-1">Executable NAV (50%)</div>
          <div className="text-2xl font-bold text-white">{formatTao(portfolio.nav_exec_50pct)}</div>
          <div className="text-sm text-gray-500 mt-1">Primary risk metric</div>
        </div>

        <div className="bg-gray-800 rounded-lg p-6 border border-gray-700">
          <div className="text-sm text-gray-400 mb-1">Executable NAV (100%)</div>
          <div className="text-2xl font-bold text-white">{formatTao(portfolio.nav_exec_100pct)}</div>
          <div className="text-sm text-gray-500 mt-1">Full exit valuation</div>
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
    </div>
  )
}
