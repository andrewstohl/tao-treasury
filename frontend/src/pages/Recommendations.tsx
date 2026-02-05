import { useQuery, useMutation, useQueryClient } from '@tanstack/react-query'
import { ArrowUp, ArrowDown, Check } from 'lucide-react'
import { api } from '../services/api'
import { Recommendation } from '../types'

function formatTao(value: string | number): string {
  const num = typeof value === 'string' ? parseFloat(value) : value
  return num.toLocaleString(undefined, { minimumFractionDigits: 2, maximumFractionDigits: 4 })
}

export default function Recommendations() {
  const queryClient = useQueryClient()

  const { data, isLoading, error } = useQuery({
    queryKey: ['recommendations'],
    queryFn: () => api.getRecommendations('pending'),
    refetchInterval: 30000,
  })

  const markExecutedMutation = useMutation({
    mutationFn: (recId: number) => api.markExecuted(recId),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ['recommendations'] })
      queryClient.invalidateQueries({ queryKey: ['positions'] })
      queryClient.invalidateQueries({ queryKey: ['dashboard'] })
    },
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
        <p className="text-red-400">Failed to load recommendations.</p>
      </div>
    )
  }

  const recommendations: Recommendation[] = data.recommendations || []

  return (
    <div className="space-y-6">
      <div className="flex items-center justify-between">
        <h1 className="text-2xl font-bold">Trade Recommendations</h1>
        <div className="text-sm text-gray-500">
          {data.pending_count} pending | Est. cost: {formatTao(data.total_estimated_cost_tao)} TAO
        </div>
      </div>

      {recommendations.length === 0 ? (
        <div className="bg-gray-800 rounded-lg p-8 text-center border border-gray-700">
          <p className="text-gray-400">No pending trade recommendations.</p>
        </div>
      ) : (
        <div className="space-y-4">
          {recommendations.map((rec) => (
            <div
              key={rec.id}
              className={`bg-gray-800 rounded-lg p-6 border ${
                rec.is_urgent ? 'border-red-600' : 'border-gray-700'
              }`}
            >
              <div className="flex items-start justify-between">
                <div className="flex items-start gap-4">
                  <div className={`p-3 rounded-lg ${
                    rec.direction === 'buy' ? 'bg-green-600/20' : 'bg-red-600/20'
                  }`}>
                    {rec.direction === 'buy' ? (
                      <ArrowUp className="text-green-400" size={24} />
                    ) : (
                      <ArrowDown className="text-red-400" size={24} />
                    )}
                  </div>

                  <div>
                    <div className="flex items-center gap-2">
                      <span className="font-semibold text-lg capitalize">{rec.direction}</span>
                      <span className="text-gray-400">{rec.subnet_name || `SN${rec.netuid}`}</span>
                      {rec.is_urgent && (
                        <span className="px-2 py-0.5 rounded text-xs bg-red-600/20 text-red-400">
                          URGENT
                        </span>
                      )}
                      {rec.tranche_number && (
                        <span className="px-2 py-0.5 rounded text-xs bg-gray-700 text-gray-400">
                          Tranche {rec.tranche_number}/{rec.total_tranches}
                        </span>
                      )}
                    </div>

                    <div className="grid grid-cols-2 md:grid-cols-4 gap-4 mt-4 text-sm">
                      <div>
                        <div className="text-gray-500">Size (TAO)</div>
                        <div className="tabular-nums">{formatTao(rec.size_tao)}</div>
                      </div>
                      <div>
                        <div className="text-gray-500">Size (Alpha)</div>
                        <div className="tabular-nums">{formatTao(rec.size_alpha)}</div>
                      </div>
                      <div>
                        <div className="text-gray-500">Est. Slippage</div>
                        <div className={`tabular-nums ${parseFloat(rec.estimated_slippage_pct) > 5 ? 'text-red-400' : ''}`}>
                          {parseFloat(rec.estimated_slippage_pct).toFixed(2)}%
                        </div>
                      </div>
                      <div>
                        <div className="text-gray-500">Est. Cost</div>
                        <div className="tabular-nums">{formatTao(rec.total_estimated_cost_tao)} τ</div>
                      </div>
                    </div>

                    <div className="mt-4">
                      <div className="text-xs text-gray-500 mb-1">
                        Trigger: <span className="text-gray-400">{rec.trigger_type}</span>
                      </div>
                      <p className="text-sm text-gray-400">{rec.reason}</p>
                    </div>
                  </div>
                </div>

                <div className="flex flex-col items-end gap-2">
                  <div className="text-xs text-gray-500">
                    Priority: {rec.priority}
                  </div>
                  <button
                    onClick={() => markExecutedMutation.mutate(rec.id)}
                    disabled={markExecutedMutation.isPending}
                    className="flex items-center gap-2 px-4 py-2 bg-tao-600 hover:bg-tao-500 rounded text-white text-sm disabled:opacity-50"
                  >
                    <Check size={16} />
                    Mark Executed
                  </button>
                </div>
              </div>
            </div>
          ))}
        </div>
      )}
    </div>
  )
}
