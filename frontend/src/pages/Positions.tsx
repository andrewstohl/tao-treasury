import { useState, useMemo } from 'react'
import { useQuery } from '@tanstack/react-query'
import { ChevronUp, ChevronDown, ChevronsUpDown } from 'lucide-react'
import { api } from '../services/api'
import { Position } from '../types'

type SortDirection = 'asc' | 'desc' | null
type SortKey = 'subnet_name' | 'tao_value_mid' | 'weight_pct' | 'current_apy' | 'unrealized_pnl_pct' | 'flow_regime' | null

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

export default function Positions() {
  const [sortKey, setSortKey] = useState<SortKey>('tao_value_mid')
  const [sortDirection, setSortDirection] = useState<SortDirection>('desc')

  const { data, isLoading, error } = useQuery({
    queryKey: ['positions'],
    queryFn: api.getPositions,
    refetchInterval: 60000,
  })

  const handleSort = (key: SortKey) => {
    if (sortKey === key) {
      // Toggle direction or reset
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
    const positions: Position[] = data?.positions || []
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
        case 'unrealized_pnl_pct':
          aVal = parseFloat(a.unrealized_pnl_pct)
          bVal = parseFloat(b.unrealized_pnl_pct)
          break
        case 'flow_regime':
          aVal = a.flow_regime || 'neutral'
          bVal = b.flow_regime || 'neutral'
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
  }, [data?.positions, sortKey, sortDirection])

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

  return (
    <div className="space-y-6">
      <div className="flex items-center justify-between">
        <h1 className="text-2xl font-bold">Positions</h1>
        <div className="text-sm text-gray-500">
          {sortedPositions.length} positions | Total: {formatTao(data.total_tao_value_mid)} TAO
        </div>
      </div>

      {sortedPositions.length === 0 ? (
        <div className="bg-gray-800 rounded-lg p-8 text-center border border-gray-700">
          <p className="text-gray-400">No positions found. Try refreshing data from TaoStats.</p>
        </div>
      ) : (
        <div className="bg-gray-800 rounded-lg border border-gray-700 overflow-hidden">
          <table className="w-full">
            <thead className="bg-gray-900/50">
              <tr className="text-sm text-gray-400">
                <th className="p-4"></th>
                <SortableHeader
                  label="Subnet"
                  sortKey="subnet_name"
                  currentSortKey={sortKey}
                  currentDirection={sortDirection}
                  onSort={handleSort}
                />
                <SortableHeader
                  label="TAO Value"
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
                  label="APY / Daily Yield"
                  sortKey="current_apy"
                  currentSortKey={sortKey}
                  currentDirection={sortDirection}
                  onSort={handleSort}
                  align="right"
                />
                <SortableHeader
                  label="Unrealized P&L"
                  sortKey="unrealized_pnl_pct"
                  currentSortKey={sortKey}
                  currentDirection={sortDirection}
                  onSort={handleSort}
                  align="right"
                />
                <SortableHeader
                  label="Flow Regime"
                  sortKey="flow_regime"
                  currentSortKey={sortKey}
                  currentDirection={sortDirection}
                  onSort={handleSort}
                />
                <th className="p-4">Action</th>
              </tr>
            </thead>
            <tbody className="divide-y divide-gray-700">
              {sortedPositions.map((pos) => (
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
                  <td className="p-4 text-right">
                    <div className="font-mono">{formatTao(pos.tao_value_mid)} τ</div>
                    <div className="text-xs text-gray-500">{formatTao(pos.alpha_balance)} α</div>
                  </td>
                  <td className="p-4 text-right font-mono">{parseFloat(pos.weight_pct).toFixed(1)}%</td>
                  <td className="p-4 text-right">
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
                  <td className="p-4 text-right">
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
