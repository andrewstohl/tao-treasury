import { useState } from 'react'
import { useQuery } from '@tanstack/react-query'
import { api } from '../services/api'
import { Subnet } from '../types'

function formatTao(value: string | number): string {
  const num = typeof value === 'string' ? parseFloat(value) : value
  return num.toLocaleString(undefined, { minimumFractionDigits: 2, maximumFractionDigits: 2 })
}

function formatPercent(value: string | number): string {
  const num = typeof value === 'string' ? parseFloat(value) : value
  return `${num.toFixed(4)}%`
}

export default function Subnets() {
  const [eligibleOnly, setEligibleOnly] = useState(false)

  const { data, isLoading, error } = useQuery({
    queryKey: ['subnets', eligibleOnly],
    queryFn: () => api.getSubnets(eligibleOnly),
    refetchInterval: 120000,
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
        <p className="text-red-400">Failed to load subnets. Please try refreshing data.</p>
      </div>
    )
  }

  const subnets: Subnet[] = data.subnets || []

  return (
    <div className="space-y-6">
      <div className="flex items-center justify-between">
        <h1 className="text-2xl font-bold">Subnets</h1>
        <div className="flex items-center gap-4">
          <label className="flex items-center gap-2 cursor-pointer">
            <input
              type="checkbox"
              checked={eligibleOnly}
              onChange={(e) => setEligibleOnly(e.target.checked)}
              className="rounded bg-gray-700 border-gray-600"
            />
            <span className="text-sm text-gray-400">Eligible only</span>
          </label>
          <div className="text-sm text-gray-500">
            {data.eligible_count} eligible / {data.total} total
          </div>
        </div>
      </div>

      {subnets.length === 0 ? (
        <div className="bg-gray-800 rounded-lg p-8 text-center border border-gray-700">
          <p className="text-gray-400">No subnets found. Try refreshing data from TaoStats.</p>
        </div>
      ) : (
        <div className="bg-gray-800 rounded-lg border border-gray-700 overflow-hidden">
          <table className="w-full">
            <thead className="bg-gray-900/50">
              <tr className="text-left text-sm text-gray-400">
                <th className="p-4">Subnet</th>
                <th className="p-4">Emission</th>
                <th className="p-4">Liquidity</th>
                <th className="p-4">Holders</th>
                <th className="p-4">7d Flow</th>
                <th className="p-4">Regime</th>
                <th className="p-4">APY</th>
                <th className="p-4">Status</th>
              </tr>
            </thead>
            <tbody className="divide-y divide-gray-700">
              {subnets.map((subnet) => (
                <tr key={subnet.id} className="hover:bg-gray-700/30">
                  <td className="p-4">
                    <div className="font-medium">{subnet.name}</div>
                    <div className="text-xs text-gray-500">SN{subnet.netuid} | {subnet.age_days}d old</div>
                  </td>
                  <td className="p-4 font-mono text-sm">
                    {formatPercent(parseFloat(subnet.emission_share) * 100)}
                  </td>
                  <td className="p-4 font-mono text-sm">{formatTao(subnet.pool_tao_reserve)} τ</td>
                  <td className="p-4 font-mono text-sm">{subnet.holder_count}</td>
                  <td className="p-4">
                    <span className={`font-mono text-sm ${parseFloat(subnet.taoflow_7d) >= 0 ? 'text-green-400' : 'text-red-400'}`}>
                      {parseFloat(subnet.taoflow_7d) >= 0 ? '+' : ''}{formatTao(subnet.taoflow_7d)} τ
                    </span>
                  </td>
                  <td className="p-4">
                    <span className={`capitalize text-sm ${
                      subnet.flow_regime === 'risk_on' ? 'text-green-400' :
                      subnet.flow_regime === 'risk_off' ? 'text-red-400' :
                      subnet.flow_regime === 'quarantine' ? 'text-orange-400' :
                      'text-yellow-400'
                    }`}>
                      {subnet.flow_regime.replace('_', ' ')}
                    </span>
                  </td>
                  <td className="p-4 font-mono text-sm">
                    {parseFloat(subnet.validator_apy).toFixed(1)}%
                  </td>
                  <td className="p-4">
                    {subnet.is_eligible ? (
                      <span className="px-2 py-1 rounded text-xs font-medium bg-green-600/20 text-green-400">
                        Eligible
                      </span>
                    ) : (
                      <div>
                        <span className="px-2 py-1 rounded text-xs font-medium bg-red-600/20 text-red-400">
                          Excluded
                        </span>
                        {subnet.ineligibility_reasons && (
                          <div className="text-xs text-gray-500 mt-1 max-w-[150px] truncate" title={subnet.ineligibility_reasons}>
                            {subnet.ineligibility_reasons}
                          </div>
                        )}
                      </div>
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
