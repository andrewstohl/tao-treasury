import { useState, useMemo } from 'react'
import { useQuery } from '@tanstack/react-query'
import { Search, ChevronRight, ChevronDown, Compass } from 'lucide-react'
import { supabase } from '../services/supabase'
import { formatTao, formatCompact } from '../utils/format'
import SortableHeader, { useSortToggle, type SortDirection } from '../components/common/SortableHeader'

// Extended SubnetProfile interface with additional fields from subnet_profiles table
interface SubnetProfile {
  id?: number
  netuid: number
  subnet_name: string | null
  alpha_price: number | null
  market_cap: number | null
  pool_tao_reserve: number | null
  emission_share: number | null
  category: 'Core' | 'Growth' | 'Speculative' | 'Dead' | string | null
  eligible: boolean | null
  age_days: number | null
  holder_count: number | null
  owner_take: number | null
  taoflow_1d: number | null
  taoflow_3d: number | null
  taoflow_7d: number | null
  taoflow_14d: number | null
  ineligibility_reason: string | null
  created_at?: string
  updated_at?: string
}

type SortKey =
  | 'netuid'
  | 'subnet_name'
  | 'alpha_price'
  | 'market_cap'
  | 'pool_tao_reserve'
  | 'emission_share'
  | 'taoflow_7d'
  | 'category'
  | 'eligible'

type CategoryFilter = 'all' | 'Core' | 'Growth' | 'Speculative' | 'Dead'
type EligibleFilter = 'all' | 'eligible' | 'ineligible'

