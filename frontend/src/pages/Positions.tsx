import { useQuery } from '@tanstack/react-query'
import { api } from '../services/api'
import { Position } from '../types'

function formatTao(value: string | number): string {
  const num = typeof value === 'string' ? parseFloat(value) : value
  return num.toLocaleString(undefined, { minimumFractionDigits: 2, maximumFractionDigits: 4 })
}

function formatPercent(value: string | number): string {
  const num = typeof value === 'string' ? parseFloat(value) : value
  return `${num >= 0 ? '+' : ''}${num.toFixed(2)}%`
}

function getRegimeColor(regime: string | null): string {
  switch (regime) {
    case 'risk_on': return 'text-green-400'
    case 'risk_off': return 'text-red-400'
    case 'quarantine': return 'text-orange-400'
    case 'dead': return 'text-red-600'
    default: return 'text-yellow-400'
  }
}

function getHealthColor(status: string): string {
  switch (status) {
    case 'green': return 'bg-green-500'
    case 'yellow': return 'bg-yellow-500'
    case 'red': return 'bg-red-500'
    default: return 'bg-gray-500'
  }
}

function getHealthBgColor(status: string): string {
  switch (status) {
    case 'green': return 'bg-green-600/10 border-green-600/30'
    case 'yellow': return 'bg-yellow-600/10 border-yellow-600/30'
    case 'red': return 'bg-red-600/10 border-red-600/30'
    default: return ''
  }
}

export default function Positions() {
  const { data, isLoading, error } = useQuery({
    queryKey: ['positions'],
    queryFn: api.getPositions,
    refetchInterval: 60000,
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
        <p className="text-red-400">Failed to load positions. Please try refreshing data.</p>
      </div>
    )
  }

  const positions: Position[] = data.positions || []

  return (
    <div className="space-y-6">
      <div className="flex items-center justify-between">
        <h1 className="text-2xl font-bold">Positions</h1>
        <div className="text-sm text-gray-500">
          {positions.length} positions | Total: {formatTao(data.total_tao_value_mid)} TAO
        </div>
      </div>

      {positions.length === 0 ? (
        <div className="bg-gray-800 rounded-lg p-8 text-center border border-gray-700">
          <p className="text-gray-400">No positions found. Try refreshing data from TaoStats.</p>
        </div>
      ) : (
        <div className="bg-gray-800 rounded-lg border border-gray-700 overflow-hidden">
          <table className="w-full">
            <thead className="bg-gray-900/50">
              <tr className="text-left text-sm text-gray-400">
                <th className="p-4"></th>
                <th className="p-4">Subnet</th>
                <th className="p-4">TAO Value</th>
                <th className="p-4">Weight</th>
                <th className="p-4">APY / Daily Yield</th>
                <th className="p-4">Unrealized P&L</th>
                <th className="p-4">Flow Regime</th>
                <th className="p-4">Action</th>
              </tr>
            </thead>
            <tbody className="divide-y divide-gray-700">
              {positions.map((pos) => (
                <tr key={pos.id} className={`hover:bg-gray-700/30 ${getHealthBgColor(pos.health_status)}`}>
                  {/* Health indicator */}
                  <td className="p-4 w-4">
                    <div
                      className={`w-3 h-3 rounded-full ${getHealthColor(pos.health_status)}`}
                      title={pos.health_reason || 'Healthy'}
                    />
                  </td>
                  <td className="p-4">
                    <div className="font-medium">{pos.subnet_name || `SN${pos.netuid}`}</div>
                    <div className="text-xs text-gray-500">netuid: {pos.netuid}</div>
                  </td>
                  <td className="p-4">
                    <div className="font-mono">{formatTao(pos.tao_value_mid)} τ</div>
                    <div className="text-xs text-gray-500">{formatTao(pos.alpha_balance)} α</div>
                  </td>
                  <td className="p-4 font-mono">{parseFloat(pos.weight_pct).toFixed(1)}%</td>
                  <td className="p-4">
                    {pos.current_apy ? (
                      <>
                        <div className="font-mono text-green-400">
                          {parseFloat(pos.current_apy).toFixed(1)}% APY
                        </div>
                        <div className="text-xs text-gray-400">
                          +{pos.daily_yield_tao ? parseFloat(pos.daily_yield_tao).toFixed(4) : '0'} τ/day
                        </div>
                      </>
                    ) : (
                      <span className="text-gray-500">-</span>
                    )}
                  </td>
                  <td className="p-4">
                    <span className={`font-mono ${parseFloat(pos.unrealized_pnl_tao) >= 0 ? 'text-green-400' : 'text-red-400'}`}>
                      {formatTao(pos.unrealized_pnl_tao)} τ
                    </span>
                    <div className={`text-xs ${parseFloat(pos.unrealized_pnl_pct) >= 0 ? 'text-green-400' : 'text-red-400'}`}>
                      {formatPercent(pos.unrealized_pnl_pct)}
                    </div>
                  </td>
                  <td className="p-4">
                    <span className={`capitalize ${getRegimeColor(pos.flow_regime)}`}>
                      {pos.flow_regime?.replace('_', ' ') || 'unknown'}
                    </span>
                  </td>
                  <td className="p-4">
                    {pos.health_reason ? (
                      <div className="text-xs text-gray-400 max-w-[200px]" title={pos.health_reason}>
                        {pos.health_reason}
                      </div>
                    ) : pos.recommended_action ? (
                      <div>
                        <span className={`px-2 py-1 rounded text-xs font-medium ${
                          pos.recommended_action === 'sell' ? 'bg-red-600/20 text-red-400' :
                          pos.recommended_action === 'buy' ? 'bg-green-600/20 text-green-400' :
                          'bg-yellow-600/20 text-yellow-400'
                        }`}>
                          {pos.recommended_action}
                        </span>
                      </div>
                    ) : (
                      <span className="text-green-400 text-sm">Healthy</span>
                    )}
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      )}
    </div>
  )
}
