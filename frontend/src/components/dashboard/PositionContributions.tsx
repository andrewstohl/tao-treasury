import { useState } from 'react'
import { useQuery } from '@tanstack/react-query'
import { Layers } from 'lucide-react'
import { api } from '../../services/api'
import type { Attribution, PositionContribution } from '../../types'
import { formatTao, formatPercent, safeFloat } from '../../utils/format'

const PERIOD_OPTIONS = [
  { days: 1, label: '24h' },
  { days: 7, label: '7d' },
  { days: 30, label: '30d' },
]

export default function PositionContributions() {
  const [days, setDays] = useState(7)

  const { data: attr, isLoading } = useQuery<Attribution>({
    queryKey: ['attribution', days],
    queryFn: () => api.getAttribution(days),
    refetchInterval: 60000,
  })

  if (isLoading) {
    return (
      <div className="bg-gray-800 rounded-lg border border-gray-700 p-6 animate-pulse h-48" />
    )
  }

  if (!attr || attr.position_contributions.length === 0) {
    return (
      <div className="bg-gray-800 rounded-lg border border-gray-700 p-6">
        <div className="text-sm text-gray-500 text-center py-8">
          Position contribution data unavailable.
        </div>
      </div>
    )
  }

  return (
    <div className="space-y-4">
      <div className="flex items-center justify-between">
        <h3 className="text-lg font-semibold flex items-center gap-2">
          <Layers className="w-5 h-5" />
          Position Contributions
        </h3>
        <div className="flex gap-1">
          {PERIOD_OPTIONS.map((opt) => (
            <button
              key={opt.days}
              onClick={() => setDays(opt.days)}
              className={`px-3 py-1 rounded text-xs font-medium transition-colors ${
                days === opt.days
                  ? 'bg-gray-600 text-white'
                  : 'text-gray-500 hover:text-gray-300'
              }`}
            >
              {opt.label}
            </button>
          ))}
        </div>
      </div>

      <div className="bg-gray-800 rounded-lg border border-gray-700 overflow-hidden">
        <div className="overflow-x-auto">
          <table className="w-full">
            <thead className="bg-gray-900/50">
              <tr className="text-xs text-gray-500 uppercase tracking-wider">
                <th className="px-4 py-2 text-left">Subnet</th>
                <th className="px-4 py-2 text-right">Weight</th>
                <th className="px-4 py-2 text-right">Return</th>
                <th className="px-4 py-2 text-right">Yield</th>
                <th className="px-4 py-2 text-right">Price</th>
                <th className="px-4 py-2 text-right">Contribution</th>
              </tr>
            </thead>
            <tbody className="divide-y divide-gray-700">
              {attr.position_contributions.map((pc) => (
                <ContributionRow key={pc.netuid} pc={pc} />
              ))}
            </tbody>
          </table>
        </div>
      </div>
    </div>
  )
}

function ContributionRow({ pc }: { pc: PositionContribution }) {
  const returnVal = safeFloat(pc.return_tao)
  const priceVal = safeFloat(pc.price_effect_tao)
  const contribVal = safeFloat(pc.contribution_pct)

  return (
    <tr className="hover:bg-gray-700/30">
      <td className="px-4 py-2.5">
        <div className="font-medium text-sm">{pc.subnet_name}</div>
        <div className="text-xs text-gray-500">SN{pc.netuid}</div>
      </td>
      <td className="px-4 py-2.5 text-right font-mono text-sm text-gray-400">
        {safeFloat(pc.weight_pct).toFixed(1)}%
      </td>
      <td className="px-4 py-2.5 text-right">
        <span className={`font-mono text-sm ${returnVal >= 0 ? 'text-green-400' : 'text-red-400'}`}>
          {returnVal >= 0 ? '+' : ''}{formatTao(pc.return_tao)} τ
        </span>
        <div className={`text-xs font-mono ${returnVal >= 0 ? 'text-green-400' : 'text-red-400'}`}>
          {formatPercent(pc.return_pct)}
        </div>
      </td>
      <td className="px-4 py-2.5 text-right font-mono text-sm text-green-400">
        +{formatTao(pc.yield_tao)} τ
      </td>
      <td className={`px-4 py-2.5 text-right font-mono text-sm ${priceVal >= 0 ? 'text-green-400' : 'text-red-400'}`}>
        {priceVal >= 0 ? '+' : ''}{formatTao(pc.price_effect_tao)} τ
      </td>
      <td className="px-4 py-2.5 text-right">
        <div className="flex items-center justify-end gap-2">
          <span className={`font-mono text-sm font-semibold ${contribVal >= 0 ? 'text-green-400' : 'text-red-400'}`}>
            {contribVal >= 0 ? '+' : ''}{contribVal.toFixed(2)}%
          </span>
          <div className="w-16 bg-gray-700 rounded-full h-1.5">
            <div
              className={`h-1.5 rounded-full ${contribVal >= 0 ? 'bg-green-500' : 'bg-red-500'}`}
              style={{ width: `${Math.min(Math.abs(contribVal) * 10, 100)}%` }}
            />
          </div>
        </div>
      </td>
    </tr>
  )
}