export default function Discover() {
  const [searchQuery, setSearchQuery] = useState('')
  const [categoryFilter, setCategoryFilter] = useState<CategoryFilter>('all')
  const [eligibleFilter, setEligibleFilter] = useState<EligibleFilter>('all')
  const [sortKey, setSortKey] = useState<SortKey | null>('netuid')
  const [sortDirection, setSortDirection] = useState<SortDirection>('asc')
  const [expandedNetuid, setExpandedNetuid] = useState<number | null>(null)

  const handleSort = useSortToggle(sortKey, sortDirection, setSortKey, setSortDirection)

  // Fetch subnet profiles from Supabase
  const { data: subnets, isLoading, error } = useQuery<SubnetProfile[]>({
    queryKey: ['subnet-profiles'],
    queryFn: async () => {
      const { data, error } = await supabase
        .from('subnet_profiles')
        .select('*')
        .order('netuid', { ascending: true })
      
      if (error) throw error
      return (data || []) as SubnetProfile[]
    },
    refetchInterval: 120000,
  })

  // Filter and sort logic
  const filteredAndSorted = useMemo(() => {
    let result = [...(subnets || [])]

    // Text search
    if (searchQuery.trim()) {
      const q = searchQuery.trim().toLowerCase()
      result = result.filter(
        (s) =>
          (s.subnet_name?.toLowerCase().includes(q) ?? false) ||
          String(s.netuid).includes(q)
      )
    }

    // Category filter
    if (categoryFilter !== 'all') {
      result = result.filter((s) => s.category === categoryFilter)
    }

    // Eligible filter
    if (eligibleFilter === 'eligible') {
      result = result.filter((s) => s.eligible === true)
    } else if (eligibleFilter === 'ineligible') {
      result = result.filter((s) => s.eligible === false)
    }

    // Sort
    if (!sortKey || !sortDirection) return result

    return result.sort((a, b) => {
      let aVal: number | string | null | boolean
      let bVal: number | string | null | boolean

      switch (sortKey) {
        case 'netuid':
          aVal = a.netuid
          bVal = b.netuid
          break
        case 'subnet_name':
          aVal = a.subnet_name || ''
          bVal = b.subnet_name || ''
          return sortDirection === 'asc'
            ? (aVal as string).localeCompare(bVal as string)
            : (bVal as string).localeCompare(aVal as string)
        case 'alpha_price':
          aVal = a.alpha_price ?? -Infinity
          bVal = b.alpha_price ?? -Infinity
          break
        case 'market_cap':
          aVal = a.market_cap ?? -Infinity
          bVal = b.market_cap ?? -Infinity
          break
        case 'pool_tao_reserve':
          aVal = a.pool_tao_reserve ?? -Infinity
          bVal = b.pool_tao_reserve ?? -Infinity
          break
        case 'emission_share':
          aVal = a.emission_share ?? -Infinity
          bVal = b.emission_share ?? -Infinity
          break
        case 'taoflow_7d':
          aVal = a.taoflow_7d ?? -Infinity
          bVal = b.taoflow_7d ?? -Infinity
          break
        case 'category':
          aVal = a.category || ''
          bVal = b.category || ''
          return sortDirection === 'asc'
            ? (aVal as string).localeCompare(bVal as string)
            : (bVal as string).localeCompare(aVal as string)
        case 'eligible':
          aVal = a.eligible ? 1 : 0
          bVal = b.eligible ? 1 : 0
          break
        default:
          return 0
      }

      return sortDirection === 'asc'
        ? (aVal as number) - (bVal as number)
        : (bVal as number) - (aVal as number)
    })
  }, [subnets, searchQuery, categoryFilter, eligibleFilter, sortKey, sortDirection])

  // Summary stats
  const summaryStats = useMemo(() => {
    if (!subnets) return { total: 0, eligible: 0, totalTao: 0 }
    const total = subnets.length
    const eligible = subnets.filter((s) => s.eligible).length
    const totalTao = subnets.reduce((sum, s) => sum + (s.pool_tao_reserve || 0), 0)
    return { total, eligible, totalTao }
  }, [subnets])

  const hasActiveFilters = searchQuery.trim() !== '' || categoryFilter !== 'all' || eligibleFilter !== 'all'

  const getCategoryColor = (category: string | null) => {
    switch (category) {
      case 'Core':
        return 'bg-blue-600/20 text-blue-400 border-blue-500/30'
      case 'Growth':
        return 'bg-green-600/20 text-green-400 border-green-500/30'
      case 'Speculative':
        return 'bg-yellow-600/20 text-yellow-400 border-yellow-500/30'
      case 'Dead':
        return 'bg-red-600/20 text-red-400 border-red-500/30'
      default:
        return 'bg-[#1a2d42]/30 text-[#6f87a0] border-[#2a4a66]'
    }
  }

  if (isLoading) {
    return (
      <div className="flex items-center justify-center h-64">
        <div className="animate-spin rounded-full h-8 w-8 border-b-2 border-[#2a3ded]"></div>
      </div>
    )
  }

  if (error) {
    return (
      <div className="bg-red-900/20 border border-red-700 rounded-lg p-4">
        <p className="text-red-400">Failed to load subnets. Please try refreshing.</p>
      </div>
    )
  }

  return (
    <div className="space-y-4 md:space-y-6">
      {/* Header */}
      <div className="flex flex-col sm:flex-row sm:items-center sm:justify-between gap-2">
        <div className="flex items-center gap-3">
          <Compass className="w-6 h-6 text-[#2a3ded]" />
          <h1 className="text-xl md:text-2xl font-bold text-white">Discover</h1>
        </div>
        <div className="text-xs md:text-sm text-[#6f87a0]">
          {summaryStats.eligible} eligible / {summaryStats.total} subnets
        </div>
      </div>

      {/* Summary Stats */}
      <div className="grid grid-cols-3 gap-2 md:gap-4">
        <div className="bg-[#121f2d] rounded-lg p-3 md:p-4 border border-[#1e3a5f]">
          <div className="text-xs md:text-sm text-[#6f87a0] mb-1">Total</div>
          <div className="text-lg md:text-2xl font-bold text-white">{summaryStats.total}</div>
        </div>
        <div className="bg-[#121f2d] rounded-lg p-3 md:p-4 border border-[#1e3a5f]">
          <div className="text-xs md:text-sm text-[#6f87a0] mb-1">Eligible</div>
          <div className="text-lg md:text-2xl font-bold text-green-400">{summaryStats.eligible}</div>
        </div>
        <div className="bg-[#121f2d] rounded-lg p-3 md:p-4 border border-[#1e3a5f]">
          <div className="text-xs md:text-sm text-[#6f87a0] mb-1">TAO in Pools</div>
          <div className="text-lg md:text-2xl font-bold text-white truncate">{formatTao(summaryStats.totalTao)} <span className="text-xs md:text-base">τ</span></div>
        </div>
      </div>

      {/* Filters Bar */}
      <div className="flex flex-col sm:flex-row sm:items-center gap-3 flex-wrap bg-[#121f2d] rounded-lg p-3 md:p-4 border border-[#1e3a5f]">
        {/* Text search */}
        <div className="relative flex-1 min-w-full sm:min-w-[200px] sm:max-w-xs">
          <Search className="absolute left-3 md:left-4 top-1/2 -translate-y-1/2 w-4 h-4 text-[#5a7a94]" />
          <input
            type="text"
            placeholder="Search name or netuid..."
            value={searchQuery}
            onChange={(e) => setSearchQuery(e.target.value)}
            className="w-full pl-9 md:pl-10 pr-3 md:pr-4 py-2 md:py-2.5 bg-[#0d1117] border border-[#1e3a5f] rounded-lg text-sm text-[#a8c4d9] placeholder-gray-500 focus:outline-none focus:border-[#2a3ded]"
          />
        </div>

        <div className="flex flex-wrap gap-2 items-center">
          {/* Category filter */}
          <select
            value={categoryFilter}
            onChange={(e) => setCategoryFilter(e.target.value as CategoryFilter)}
            className="bg-[#0d1117] border border-[#1e3a5f] rounded-lg text-xs md:text-sm text-[#8faabe] px-2.5 md:px-4 py-2 md:py-2.5 focus:outline-none focus:border-[#2a3ded]"
          >
            <option value="all">All Categories</option>
            <option value="Core">Core</option>
            <option value="Growth">Growth</option>
            <option value="Speculative">Speculative</option>
            <option value="Dead">Dead</option>
          </select>

          {/* Eligible filter */}
          <select
            value={eligibleFilter}
            onChange={(e) => setEligibleFilter(e.target.value as EligibleFilter)}
            className="bg-[#0d1117] border border-[#1e3a5f] rounded-lg text-xs md:text-sm text-[#8faabe] px-2.5 md:px-4 py-2 md:py-2.5 focus:outline-none focus:border-[#2a3ded]"
          >
            <option value="all">All Status</option>
            <option value="eligible">Eligible</option>
            <option value="ineligible">Ineligible</option>
          </select>

          {/* Sort dropdown */}
          <select
            value={`${sortKey || ''}-${sortDirection || ''}`}
            onChange={(e) => {
              const [key, dir] = e.target.value.split('-')
              setSortKey(key as SortKey || null)
              setSortDirection(dir as SortDirection)
            }}
            className="bg-[#0d1117] border border-[#1e3a5f] rounded-lg text-xs md:text-sm text-[#8faabe] px-2.5 md:px-4 py-2 md:py-2.5 focus:outline-none focus:border-[#2a3ded]"
          >
            <option value="netuid-asc">SN# (Low→High)</option>
            <option value="netuid-desc">SN# (High→Low)</option>
            <option value="alpha_price-desc">Price (High→Low)</option>
            <option value="alpha_price-asc">Price (Low→High)</option>
            <option value="market_cap-desc">Market Cap</option>
            <option value="pool_tao_reserve-desc">Liquidity</option>
            <option value="taoflow_7d-desc">7d Flow</option>
          </select>

          {/* Clear filters */}
          {hasActiveFilters && (
            <button
              onClick={() => {
                setSearchQuery('')
                setCategoryFilter('all')
                setEligibleFilter('all')
                setSortKey('netuid')
                setSortDirection('asc')
              }}
              className="text-xs text-[#6f87a0] hover:text-[#a8c4d9] underline px-2"
            >
              Clear
            </button>
          )}

          {/* Result count */}
          <span className="text-xs text-[#5a7a94] ml-2">
            {filteredAndSorted.length} shown
          </span>
        </div>
      </div>

      {/* Table */}
      {filteredAndSorted.length === 0 ? (
        <div className="bg-[#121f2d] rounded-lg p-8 text-center border border-[#1e3a5f]">
          <p className="text-[#6f87a0]">
            {hasActiveFilters
              ? 'No subnets match your filters. Try adjusting or clearing filters.'
              : 'No subnets found.'}
          </p>
        </div>
      ) : (
        <div className="bg-[#121f2d] rounded-lg border border-[#1e3a5f] overflow-hidden">
          <div className="overflow-x-auto">
            <table className="w-full min-w-[700px]">
              <thead className="bg-[#050d15]/50">
                <tr className="text-xs md:text-sm text-[#6f87a0]">
                  <th className="w-8 px-2 py-3" />
                  <SortableHeader<SortKey>
                    label="SN#"
                    sortKey="netuid"
                    currentSortKey={sortKey}
                    currentDirection={sortDirection}
                    onSort={handleSort}
                  />
                  <SortableHeader<SortKey>
                    label="Name"
                    sortKey="subnet_name"
                    currentSortKey={sortKey}
                    currentDirection={sortDirection}
                  />
                  <SortableHeader<SortKey>
                    label="Price"
                    sortKey="alpha_price"
                    currentSortKey={sortKey}
                    currentDirection={sortDirection}
                    onSort={handleSort}
                    align="right"
                  />
                  <SortableHeader<SortKey>
                    label="Market Cap"
                    sortKey="market_cap"
                    currentSortKey={sortKey}
                    currentDirection={sortDirection}
                    onSort={handleSort}
                    align="right"
                    className="hidden md:table-cell"
                  />
                  <SortableHeader<SortKey>
                    label="Liquidity"
                    sortKey="pool_tao_reserve"
                    currentSortKey={sortKey}
                    currentDirection={sortDirection}
                    onSort={handleSort}
                    align="right"
                  />
                  <SortableHeader<SortKey>
                    label="Emission"
                    sortKey="emission_share"
                    currentSortKey={sortKey}
                    currentDirection={sortDirection}
                    onSort={handleSort}
                    align="right"
                    className="hidden sm:table-cell"
                  />
                  <SortableHeader<SortKey>
                    label="7d Flow"
                    sortKey="taoflow_7d"
                    currentSortKey={sortKey}
                    currentDirection={sortDirection}
                    onSort={handleSort}
                    align="right"
                  />
                  <SortableHeader<SortKey>
                    label="Category"
                    sortKey="category"
                    currentSortKey={sortKey}
                    currentDirection={sortDirection}
                    onSort={handleSort}
                    className="hidden sm:table-cell"
                  />
                  <th className="px-4 py-3 text-xs font-medium text-[#6f87a0] uppercase tracking-wider text-left hidden md:table-cell">
                    Eligible
                  </th>
                </tr>
              </thead>
              <tbody className="divide-y divide-[#1e3a5f]">
                {filteredAndSorted.map((subnet) => {
                  const isExpanded = expandedNetuid === subnet.netuid
                  return (
                    <SubnetRow
                      key={subnet.netuid}
                      subnet={subnet}
                      isExpanded={isExpanded}
                      onToggle={() =>
                        setExpandedNetuid(isExpanded ? null : subnet.netuid)
                      }
                      getCategoryColor={getCategoryColor}
                    />
                  )
                })}
              </tbody>
            </table>
          </div>
        </div>
      )}
    </div>
  )
}

