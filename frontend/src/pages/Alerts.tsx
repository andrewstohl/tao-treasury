import { useState } from 'react'
import { useQuery, useMutation, useQueryClient } from '@tanstack/react-query'
import { AlertTriangle, CheckCircle, XCircle } from 'lucide-react'
import { api } from '../services/api'
import { Alert } from '../types'

export default function Alerts() {
  const [activeOnly, setActiveOnly] = useState(true)
  const queryClient = useQueryClient()

  const { data, isLoading, error } = useQuery({
    queryKey: ['alerts', activeOnly],
    queryFn: () => api.getAlerts(activeOnly),
    refetchInterval: 30000,
  })

  const ackMutation = useMutation({
    mutationFn: ({ alertId, action }: { alertId: number; action: string }) =>
      api.acknowledgeAlert(alertId, action),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ['alerts'] })
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
        <p className="text-red-400">Failed to load alerts.</p>
      </div>
    )
  }

  const alerts: Alert[] = data.alerts || []

  return (
    <div className="space-y-6">
      <div className="flex items-center justify-between">
        <h1 className="text-2xl font-bold">Alerts</h1>
        <div className="flex items-center gap-4">
          <label className="flex items-center gap-2 cursor-pointer">
            <input
              type="checkbox"
              checked={activeOnly}
              onChange={(e) => setActiveOnly(e.target.checked)}
              className="rounded bg-gray-700 border-gray-600"
            />
            <span className="text-sm text-gray-400">Active only</span>
          </label>
          <div className="text-sm text-gray-500">
            {data.active_count} active / {data.total} total
          </div>
        </div>
      </div>

      {/* Summary */}
      <div className="flex gap-4">
        {Object.entries(data.by_severity || {}).map(([severity, count]) => (
          <div
            key={severity}
            className={`px-4 py-2 rounded-lg ${
              severity === 'critical' ? 'bg-red-600/20 text-red-400' :
              severity === 'warning' ? 'bg-yellow-600/20 text-yellow-400' :
              'bg-blue-600/20 text-blue-400'
            }`}
          >
            {String(count)} {severity}
          </div>
        ))}
      </div>

      {alerts.length === 0 ? (
        <div className="bg-gray-800 rounded-lg p-8 text-center border border-gray-700">
          <CheckCircle className="mx-auto text-green-400 mb-4" size={48} />
          <p className="text-gray-400">No active alerts. All clear!</p>
        </div>
      ) : (
        <div className="space-y-4">
          {alerts.map((alert) => (
            <div
              key={alert.id}
              className={`bg-gray-800 rounded-lg p-4 border ${
                alert.severity === 'critical' ? 'border-red-600' :
                alert.severity === 'warning' ? 'border-yellow-600' :
                'border-blue-600'
              }`}
            >
              <div className="flex items-start justify-between">
                <div className="flex items-start gap-3">
                  <AlertTriangle
                    className={
                      alert.severity === 'critical' ? 'text-red-400' :
                      alert.severity === 'warning' ? 'text-yellow-400' :
                      'text-blue-400'
                    }
                    size={20}
                  />
                  <div>
                    <div className="flex items-center gap-2">
                      <span className="font-semibold">{alert.title}</span>
                      <span className={`px-2 py-0.5 rounded text-xs ${
                        alert.severity === 'critical' ? 'bg-red-600/20 text-red-400' :
                        alert.severity === 'warning' ? 'bg-yellow-600/20 text-yellow-400' :
                        'bg-blue-600/20 text-blue-400'
                      }`}>
                        {alert.severity}
                      </span>
                      <span className="text-xs text-gray-500">{alert.category}</span>
                    </div>
                    <p className="text-gray-400 mt-1">{alert.message}</p>
                    <div className="text-xs text-gray-500 mt-2">
                      {new Date(alert.created_at).toLocaleString()}
                      {alert.netuid && ` | SN${alert.netuid}`}
                    </div>
                  </div>
                </div>

                {alert.is_active && !alert.is_acknowledged && (
                  <div className="flex gap-2">
                    <button
                      onClick={() => ackMutation.mutate({ alertId: alert.id, action: 'acknowledged' })}
                      disabled={ackMutation.isPending}
                      className="p-2 rounded bg-gray-700 hover:bg-gray-600 text-gray-300"
                      title="Acknowledge"
                    >
                      <CheckCircle size={16} />
                    </button>
                    <button
                      onClick={() => ackMutation.mutate({ alertId: alert.id, action: 'resolved' })}
                      disabled={ackMutation.isPending}
                      className="p-2 rounded bg-gray-700 hover:bg-gray-600 text-gray-300"
                      title="Resolve"
                    >
                      <XCircle size={16} />
                    </button>
                  </div>
                )}

                {alert.is_acknowledged && (
                  <span className="text-xs text-gray-500">
                    Acknowledged {alert.acknowledged_at && new Date(alert.acknowledged_at).toLocaleDateString()}
                  </span>
                )}
              </div>
            </div>
          ))}
        </div>
      )}
    </div>
  )
}
