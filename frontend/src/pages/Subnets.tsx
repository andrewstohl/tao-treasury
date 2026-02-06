import { useState, useMemo, useRef, useEffect, useCallback } from 'react'
import { useQuery } from '@tanstack/react-query'
import { ChevronRight, ChevronDown, AlertTriangle, Search, SlidersHorizontal, Columns3 } from 'lucide-react'
import { api } from '../services/api'
import type { EnrichedSubnet, EnrichedSubnetListResponse } from '../types'
import { formatTao, formatCompact } from '../utils/format'
import SortableHeader, { useSortToggle, type SortDirection } from '../components/common/SortableHeader'
import SparklineCell from '../components/common/cells/SparklineCell'
import PriceChangeCell from '../components/common/cells/PriceChangeCell'
import VolumeBar from '../components/common/cells/VolumeBar'
import RegimeBadge from '../components/common/cells/RegimeBadge'
import ViabilityBadge from '../components/common/cells/ViabilityBadge'
import SubnetExpandedRow from '../components/common/SubnetExpandedRow'

type SortKey =
  | 'netuid'
  | 'rank'
  | 'alpha_price_tao'
  | 'price_change_24h'
  | 'market_cap_tao'
  | 'tao_volume_24h'
  | 'emission_share'
  | 'pool_tao_reserve'
  | 'validator_apy'
  | 'incentive_burn'
  | 'flow_regime'
  | 'viability_score'

// --- Column visibility ---
type ColumnKey =
  | 'sparkline'
  | 'price'
  | 'change'
  | 'mktcap'
  | 'volume'
  | 'emission'
  | 'liquidity'
  | 'apy'
  | 'burn'
  | 'regime'
  | 'viability'
  | 'status'

const ALL_COLUMNS: { key: ColumnKey; label: string }[] = [
  { key: 'sparkline', label: '7d Chart' },
  { key: 'price', label: 'Price' },
  { key: 'change', label: '24h / 7d' },
  { key: 'mktcap', label: 'Mkt Cap' },
  { key: 'volume', label: 'Volume 24h' },
  { key: 'emission', label: 'Emission' },
  { key: 'liquidity', label: 'Liquidity' },
  { key: 'apy', label: 'APY' },
  { key: 'burn', label: 'Burn Rate' },
  { key: 'regime', label: 'Regime' },
  { key: 'viability', label: 'Viability' },
  { key: 'status', label: 'Status' },
]

const COLUMNS_STORAGE_KEY = 'tao-subnets-columns'
const ALL_COLUMN_KEYS = ALL_COLUMNS.map((c) => c.key)

function loadVisibleColumns(): Set<ColumnKey> {
  const allKeys = new Set(ALL_COLUMN_KEYS)
  try {
    const stored = localStorage.getItem(COLUMNS_STORAGE_KEY)
    if (stored) {
      const parsed: string[] = JSON.parse(stored)
      if (Array.isArray(parsed) && parsed.length > 0) {
        // Keep only keys that still exist, and auto-show any newly added columns
        const valid = new Set(parsed.filter((k) => allKeys.has(k as ColumnKey)) as ColumnKey[])
        for (const key of ALL_COLUMN_KEYS) {
          if (!valid.has(key)) valid.add(key)
        }
        return valid
      }
    }
  } catch {
    // ignore
  }
  return new Set(ALL_COLUMN_KEYS)
}

function saveVisibleColumns(cols: Set<ColumnKey>) {
  localStorage.setItem(COLUMNS_STORAGE_KEY, JSON.stringify([...cols]))
}

// --- Filter types ---
type RegimeFilter = 'all' | 'risk_on' | 'neutral' | 'risk_off' | 'quarantine' | 'dead'
type ViabilityFilter = 'all' | 'tier_1' | 'tier_2' | 'tier_3' | 'tier_4'