function SubnetRow({
  subnet,
  isExpanded,
  onToggle,
  getCategoryColor,
}: {
  subnet: SubnetProfile
  isExpanded: boolean
  onToggle: () => void
  getCategoryColor: (category: string | null) => string
}) {
  const emissionPct = subnet.emission_share
    ? (subnet.emission_share * 100).toFixed(2)
    : '--'

  return (
    <>
      <tr
        className="hover:bg-[#1a2d42]/30 cursor-pointer transition-colors"
        onClick={onToggle}
      >
        {/* Expand chevron */}
        <td className="px-2 py-3 text-[#5a7a94]">
          {isExpanded ? (
            <ChevronDown className="w-4 h-4" />
          ) : (
            <ChevronRight className="w-4 h-4" />
          )}
        </td>

        {/* SN# */}
        <td className="px-2 md:px-4 py-3 text-xs md:text-sm tabular-nums text-[#8faabe]">
          {subnet.netuid}
        </td>

        {/* Name */}
        <td className="px-2 md:px-4 py-3">
          <div className="font-medium text-xs md:text-sm text-white truncate max-w-[100px] md:max-w-[150px]">
            {subnet.subnet_name || `Subnet ${subnet.netuid}`}
          </div>
        </td>

        {/* Price */}
        <td className="px-2 md:px-4 py-3 text-right tabular-nums text-xs md:text-sm text-[#8faabe]">
          {subnet.alpha_price != null
            ? `${subnet.alpha_price.toFixed(6)} τ`
            : '--'}
        </td>

        {/* Market Cap - hidden on mobile */}
        <td className="hidden md:table-cell px-4 py-3 text-right tabular-nums text-sm text-[#8faabe]">
          {subnet.market_cap != null && subnet.market_cap > 0
            ? `${formatCompact(subnet.market_cap)} τ`
            : '--'}
        </td>

        {/* Liquidity */}
        <td className="px-2 md:px-4 py-3 text-right tabular-nums text-xs md:text-sm text-[#8faabe]">
          {subnet.pool_tao_reserve != null
            ? `${formatTao(subnet.pool_tao_reserve)} τ`
            : '--'}
        </td>

        {/* Emission - hidden on mobile */}
        <td className="hidden sm:table-cell px-4 py-3 text-right tabular-nums text-sm text-[#8faabe]">
          {emissionPct}%
        </td>

        {/* 7d Flow */}
        <td className="px-2 md:px-4 py-3 text-right tabular-nums text-xs md:text-sm">
          {subnet.taoflow_7d != null ? (
            <span className={subnet.taoflow_7d >= 0 ? 'text-green-400' : 'text-red-400'}>
              {subnet.taoflow_7d >= 0 ? '+' : ''}
              {subnet.taoflow_7d.toFixed(2)}
            </span>
          ) : (
            '--'
          )}
        </td>

        {/* Category - hidden on mobile */}
        <td className="hidden sm:table-cell px-4 py-3">
          <span
            className={`inline-flex px-2 py-0.5 rounded text-xs font-medium border ${getCategoryColor(
              subnet.category
            )}`}
          >
            {subnet.category || 'Unknown'}
          </span>
        </td>

        {/* Eligible - hidden on mobile */}
        <td className="hidden md:table-cell px-4 py-3">
          {subnet.eligible ? (
            <span className="inline-flex px-2 py-0.5 rounded text-xs font-medium bg-green-600/20 text-green-400">
              Yes
            </span>
          ) : (
            <span className="inline-flex px-2 py-0.5 rounded text-xs font-medium bg-red-600/20 text-red-400">
              No
            </span>
          )}
        </td>
      </tr>

      {/* Expanded row */}
      {isExpanded && <SubnetExpandedRow subnet={subnet} />}
    </>
  )
}

