import { useState, useMemo } from 'react'
import { useQuery } from '@tanstack/react-query'
import { ChevronUp, ChevronDown, ChevronsUpDown } from 'lucide-react'
import { api } from '../services/api'
import { Subnet } from '../types'

type SortDirection = 'asc' | 'desc' | null
type SortKey = 'name' | 'emission_share' | 'pool_tao_reserve' | 'holder_count' | 'taoflow_7d' | 'flow_regime' | 'validator_apy' | null

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
      className={`p-4 cursor-pointer hover:bg-gray-700/50 select-none ${align === 'right' ? 'text-right' : 'text-left'}`}
      onClick={() => onSort(sortKey)}
    >
      <div className={`flex items-center gap-1 ${align === 'right' ? 'justify-end' : ''}`}>
        <span>{label}</span>
        <span className="text-gray-500">
          {isActive ? (
            currentDirection === 'asc' ? <ChevronUp className="w-4 h-4" /> : <ChevronDown className="w-4 h-4" />
          ) : (
            <ChevronsUpDown className="w-4 h-4 opacity-50" />
          )}
        </span>
      </div>
    </th>
  )
}

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
  const [sortKey, setSortKey] = useState<SortKey>('emission_share')
  const [sortDirection, setSortDirection] = useState<SortDirection>('desc')

  const { data, isLoading, error } = useQuery({
    queryKey: ['subnets', eligibleOnly],
    queryFn: () => api.getSubnets(eligibleOnly),
    refetchInterval: 120000,
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

  const sortedSubnets = useMemo(() => {
    const subnets: Subnet[] = data?.subnets || []
    if (!sortKey || !sortDirection) return subnets

    return [...subnets].sort((a, b) => {
      let aVal: number | string
      let bVal: number | string

      switch (sortKey) {
        case 'name':
          aVal = a.name
          bVal = b.name
          break
        case 'emission_share':
          aVal = parseFloat(a.emission_share)
          bVal = parseFloat(b.emission_share)
          break
        case 'pool_tao_reserve':
          aVal = parseFloat(a.pool_tao_reserve)
          bVal = parseFloat(b.pool_tao_reserve)
          break
        case 'holder_count':
          aVal = a.holder_count
          bVal = b.holder_count
          break
        case 'taoflow_7d':
          aVal = parseFloat(a.taoflow_7d)
          bVal = parseFloat(b.taoflow_7d)
          break
        case 'flow_regime':
          aVal = a.flow_regime
          bVal = b.flow_regime
          break
        case 'validator_apy':
          aVal = parseFloat(a.validator_apy)
          bVal = parseFloat(b.validator_apy)
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
  }, [data?.subnets, sortKey, sortDirection])

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

      {sortedSubnets.length === 0 ? (
        <div className="bg-gray-800 rounded-lg p-8 text-center border border-gray-700">
          <p className="text-gray-400">No subnets found. Try refreshing data from TaoStats.</p>
        </div>
      ) : (
        <div className="bg-gray-800 rounded-lg border border-gray-700 overflow-hidden">
          <table className="w-full">
            <thead className="bg-gray-900/50">
              <tr className="text-sm text-gray-400">
                <SortableHeader
                  label="Subnet"
                  sortKey="name"
                  currentSortKey={sortKey}
                  currentDirection={sortDirection}
                  onSort={handleSort}
                />
                <SortableHeader
                  label="Emission"
                  sortKey="emission_share"
                  currentSortKey={sortKey}
                  currentDirection={sortDirection}
                  onSort={handleSort}
                  align="right"
                />
                <SortableHeader
                  label="Liquidity"
                  sortKey="pool_tao_reserve"
                  currentSortKey={sortKey}
                  currentDirection={sortDirection}
                  onSort={handleSort}
                  align="right"
                />
                <SortableHeader
                  label="Holders"
                  sortKey="holder_count"
                  currentSortKey={sortKey}
                  currentDirection={sortDirection}
                  onSort={handleSort}
                  align="right"
                />
                <SortableHeader
                  label="7d Flow"
                  sortKey="taoflow_7d"
                  currentSortKey={sortKey}
                  currentDirection={sortDirection}
                  onSort={handleSort}
                  align="right"
                />
                <SortableHeader
                  label="Regime"
                  sortKey="flow_regime"
                  currentSortKey={sortKey}
                  currentDirection={sortDirection}
                  onSort={handleSort}
                />
                <SortableHeader
                  label="APY"
                  sortKey="validator_apy"
                  currentSortKey={sortKey}
                  currentDirection={sortDirection}
                  onSort={handleSort}
                  align="right"
                />
                <th className="p-4 text-left">Status</th>
              </tr>
            </thead>
            <tbody className="divide-y divide-gray-700">
              {sortedSubnets.map((subnet) => (
                <tr key={subnet.id} className="hover:bg-gray-700/30">
                  <td className="p-4">
                    <div className="font-medium">{subnet.name}</div>
                    <div className="text-xs text-gray-500">SN{subnet.netuid} | {subnet.age_days}d old</div>
                  </td>
                  <td className="p-4 text-right font-mono text-sm">
                    {formatPercent(parseFloat(subnet.emission_share) * 100)}
                  </td>
                  <td className="p-4 text-right font-mono text-sm">{formatTao(subnet.pool_tao_reserve)} τ</td>
                  <td className="p-4 text-right font-mono text-sm">{subnet.holder_count}</td>
                  <td className="p-4 text-right">
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
                  <td className="p-4 text-right font-mono text-sm">
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