export default function Subnets() {
  const [eligibleOnly, setEligibleOnly] = useState(false)
  const [sortKey, setSortKey] = useState<SortKey | null>('netuid')
  const [sortDirection, setSortDirection] = useState<SortDirection>('asc')
  const [expandedNetuid, setExpandedNetuid] = useState<number | null>(null)

  // Search & filters
  const [searchQuery, setSearchQuery] = useState('')
  const [regimeFilter, setRegimeFilter] = useState<RegimeFilter>('all')
  const [viabilityFilter, setViabilityFilter] = useState<ViabilityFilter>('all')

  // Column visibility
  const [visibleColumns, setVisibleColumns] = useState<Set<ColumnKey>>(loadVisibleColumns)
  const [showColumnMenu, setShowColumnMenu] = useState(false)
  const columnMenuRef = useRef<HTMLDivElement>(null)

  const handleSort = useSortToggle(sortKey, sortDirection, setSortKey, setSortDirection)

  const toggleColumn = useCallback((key: ColumnKey) => {
    setVisibleColumns((prev) => {
      const next = new Set(prev)
      if (next.has(key)) {
        next.delete(key)
      } else {
        next.add(key)
      }
      saveVisibleColumns(next)
      return next
    })
  }, [])

  const isColVisible = useCallback(
    (key: ColumnKey) => visibleColumns.has(key),
    [visibleColumns],
  )

  // Close column menu on outside click
  useEffect(() => {
    function handleClickOutside(e: MouseEvent) {
      if (columnMenuRef.current && !columnMenuRef.current.contains(e.target as Node)) {
        setShowColumnMenu(false)
      }
    }
    if (showColumnMenu) {
      document.addEventListener('mousedown', handleClickOutside)
      return () => document.removeEventListener('mousedown', handleClickOutside)
    }
  }, [showColumnMenu])

  const { data, isLoading, error, isFetching } = useQuery<EnrichedSubnetListResponse>({
    queryKey: ['subnets-enriched', eligibleOnly],
    queryFn: () => api.getEnrichedSubnets(eligibleOnly),
    refetchInterval: 120000,
  })

  // Filter -> sort pipeline
  const filteredAndSorted = useMemo(() => {
    let subnets: EnrichedSubnet[] = data?.subnets || []

    // Text search
    if (searchQuery.trim()) {
      const q = searchQuery.trim().toLowerCase()
      subnets = subnets.filter(
        (s) =>
          s.name.toLowerCase().includes(q) ||
          String(s.netuid).includes(q),
      )
    }

    // Regime filter
    if (regimeFilter !== 'all') {
      subnets = subnets.filter((s) => s.flow_regime === regimeFilter)
    }

    // Viability tier filter
    if (viabilityFilter !== 'all') {
      subnets = subnets.filter((s) => s.viability_tier === viabilityFilter)
    }

    // Sort
    if (!sortKey || !sortDirection) return subnets

    return [...subnets].sort((a, b) => {
      let aVal: number | string
      let bVal: number | string

      switch (sortKey) {
        case 'netuid':
          aVal = a.netuid
          bVal = b.netuid
          break
        case 'rank':
          if (a.rank == null && b.rank == null) return 0
          if (a.rank == null) return 1
          if (b.rank == null) return -1
          aVal = a.rank
          bVal = b.rank
          break
        case 'alpha_price_tao':
          aVal = parseFloat(a.alpha_price_tao)
          bVal = parseFloat(b.alpha_price_tao)
          break
        case 'price_change_24h':
          aVal = a.volatile?.price_change_24h ?? -Infinity
          bVal = b.volatile?.price_change_24h ?? -Infinity
          break
        case 'market_cap_tao':
          aVal = parseFloat(a.market_cap_tao)
          bVal = parseFloat(b.market_cap_tao)
          break
        case 'tao_volume_24h':
          aVal = a.volatile?.tao_volume_24h ?? -Infinity
          bVal = b.volatile?.tao_volume_24h ?? -Infinity
          break
        case 'emission_share':
          aVal = parseFloat(a.emission_share)
          bVal = parseFloat(b.emission_share)
          break
        case 'pool_tao_reserve':
          aVal = parseFloat(a.pool_tao_reserve)
          bVal = parseFloat(b.pool_tao_reserve)
          break
        case 'validator_apy':
          aVal = parseFloat(a.validator_apy)
          bVal = parseFloat(b.validator_apy)
          break
        case 'incentive_burn':
          aVal = parseFloat(a.incentive_burn)
          bVal = parseFloat(b.incentive_burn)
          break
        case 'flow_regime':
          aVal = a.flow_regime
          bVal = b.flow_regime
          break
        case 'viability_score':
          aVal = a.viability_score != null ? parseFloat(a.viability_score) : -Infinity
          bVal = b.viability_score != null ? parseFloat(b.viability_score) : -Infinity
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
  }, [data?.subnets, searchQuery, regimeFilter, viabilityFilter, sortKey, sortDirection])

  // Compute colSpan: expand(1) + subnet(1) + visible optional columns
  const colSpan = 2 + visibleColumns.size

  const hasActiveFilters = searchQuery.trim() !== '' || regimeFilter !== 'all' || viabilityFilter !== 'all'

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
    <div className="space-y-4">
      {/* Header */}
      <div className="flex items-center justify-between">
        <div className="flex items-center gap-3">
          <h1 className="text-2xl font-bold">Subnets</h1>
          {isFetching && (
            <div className="animate-spin rounded-full h-4 w-4 border-b-2 border-tao-400"></div>
          )}
          {data.cache_age_seconds != null && (
            <span className="text-xs text-gray-500">
              Data: {data.cache_age_seconds}s ago
            </span>
          )}
        </div>
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

      {/* TaoStats degraded banner */}
      {data.taostats_available === false && (
        <div className="flex items-center gap-2 bg-yellow-900/20 border border-yellow-700/50 rounded-lg px-4 py-2 text-sm text-yellow-400">
          <AlertTriangle className="w-4 h-4 flex-shrink-0" />
          <span>Live market data temporarily unavailable. Showing cached data only.</span>
        </div>
      )}

      {/* Search & Filters Bar */}
      <div className="flex items-center gap-3 flex-wrap">
        {/* Text search */}
        <div className="relative flex-1 min-w-[200px] max-w-xs">
          <Search className="absolute left-4 top-1/2 -translate-y-1/2 w-4 h-4 text-gray-500" />
          <input
            type="text"
            placeholder="Search name or netuid..."
            value={searchQuery}
            onChange={(e) => setSearchQuery(e.target.value)}
            className="w-full pl-10 pr-4 py-2.5 bg-gray-800 border border-gray-700 rounded-lg text-sm text-gray-200 placeholder-gray-500 focus:outline-none focus:border-tao-500"
          />
        </div>

        {/* Regime filter */}
        <div className="flex items-center gap-1.5">
          <SlidersHorizontal className="w-4 h-4 text-gray-500" />
          <select
            value={regimeFilter}
            onChange={(e) => setRegimeFilter(e.target.value as RegimeFilter)}
            className="bg-gray-800 border border-gray-700 rounded-lg text-sm text-gray-300 px-4 py-2.5 focus:outline-none focus:border-tao-500"
          >
            <option value="all">All Regimes</option>
            <option value="risk_on">Risk On</option>
            <option value="neutral">Neutral</option>
            <option value="risk_off">Risk Off</option>
            <option value="quarantine">Quarantine</option>
            <option value="dead">Dead</option>
          </select>
        </div>

        {/* Viability tier filter */}
        <select
          value={viabilityFilter}
          onChange={(e) => setViabilityFilter(e.target.value as ViabilityFilter)}
          className="bg-gray-800 border border-gray-700 rounded-lg text-sm text-gray-300 px-4 py-2.5 focus:outline-none focus:border-tao-500"
        >
          <option value="all">All Viability</option>
          <option value="tier_1">Prime (75+)</option>
          <option value="tier_2">Eligible (55-74)</option>
          <option value="tier_3">Watchlist (40-54)</option>
          <option value="tier_4">Excluded (&lt;40)</option>
        </select>

        {/* Column visibility toggle */}
        <div className="relative" ref={columnMenuRef}>
          <button
            onClick={() => setShowColumnMenu((prev) => !prev)}
            className={`flex items-center gap-1.5 px-4 py-2.5 rounded-lg border text-sm ${
              showColumnMenu
                ? 'bg-gray-700 border-tao-500 text-tao-400'
                : 'bg-gray-800 border-gray-700 text-gray-400 hover:border-gray-600'
            }`}
          >
            <Columns3 className="w-4 h-4" />
            Columns
          </button>
          {showColumnMenu && (
            <div className="absolute right-0 top-full mt-1 bg-gray-800 border border-gray-700 rounded-lg shadow-xl z-20 py-1 w-48">
              {ALL_COLUMNS.map((col) => (
                <label
                  key={col.key}
                  className="flex items-center gap-2 px-3 py-1.5 hover:bg-gray-700 cursor-pointer text-sm text-gray-300"
                >
                  <input
                    type="checkbox"
                    checked={visibleColumns.has(col.key)}
                    onChange={() => toggleColumn(col.key)}
                    className="rounded bg-gray-600 border-gray-500"
                  />
                  {col.label}
                </label>
              ))}
              <div className="border-t border-gray-700 mt-1 pt-1 px-3 pb-1">
                <button
                  onClick={() => {
                    const all = new Set(ALL_COLUMN_KEYS)
                    setVisibleColumns(all)
                    saveVisibleColumns(all)
                  }}
                  className="text-xs text-tao-400 hover:text-tao-300"
                >
                  Show All
                </button>
              </div>
            </div>
          )}
        </div>

        {/* Active filter count + clear */}
        {hasActiveFilters && (
          <button
            onClick={() => {
              setSearchQuery('')
              setRegimeFilter('all')
              setViabilityFilter('all')
            }}
            className="text-xs text-gray-400 hover:text-gray-200 underline"
          >
            Clear filters
          </button>
        )}

        {/* Result count */}
        <span className="text-xs text-gray-500 ml-auto">
          {filteredAndSorted.length} of {data.subnets.length} shown
        </span>
      </div>

      {/* Table */}
      {filteredAndSorted.length === 0 ? (
        <div className="bg-gray-800 rounded-lg p-8 text-center border border-gray-700">
          <p className="text-gray-400">
            {hasActiveFilters
              ? 'No subnets match your filters. Try adjusting or clearing filters.'
              : 'No subnets found. Try refreshing data from TaoStats.'}
          </p>
        </div>
      ) : (
        <div className="bg-gray-800 rounded-lg border border-gray-700 overflow-x-auto">
          <table className="w-full min-w-[900px]">
            <thead className="bg-gray-900/50">
              <tr className="text-sm text-gray-400">
                {/* Expand toggle - always visible */}
                <th className="w-8 px-2 py-3" />
                {/* Subnet - always visible */}
                <SortableHeader<SortKey>
                  label="Subnet"
                  sortKey="netuid"
                  currentSortKey={sortKey}
                  currentDirection={sortDirection}
                  onSort={handleSort}
                />
                {isColVisible('sparkline') && (
                  <th className="px-4 py-3 text-xs font-medium text-gray-400 uppercase tracking-wider">
                    7d Chart
                  </th>
                )}
                {isColVisible('price') && (
                  <SortableHeader<SortKey>
                    label="Price"
                    sortKey="alpha_price_tao"
                    currentSortKey={sortKey}
                    currentDirection={sortDirection}
                    onSort={handleSort}
                    align="right"
                  />
                )}
                {isColVisible('change') && (
                  <SortableHeader<SortKey>
                    label="24h / 7d"
                    sortKey="price_change_24h"
                    currentSortKey={sortKey}
                    currentDirection={sortDirection}
                    onSort={handleSort}
                    align="right"
                  />
                )}
                {isColVisible('mktcap') && (
                  <SortableHeader<SortKey>
                    label="Mkt Cap"
                    sortKey="rank"
                    currentSortKey={sortKey}
                    currentDirection={sortDirection}
                    onSort={handleSort}
                    align="right"
                  />
                )}
                {isColVisible('volume') && (
                  <SortableHeader<SortKey>
                    label="Volume 24h"
                    sortKey="tao_volume_24h"
                    currentSortKey={sortKey}
                    currentDirection={sortDirection}
                    onSort={handleSort}
                    align="right"
                  />
                )}
                {isColVisible('emission') && (
                  <SortableHeader<SortKey>
                    label="Emission"
                    sortKey="emission_share"
                    currentSortKey={sortKey}
                    currentDirection={sortDirection}
                    onSort={handleSort}
                    align="right"
                  />
                )}
                {isColVisible('liquidity') && (
                  <SortableHeader<SortKey>
                    label="Liquidity"
                    sortKey="pool_tao_reserve"
                    currentSortKey={sortKey}
                    currentDirection={sortDirection}
                    onSort={handleSort}
                    align="right"
                  />
                )}
                {isColVisible('apy') && (
                  <SortableHeader<SortKey>
                    label="APY"
                    sortKey="validator_apy"
                    currentSortKey={sortKey}
                    currentDirection={sortDirection}
                    onSort={handleSort}
                    align="right"
                  />
                )}
                {isColVisible('burn') && (
                  <SortableHeader<SortKey>
                    label="Burn Rate"
                    sortKey="incentive_burn"
                    currentSortKey={sortKey}
                    currentDirection={sortDirection}
                    onSort={handleSort}
                    align="right"
                  />
                )}
                {isColVisible('regime') && (
                  <SortableHeader<SortKey>
                    label="Regime"
                    sortKey="flow_regime"
                    currentSortKey={sortKey}
                    currentDirection={sortDirection}
                    onSort={handleSort}
                  />
                )}
                {isColVisible('viability') && (
                  <SortableHeader<SortKey>
                    label="Viability"
                    sortKey="viability_score"
                    currentSortKey={sortKey}
                    currentDirection={sortDirection}
                    onSort={handleSort}
                  />
                )}
                {isColVisible('status') && (
                  <th className="px-4 py-3 text-xs font-medium text-gray-400 uppercase tracking-wider text-left">
                    Status
                  </th>
                )}
              </tr>
            </thead>
            <tbody className="divide-y divide-gray-700">
              {filteredAndSorted.map((subnet) => {
                const isExpanded = expandedNetuid === subnet.netuid
                return (
                  <SubnetRow
                    key={subnet.id}
                    subnet={subnet}
                    isExpanded={isExpanded}
                    onToggle={() =>
                      setExpandedNetuid(isExpanded ? null : subnet.netuid)
                    }
                    isColVisible={isColVisible}
                    colSpan={colSpan}
                  />
                )
              })}
            </tbody>
          </table>
        </div>
      )}
    </div>
  )
}

function SubnetRow({
  subnet,
  isExpanded,
  onToggle,
  isColVisible,
  colSpan,
}: {
  subnet: EnrichedSubnet
  isExpanded: boolean
  onToggle: () => void
  isColVisible: (key: ColumnKey) => boolean
  colSpan: number
}) {
  const v = subnet.volatile

  return (
    <>
      <tr
        className="hover:bg-gray-700/30 cursor-pointer"
        onClick={onToggle}
      >
        {/* Expand chevron */}
        <td className="px-2 py-3 text-gray-500">
          {isExpanded ? (
            <ChevronDown className="w-4 h-4" />
          ) : (
            <ChevronRight className="w-4 h-4" />
          )}
        </td>

        {/* Subnet name + logo */}
        <td className="px-4 py-3">
          <div className="flex items-center gap-2">
            {subnet.identity?.logo_url && (
              <img
                src={subnet.identity.logo_url}
                alt=""
                className="w-6 h-6 rounded-full flex-shrink-0 bg-gray-700"
                onError={(e) => { (e.target as HTMLImageElement).style.display = 'none' }}
              />
            )}
            <div className="min-w-0">
              <div className="font-medium text-sm">{subnet.name}</div>
              <div className="text-xs text-gray-500">SN{subnet.netuid}</div>
            </div>
          </div>
        </td>

        {/* 7d Sparkline */}
        {isColVisible('sparkline') && (
          <td className="px-2 py-3 align-middle">
            <SparklineCell data={v?.sparkline_7d} />
          </td>
        )}

        {/* Price */}
        {isColVisible('price') && (
          <td className="px-4 py-3 text-right tabular-nums text-sm">
            {parseFloat(subnet.alpha_price_tao).toFixed(6)} τ
          </td>
        )}

        {/* 24h / 7d Change */}
        {isColVisible('change') && (
          <td className="px-4 py-3">
            <PriceChangeCell
              change24h={v?.price_change_24h}
              change7d={v?.price_change_7d}
            />
          </td>
        )}

        {/* Market Cap + Rank */}
        {isColVisible('mktcap') && (
          <td className="px-4 py-3 text-right">
            {subnet.rank != null && (
              <div className="text-xs text-gray-500 tabular-nums">#{subnet.rank}</div>
            )}
            <div className="tabular-nums text-sm">
              {parseFloat(subnet.market_cap_tao) > 0
                ? formatCompact(parseFloat(subnet.market_cap_tao)) + ' τ'
                : '--'}
            </div>
          </td>
        )}

        {/* 24h Volume */}
        {isColVisible('volume') && (
          <td className="px-4 py-3">
            <VolumeBar
              volume24h={v?.tao_volume_24h}
              buyVolume={v?.tao_buy_volume_24h}
              sellVolume={v?.tao_sell_volume_24h}
            />
          </td>
        )}

        {/* Emission */}
        {isColVisible('emission') && (
          <td className="px-4 py-3 text-right tabular-nums text-sm">
            {(parseFloat(subnet.emission_share) * 100).toFixed(2)}%
          </td>
        )}

        {/* Liquidity */}
        {isColVisible('liquidity') && (
          <td className="px-4 py-3 text-right tabular-nums text-sm">
            {formatTao(subnet.pool_tao_reserve)} τ
          </td>
        )}

        {/* APY */}
        {isColVisible('apy') && (
          <td className="px-4 py-3 text-right tabular-nums text-sm">
            {parseFloat(subnet.validator_apy).toFixed(1)}%
          </td>
        )}

        {/* Burn Rate */}
        {isColVisible('burn') && (() => {
          const burn = parseFloat(subnet.incentive_burn)
          const burnPct = (burn * 100).toFixed(0)
          return (
            <td className="px-4 py-3 text-right tabular-nums text-sm">
              <span className={burn >= 1 ? 'text-red-400' : burn >= 0.5 ? 'text-yellow-400' : 'text-gray-300'}>
                {burnPct}%
              </span>
            </td>
          )
        })()}

        {/* Regime */}
        {isColVisible('regime') && (
          <td className="px-4 py-3">
            <RegimeBadge regime={subnet.flow_regime} />
          </td>
        )}

        {/* Viability */}
        {isColVisible('viability') && (
          <td className="px-4 py-3">
            <ViabilityBadge tier={subnet.viability_tier} score={subnet.viability_score} />
          </td>
        )}

        {/* Status */}
        {isColVisible('status') && (
          <td className="px-4 py-3">
            {subnet.is_eligible ? (
              <span className="px-2 py-0.5 rounded text-xs font-medium bg-green-600/20 text-green-400">
                Eligible
              </span>
            ) : (
              <span className="px-2 py-0.5 rounded text-xs font-medium bg-red-600/20 text-red-400">
                Excluded
              </span>
            )}
          </td>
        )}
      </tr>

      {/* Expanded detail row */}
      {isExpanded && (
        <tr>
          <td colSpan={colSpan} className="p-0">
            <SubnetExpandedRow
              volatile={v}
              identity={subnet.identity}
              ownerAddress={subnet.owner_address}
              ownerTake={subnet.owner_take}
              feeRate={subnet.fee_rate}
              incentiveBurn={subnet.incentive_burn}
              ageDays={subnet.age_days}
              holderCount={subnet.holder_count}
              ineligibilityReasons={subnet.ineligibility_reasons}
              taoflow1d={subnet.taoflow_1d}
              taoflow3d={subnet.taoflow_3d}
              taoflow7d={subnet.taoflow_7d}
              taoflow14d={subnet.taoflow_14d}
              viabilityScore={subnet.viability_score}
              viabilityTier={subnet.viability_tier}
              viabilityFactors={subnet.viability_factors}
            />
          </td>
        </tr>
      )}
    </>
  )
}