function SubnetExpandedRow({ subnet }: { subnet: SubnetProfile }) {
  return (
    <tr>
      <td colSpan={11} className="p-0">
        <div className="bg-[#0d1117] border-t border-[#1e3a5f] p-6">
          <div className="grid grid-cols-1 md:grid-cols-3 gap-6">
            {/* Details */}
            <div>
              <h4 className="text-sm font-medium text-[#6f87a0] mb-3">Details</h4>
              <div className="space-y-2 text-sm">
                <div className="flex justify-between">
                  <span className="text-[#5a7a94]">Age (days):</span>
                  <span className="text-[#a8c4d9]">
                    {subnet.age_days != null ? subnet.age_days : '--'}
                  </span>
                </div>
                <div className="flex justify-between">
                  <span className="text-[#5a7a94]">Holders:</span>
                  <span className="text-[#a8c4d9]">
                    {subnet.holder_count != null
                      ? subnet.holder_count.toLocaleString()
                      : '--'}
                  </span>
                </div>
                <div className="flex justify-between">
                  <span className="text-[#5a7a94]">Owner Take:</span>
                  <span className="text-[#a8c4d9]">
                    {subnet.owner_take != null
                      ? `${(subnet.owner_take * 100).toFixed(1)}%`
                      : '--'}
                  </span>
                </div>
              </div>
            </div>

            {/* Flow Data */}
            <div>
              <h4 className="text-sm font-medium text-[#6f87a0] mb-3">TAO Flow</h4>
              <div className="space-y-2 text-sm">
                <div className="flex justify-between">
                  <span className="text-[#5a7a94]">1d:</span>
                  <span
                    className={
                      subnet.taoflow_1d != null && subnet.taoflow_1d >= 0
                        ? 'text-green-400'
                        : 'text-red-400'
                    }
                  >
                    {subnet.taoflow_1d != null
                      ? `${subnet.taoflow_1d >= 0 ? '+' : ''}${subnet.taoflow_1d.toFixed(2)}`
                      : '--'}
                  </span>
                </div>
                <div className="flex justify-between">
                  <span className="text-[#5a7a94]">3d:</span>
                  <span
                    className={
                      subnet.taoflow_3d != null && subnet.taoflow_3d >= 0
                        ? 'text-green-400'
                        : 'text-red-400'
                    }
                  >
                    {subnet.taoflow_3d != null
                      ? `${subnet.taoflow_3d >= 0 ? '+' : ''}${subnet.taoflow_3d.toFixed(2)}`
                      : '--'}
                  </span>
                </div>
                <div className="flex justify-between">
                  <span className="text-[#5a7a94]">7d:</span>
                  <span
                    className={
                      subnet.taoflow_7d != null && subnet.taoflow_7d >= 0
                        ? 'text-green-400'
                        : 'text-red-400'
                    }
                  >
                    {subnet.taoflow_7d != null
                      ? `${subnet.taoflow_7d >= 0 ? '+' : ''}${subnet.taoflow_7d.toFixed(2)}`
                      : '--'}
                  </span>
                </div>
                <div className="flex justify-between">
                  <span className="text-[#5a7a94]">14d:</span>
                  <span
                    className={
                      subnet.taoflow_14d != null && subnet.taoflow_14d >= 0
                        ? 'text-green-400'
                        : 'text-red-400'
                    }
                  >
                    {subnet.taoflow_14d != null
                      ? `${subnet.taoflow_14d >= 0 ? '+' : ''}${subnet.taoflow_14d.toFixed(2)}`
                      : '--'}
                  </span>
                </div>
              </div>
            </div>

            {/* Eligibility Info */}
            <div>
              <h4 className="text-sm font-medium text-[#6f87a0] mb-3">Eligibility</h4>
              <div className="space-y-2 text-sm">
                <div className="flex justify-between">
                  <span className="text-[#5a7a94]">Status:</span>
                  <span
                    className={
                      subnet.eligible ? 'text-green-400 font-medium' : 'text-red-400 font-medium'
                    }
                  >
                    {subnet.eligible ? 'Eligible' : 'Ineligible'}
                  </span>
                </div>
                {!subnet.eligible && subnet.ineligibility_reason && (
                  <div className="mt-2 p-2 bg-red-900/10 border border-red-700/30 rounded text-xs text-red-400">
                    {subnet.ineligibility_reason}
                  </div>
                )}
              </div>
            </div>
          </div>
        </div>
      </td>
    </tr>
  )
}
