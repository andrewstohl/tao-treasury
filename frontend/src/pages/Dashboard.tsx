import { useState, useMemo, useRef, useEffect, useCallback } from 'react'
import { useQuery, useMutation, useQueryClient } from '@tanstack/react-query'
import {
  Activity,
  ChevronRight,
  ChevronDown,
  Search,
  X,
  Loader2,
  Columns3,
} from 'lucide-react'
import { api } from '../services/api'
import type { Dashboard as DashboardType, EnrichedSubnetListResponse, EnrichedSubnet, VolatilePoolData, PositionSummary, ClosedPosition } from '../types'
import { formatTao, safeFloat } from '../utils/format'
import SortableHeader, { useSortToggle, type SortDirection } from '../components/common/SortableHeader'
import SparklineCell from '../components/common/cells/SparklineCell'
import PriceChangeCell from '../components/common/cells/PriceChangeCell'
import RegimeBadge from '../components/common/cells/RegimeBadge'
import ViabilityBadge from '../components/common/cells/ViabilityBadge'
import PortfolioOverviewCards from '../components/dashboard/PortfolioOverviewCards'
import {
  PositionKPICards,
  SubnetPriceChart,
  MomentumSignal,
  ViabilityPanel,
  SubnetAbout,
} from '../components/dashboard/position-detail'

type PositionTab = 'open' | 'closed' | 'all'

type SortKey = 'value' | 'tao' | 'yield' | 'alpha' | 'pnl' | 'apy' | 'change' | 'weight'

// --- Column visibility for active positions table ---
type ColumnKey = 'validator' | 'sparkline' | 'change' | 'value' | 'weight' | 'tao' | 'yield' | 'alpha' | 'pnl' | 'apy' | 'viability' | 'regime'

const ALL_COLUMNS: { key: ColumnKey; label: string }[] = [
  { key: 'sparkline', label: '7d Chart' },
  { key: 'change', label: '24h / 7d' },
  { key: 'value', label: 'Value (USD)' },
  { key: 'weight', label: '% of Stake' },
  { key: 'tao', label: 'TAO' },
  { key: 'yield', label: 'Yield' },
  { key: 'alpha', label: 'Alpha' },
  { key: 'pnl', label: 'P&L' },
  { key: 'apy', label: 'APY' },
  { key: 'viability', label: 'Viability' },
  { key: 'regime', label: 'Regime' },
  { key: 'validator', label: 'Validator' },
]

const COLUMNS_STORAGE_KEY = 'tao-positions-columns'
const ALL_COLUMN_KEYS = ALL_COLUMNS.map((c) => c.key)

function loadVisibleColumns(): Set<ColumnKey> {
  const allKeys = new Set(ALL_COLUMN_KEYS)
  try {
    const stored = localStorage.getItem(COLUMNS_STORAGE_KEY)
    if (stored) {
      const parsed: string[] = JSON.parse(stored)
      if (Array.isArray(parsed) && parsed.length > 0) {
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

// Three-tier fallback logo component:
// 1. Try subnet's own logo
// 2. Try Root (SN0) logo
// 3. Show netuid in a circle
function SubnetLogo({
  logoUrl,
  rootLogoUrl,
  netuid,
  className = '',
  dimmed = false,
}: {
  logoUrl?: string | null
  rootLogoUrl?: string | null
  netuid: number
  className?: string
  dimmed?: boolean
}) {
  const [imgFailed, setImgFailed] = useState(false)
  const [rootFailed, setRootFailed] = useState(false)

  const baseClass = `w-6 h-6 rounded-full flex-shrink-0 bg-[#1e2128] ${className}`
  const opacityClass = dimmed ? 'opacity-60' : ''

  // Tier 1: Try subnet's own logo
  if (logoUrl && !imgFailed) {
    return (
      <img
        src={logoUrl}
        alt=""
        className={`${baseClass} ${opacityClass}`}
        onError={() => setImgFailed(true)}
      />
    )
  }

  // Tier 2: Try Root (SN0) logo
  if (rootLogoUrl && !rootFailed) {
    return (
      <img
        src={rootLogoUrl}
        alt=""
        className={`${baseClass} ${opacityClass}`}
        onError={() => setRootFailed(true)}
      />
    )
  }

  // Tier 3: Show netuid in a circle
  return (
    <div className={`${baseClass} flex items-center justify-center text-xs font-bold ${dimmed ? 'text-[#8a8f98]' : 'text-[#9ca3af]'}`}>
      {netuid}
    </div>
  )
}

export default function Dashboard() {
  const [expandedNetuid, setExpandedNetuid] = useState<number | null>(null)
  const [positionTab, setPositionTab] = useState<PositionTab>('open')
  const [searchQuery, setSearchQuery] = useState('')
  const [sortKey, setSortKey] = useState<SortKey | null>('value')
  const [sortDirection, setSortDirection] = useState<SortDirection>('desc')
  const [newWalletAddress, setNewWalletAddress] = useState('')
  const [selectedWallet, setSelectedWallet] = useState<string>('all')

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

  const queryClient = useQueryClient()

  const { data, isLoading, error } = useQuery<DashboardType>({
    queryKey: ['dashboard', selectedWallet],
    queryFn: () => api.getDashboard(selectedWallet === 'all' ? undefined : selectedWallet),
    refetchInterval: 120000,  // 2 min - reduced to avoid rate limits
  })

  const [walletError, setWalletError] = useState<string | null>(null)
  const [backgroundSyncing, setBackgroundSyncing] = useState(false)

  const addWalletMutation = useMutation({
    mutationFn: async (address: string) => {
      // 1. Add wallet to DB (fast — returns immediately)
      const wallet = await api.addWallet(address)
      // 2. Quick refresh: positions appear in ~3s with interim cost basis.
      //    Decomposition handles unindexed buys correctly (zero P&L contribution).
      await api.triggerRefresh('refresh')
      return wallet
    },
    onSuccess: () => {
      // 3. Positions visible immediately — invalidate to show them
      queryClient.invalidateQueries({ queryKey: ['dashboard'] })
      queryClient.invalidateQueries({ queryKey: ['portfolio-overview'] })
      setNewWalletAddress('')
      setWalletError(null)

      // 4. Full sync in background — authoritative FIFO, entry dates, yield.
      //    Takes ~60s but doesn't block the UI. Data silently updates when done.
      setBackgroundSyncing(true)
      api.triggerRefresh('full')
        .then(() => {
          queryClient.invalidateQueries({ queryKey: ['dashboard'] })
          queryClient.invalidateQueries({ queryKey: ['portfolio-overview'] })
        })
        .finally(() => setBackgroundSyncing(false))
    },
    onError: (error: unknown) => {
      // Extract error message from axios response
      const axiosError = error as { response?: { status?: number; data?: { detail?: string } }; message?: string }
      if (axiosError.response?.status === 409) {
        setWalletError('This wallet has already been added')
      } else if (axiosError.response?.status === 422) {
        setWalletError('Invalid wallet address format. Please enter a valid SS58 address (47-48 characters)')
      } else if (axiosError.response?.data?.detail) {
        setWalletError(axiosError.response.data.detail)
      } else {
        setWalletError(axiosError.message || 'Failed to add wallet')
      }
    },
  })

  const deleteWalletMutation = useMutation({
    mutationFn: (address: string) => api.deleteWallet(address),
    onSuccess: () => {
      // Reset wallet filter to "all" since the selected wallet may have been deleted
      setSelectedWallet('all')
      // Invalidate all portfolio-related queries so positions and KPIs refresh
      queryClient.invalidateQueries({ queryKey: ['dashboard'] })
      queryClient.invalidateQueries({ queryKey: ['portfolio-overview'] })
    },
  })

  const handleAddWallet = () => {
    const address = newWalletAddress.trim()
    if (address && address.length >= 46) {
      setWalletError(null)
      addWalletMutation.mutate(address)
    }
  }

  const { data: enrichedData } = useQuery<EnrichedSubnetListResponse>({
    queryKey: ['subnets-enriched', false],
    queryFn: () => api.getEnrichedSubnets(false),
    refetchInterval: 120000,
  })

  const enrichedLookup = useMemo(() => {
    const map = new Map<number, EnrichedSubnet>()
    if (enrichedData?.subnets) {
      for (const s of enrichedData.subnets) {
        map.set(s.netuid, s)
      }
    }
    return map
  }, [enrichedData?.subnets])

  // Sort open positions based on selected sort key/direction
  const openPositions = useMemo(() => {
    const positions = data?.top_positions || []
    if (!sortKey || !sortDirection) {
      return [...positions].sort((a, b) => safeFloat(b.tao_value_mid) - safeFloat(a.tao_value_mid))
    }

    return [...positions].sort((a, b) => {
      let aVal: number
      let bVal: number

      switch (sortKey) {
        case 'value':
        case 'tao':
          aVal = safeFloat(a.tao_value_mid)
          bVal = safeFloat(b.tao_value_mid)
          break
        case 'weight':
          aVal = safeFloat(a.weight_pct)
          bVal = safeFloat(b.weight_pct)
          break
        case 'yield':
          aVal = safeFloat(a.unrealized_yield_tao)
          bVal = safeFloat(b.unrealized_yield_tao)
          break
        case 'alpha':
          aVal = safeFloat(a.unrealized_alpha_pnl_tao)
          bVal = safeFloat(b.unrealized_alpha_pnl_tao)
          break
        case 'pnl':
          aVal = safeFloat(a.unrealized_pnl_tao)
          bVal = safeFloat(b.unrealized_pnl_tao)
          break
        case 'apy':
          aVal = safeFloat(a.current_apy)
          bVal = safeFloat(b.current_apy)
          break
        case 'change': {
          const aEnr = enrichedLookup.get(a.netuid)
          const bEnr = enrichedLookup.get(b.netuid)
          aVal = aEnr?.volatile?.price_change_24h ?? 0
          bVal = bEnr?.volatile?.price_change_24h ?? 0
          break
        }
        default:
          aVal = safeFloat(a.tao_value_mid)
          bVal = safeFloat(b.tao_value_mid)
      }

      return sortDirection === 'asc' ? aVal - bVal : bVal - aVal
    })
  }, [data?.top_positions, sortKey, sortDirection, enrichedLookup])

  // Filtered positions
  const filteredOpen = useMemo(() => {
    if (!searchQuery) return openPositions
    const q = searchQuery.toLowerCase()
    return openPositions.filter(p =>
      (p.subnet_name || '').toLowerCase().includes(q) ||
      String(p.netuid).includes(q)
    )
  }, [openPositions, searchQuery])

  const filteredClosed = useMemo(() => {
    const positions = data?.closed_positions || []
    if (!searchQuery) return positions
    const q = searchQuery.toLowerCase()
    return positions.filter(p =>
      (p.subnet_name || '').toLowerCase().includes(q) ||
      String(p.netuid).includes(q)
    )
  }, [data?.closed_positions, searchQuery])

  // colSpan for expanded detail row: expand(1) + position(1) + visible columns
  const colSpan = 2 + visibleColumns.size

  if (isLoading) {
    return (
      <div className="flex items-center justify-center h-64">
        <div className="animate-spin rounded-full h-8 w-8 border-b-2 border-[#2a3ded]"></div>
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

  const { portfolio, action_items, wallets } = data
  const taoPrice = safeFloat(portfolio.tao_price_usd)
  const walletAddresses = wallets || []
  const truncateAddress = (addr: string) => `${addr.slice(0, 6)}...${addr.slice(-5)}`

  const openCount = data.top_positions?.length || 0
  const closedCount = data.closed_positions?.length || 0

  const tabs: { key: PositionTab; label: string; count: number }[] = [
    { key: 'open', label: 'Active Positions', count: openCount },
    { key: 'closed', label: 'Inactive Positions', count: closedCount },
    { key: 'all', label: 'All Positions', count: openCount + closedCount },
  ]

  return (
    <div className="space-y-5">
      <div className="flex items-center justify-between">
        <h1 className="text-2xl font-bold text-[#2a3ded]">Track</h1>
      </div>

      {/* Wallet Address Bar */}
      <div className="space-y-3">
        <div className="flex items-center gap-3">
          <div className="flex-1 flex items-center gap-2 bg-[#16181d] border border-[#2a2f38] rounded-lg px-4 py-2.5">
            <Search className="w-4 h-4 text-[#8a8f98] flex-shrink-0" />
            <input
              type="text"
              placeholder="Add wallet address (SS58 format)"
              value={newWalletAddress}
              onChange={(e) => setNewWalletAddress(e.target.value)}
              className="flex-1 bg-transparent text-sm text-white placeholder-gray-500 outline-none"
              onKeyDown={(e) => {
                if (e.key === 'Enter') {
                  handleAddWallet()
                }
              }}
            />
          </div>
          <button
            onClick={handleAddWallet}
            disabled={addWalletMutation.isPending || newWalletAddress.trim().length < 46}
            className="px-4 py-2.5 bg-[#2a3ded] disabled:cursor-not-allowed rounded-lg text-sm font-medium text-white transition-colors flex items-center gap-2"
          >
            {addWalletMutation.isPending && <Loader2 className="w-4 h-4 animate-spin" />}
            {addWalletMutation.isPending ? 'Adding...' : 'Add'}
          </button>
        </div>
        {walletError && (
          <p className="text-sm text-red-400">{walletError}</p>
        )}
        {backgroundSyncing && (
          <p className="text-xs text-[#8a8f98] flex items-center gap-1.5">
            <Loader2 className="w-3 h-3 animate-spin" />
            Syncing full history...
          </p>
        )}
        {walletAddresses.length > 0 && (
          <div className="flex flex-wrap gap-2">
            {walletAddresses.map((addr) => (
              <div
                key={addr}
                className="flex items-center gap-2 px-3 py-1.5 bg-[#1e2128]/60 rounded-full text-sm"
              >
                <span className="font-mono text-[#8faabe]">{truncateAddress(addr)}</span>
                <button
                  onClick={() => deleteWalletMutation.mutate(addr)}
                  disabled={deleteWalletMutation.isPending}
                  className="text-[#8a8f98] hover:text-red-400 transition-colors disabled:opacity-50"
                  title="Remove wallet"
                >
                  <X className="w-4 h-4" />
                </button>
              </div>
            ))}
          </div>
        )}
        {walletAddresses.length === 0 && (
          <p className="text-sm text-[#8a8f98]">
            No wallets added yet. Enter a wallet address above to start tracking.
          </p>
        )}
      </div>

      {/* Action Items */}
      {action_items && action_items.length > 0 && (
        <div className="bg-[#16181d] rounded-lg border border-[#2a2f38]">
          <div className="px-4 py-3 border-b border-[#2a2f38] flex items-center justify-between">
            <h3 className="text-base font-semibold flex items-center gap-2">
              <Activity className="w-4 h-4" />
              Action Items
            </h3>
            <span className="text-xs text-[#8a8f98]">{action_items.length} items</span>
          </div>
          <div className="divide-y divide-gray-700">
            {action_items.slice(0, 5).map((item, idx) => (
              <div key={idx} className="px-4 py-3 flex items-start gap-3">
                <div className={`px-2 py-1 rounded text-xs font-semibold ${
                  item.priority === 'high' ? 'bg-red-600/20 text-red-400' :
                  item.priority === 'medium' ? 'bg-yellow-600/20 text-yellow-400' :
                  'bg-blue-600/20 text-blue-400'
                }`}>
                  {item.priority.toUpperCase()}
                </div>
                <div className="flex-1">
                  <div className="text-sm font-medium">{item.title}</div>
                  <div className="text-xs text-[#9ca3af]">{item.description}</div>
                </div>
                {item.potential_gain_tao && (
                  <div className="text-right">
                    <div className="text-sm text-green-400">+{safeFloat(item.potential_gain_tao).toFixed(2)} τ</div>
                    <div className="text-xs text-[#8a8f98]">potential</div>
                  </div>
                )}
              </div>
            ))}
          </div>
        </div>
      )}

      {/* Spacer: wallet to KPI cards */}
      <div className="h-5" />

      {/* Portfolio Overview Cards */}
      <PortfolioOverviewCards wallet={selectedWallet === 'all' ? undefined : selectedWallet} />

      {/* Spacer: KPI cards to positions */}
      <div className="h-20" />

      {/* Positions Section */}
      <div className="space-y-4">
        {/* Tabs */}
        <div className="flex items-center border-b border-[#2a2f38]">
          {tabs.map((tab) => (
            <button
              key={tab.key}
              onClick={() => setPositionTab(tab.key)}
              className={`px-1 pb-2.5 mr-6 text-sm font-medium transition-colors border-b-2 ${
                positionTab === tab.key
                  ? 'text-white border-[#2a3ded]'
                  : 'text-[#8a8f98] hover:text-[#8faabe] border-transparent'
              }`}
            >
              {tab.label}
              <span className="ml-1.5 text-xs text-[#6b7280]">({tab.count})</span>
            </button>
          ))}
        </div>

        {/* Filters + Column Toggle */}
        <div className="flex items-center gap-3">
          <div className="flex items-center gap-2 bg-[#16181d] border border-[#2a2f38] rounded-lg px-4 py-2.5 w-64">
            <Search className="w-4 h-4 text-[#8a8f98] flex-shrink-0" />
            <input
              type="text"
              placeholder="Search subnets..."
              value={searchQuery}
              onChange={(e) => setSearchQuery(e.target.value)}
              className="flex-1 bg-transparent text-sm text-[#8faabe] placeholder-gray-500 outline-none"
            />
            {searchQuery && (
              <button onClick={() => setSearchQuery('')} className="text-[#8a8f98] hover:text-[#8faabe]">
                <X className="w-4 h-4" />
              </button>
            )}
          </div>
          <select
            value={selectedWallet}
            onChange={(e) => setSelectedWallet(e.target.value)}
            className="bg-[#16181d] border border-[#2a2f38] rounded-lg px-4 py-2.5 text-sm text-[#8faabe]"
          >
            <option value="all">Wallet: All</option>
            {walletAddresses.map(addr => (
              <option key={addr} value={addr}>{truncateAddress(addr)}</option>
            ))}
          </select>

          {/* Column visibility toggle */}
          <div className="relative" ref={columnMenuRef}>
            <button
              onClick={() => setShowColumnMenu((prev) => !prev)}
              className={`flex items-center gap-1.5 px-4 py-2.5 rounded-lg border text-sm ${
                showColumnMenu
                  ? 'bg-[#1e2128] border-[#2a3ded] text-[#2a3ded]'
                  : 'bg-[#16181d] border-[#2a2f38] text-[#8a8f98] hover:border-[#3a3f48]'
              }`}
            >
              <Columns3 className="w-4 h-4" />
              Columns
            </button>
            {showColumnMenu && (
              <div className="absolute right-0 top-full mt-1 bg-[#16181d] border border-[#2a2f38] rounded-lg shadow-xl z-20 py-1 w-48">
                {ALL_COLUMNS.map((col) => (
                  <label
                    key={col.key}
                    className="flex items-center gap-2 px-3 py-1.5 hover:bg-[#1e2128] cursor-pointer text-sm text-[#8faabe]"
                  >
                    <input
                      type="checkbox"
                      checked={visibleColumns.has(col.key)}
                      onChange={() => toggleColumn(col.key)}
                      className="rounded bg-[#2a2f38] border-[#3a3f48]"
                    />
                    {col.label}
                  </label>
                ))}
                <div className="border-t border-[#2a2f38] mt-1 pt-1 px-3 pb-1">
                  <button
                    onClick={() => {
                      const all = new Set(ALL_COLUMN_KEYS)
                      setVisibleColumns(all)
                      saveVisibleColumns(all)
                    }}
                    className="text-xs text-[#2a3ded] hover:text-[#3a4dff]"
                  >
                    Show All
                  </button>
                </div>
              </div>
            )}
          </div>

          {/* Result count */}
          <span className="text-xs text-[#6b7280] ml-auto">
            {positionTab === 'open' ? filteredOpen.length :
             positionTab === 'closed' ? filteredClosed.length :
             filteredOpen.length + filteredClosed.length} positions
          </span>
        </div>

        {/* Active Positions Table */}
        {(positionTab === 'open' || positionTab === 'all') && filteredOpen.length > 0 && (
          <>
            {positionTab === 'all' && (
              <div className="text-xs text-[#8a8f98] uppercase tracking-wider font-medium">
                Active Positions ({filteredOpen.length})
              </div>
            )}
            <div className="bg-[#16181d] rounded-lg border border-[#2a2f38] overflow-x-auto">
              <table className="w-full min-w-[800px]">
                <thead className="bg-[#0d0f12]/60">
                  <tr>
                    {/* Expand toggle - always visible */}
                    <th className="w-8 px-2 py-3" />
                    {/* Subnet name - always visible */}
                    <th className="px-4 py-3 text-xs font-medium text-white uppercase tracking-wider text-left">
                      Subnet
                    </th>
                    {isColVisible('sparkline') && (
                      <th className="px-4 py-3 text-xs font-medium text-white uppercase tracking-wider text-center">
                        7d Chart
                      </th>
                    )}
                    {isColVisible('change') && (
                      <SortableHeader<SortKey>
                        label="24h / 7d"
                        sortKey="change"
                        currentSortKey={sortKey}
                        currentDirection={sortDirection}
                        onSort={handleSort}
                        align="center"
                      />
                    )}
                    {isColVisible('value') && (
                      <SortableHeader<SortKey>
                        label="Value"
                        sortKey="value"
                        currentSortKey={sortKey}
                        currentDirection={sortDirection}
                        onSort={handleSort}
                        align="center"
                      />
                    )}
                    {isColVisible('weight') && (
                      <SortableHeader<SortKey>
                        label="% of Stake"
                        sortKey="weight"
                        currentSortKey={sortKey}
                        currentDirection={sortDirection}
                        onSort={handleSort}
                        align="center"
                      />
                    )}
                    {isColVisible('tao') && (
                      <SortableHeader<SortKey>
                        label="TAO"
                        sortKey="tao"
                        currentSortKey={sortKey}
                        currentDirection={sortDirection}
                        onSort={handleSort}
                        align="center"
                      />
                    )}
                    {isColVisible('yield') && (
                      <SortableHeader<SortKey>
                        label="Yield"
                        sortKey="yield"
                        currentSortKey={sortKey}
                        currentDirection={sortDirection}
                        onSort={handleSort}
                        align="center"
                      />
                    )}
                    {isColVisible('alpha') && (
                      <SortableHeader<SortKey>
                        label="Alpha"
                        sortKey="alpha"
                        currentSortKey={sortKey}
                        currentDirection={sortDirection}
                        onSort={handleSort}
                        align="center"
                      />
                    )}
                    {isColVisible('pnl') && (
                      <SortableHeader<SortKey>
                        label="P&L"
                        sortKey="pnl"
                        currentSortKey={sortKey}
                        currentDirection={sortDirection}
                        onSort={handleSort}
                        align="center"
                      />
                    )}
                    {isColVisible('apy') && (
                      <SortableHeader<SortKey>
                        label="APY"
                        sortKey="apy"
                        currentSortKey={sortKey}
                        currentDirection={sortDirection}
                        onSort={handleSort}
                        align="center"
                      />
                    )}
                    {isColVisible('viability') && (
                      <th className="px-4 py-3 text-xs font-medium text-white uppercase tracking-wider text-center">
                        Viability
                      </th>
                    )}
                    {isColVisible('regime') && (
                      <th className="px-4 py-3 text-xs font-medium text-white uppercase tracking-wider text-center">
                        Regime
                      </th>
                    )}
                    {isColVisible('validator') && (
                      <th className="px-4 py-3 text-xs font-medium text-white uppercase tracking-wider text-center">
                        Validator
                      </th>
                    )}
                  </tr>
                </thead>
                <tbody className="divide-y divide-[#2a2f38]/50">
                  {filteredOpen.map((position) => {
                    const enriched = enrichedLookup.get(position.netuid)
                    const rootEnriched = enrichedLookup.get(0)
                    const v = enriched?.volatile ?? null
                    const isExpanded = expandedNetuid === position.netuid
                    return (
                      <PositionRow
                        key={`${position.wallet_address || ''}-${position.netuid}`}
                        position={position}
                        enriched={enriched ?? null}
                        rootLogoUrl={rootEnriched?.identity?.logo_url}
                        v={v}
                        taoPrice={taoPrice}
                        isExpanded={isExpanded}
                        onToggle={() => setExpandedNetuid(isExpanded ? null : position.netuid)}
                        isColVisible={isColVisible}
                        colSpan={colSpan}
                        showWalletBadge={selectedWallet === 'all' && walletAddresses.length > 1}
                      />
                    )
                  })}
                </tbody>
              </table>
            </div>
          </>
        )}

        {/* Free TAO balance */}
        {(positionTab === 'open' || positionTab === 'all') && safeFloat(data?.free_tao_balance) > 0 && (
          <div className="bg-[#16181d]/50 rounded-lg border border-[#2a2f38] px-5 py-3 flex items-center justify-between">
            <div className="flex items-center gap-3">
              <div className="w-8 h-8 rounded-full bg-green-900/40 flex items-center justify-center text-green-500 text-sm font-bold">τ</div>
              <div>
                <div className="font-medium text-sm text-[#9ca3af]">Free TAO</div>
                <div className="text-xs text-[#6b7280]">Unstaked buffer</div>
              </div>
            </div>
            <div className="tabular-nums text-sm text-[#9ca3af]">{formatTao(data?.free_tao_balance ?? '0')} τ</div>
          </div>
        )}

        {/* Closed Positions Table */}
        {(positionTab === 'closed' || positionTab === 'all') && filteredClosed.length > 0 && (
          <>
            {positionTab === 'all' && (
              <div className="text-xs text-[#8a8f98] uppercase tracking-wider font-medium pt-2">
                Inactive Positions ({filteredClosed.length})
              </div>
            )}
            <div className="bg-[#16181d] rounded-lg border border-[#2a2f38] overflow-x-auto opacity-70">
              <table className="w-full">
                <thead className="bg-[#0d0f12]/60">
                  <tr>
                    <th className="px-4 py-3 text-xs font-medium text-white uppercase tracking-wider text-center">
                      Position
                    </th>
                    <th className="px-4 py-3 text-xs font-medium text-white uppercase tracking-wider text-center">
                      Staked
                    </th>
                    <th className="px-4 py-3 text-xs font-medium text-white uppercase tracking-wider text-center">
                      Returned
                    </th>
                    <th className="px-4 py-3 text-xs font-medium text-white uppercase tracking-wider text-center">
                      P&L
                    </th>
                    <th className="px-4 py-3 text-xs font-medium text-white uppercase tracking-wider text-center">
                      Opened
                    </th>
                    <th className="px-4 py-3 text-xs font-medium text-white uppercase tracking-wider text-center">
                      Closed
                    </th>
                  </tr>
                </thead>
                <tbody className="divide-y divide-[#2a2f38]/50">
                  {filteredClosed.map((position) => {
                    const enriched = enrichedLookup.get(position.netuid)
                    const rootEnriched = enrichedLookup.get(0)
                    return (
                      <ClosedPositionRow
                        key={position.netuid}
                        position={position}
                        enriched={enriched ?? null}
                        rootLogoUrl={rootEnriched?.identity?.logo_url}
                      />
                    )
                  })}
                </tbody>
              </table>
            </div>
          </>
        )}

        {/* Empty state */}
        {((positionTab === 'open' && filteredOpen.length === 0) ||
          (positionTab === 'closed' && filteredClosed.length === 0) ||
          (positionTab === 'all' && filteredOpen.length === 0 && filteredClosed.length === 0)) && (
          <div className="text-center py-8 text-[#8a8f98]">
            {searchQuery ? 'No positions match your search.' : 'No positions found.'}
          </div>
        )}
      </div>
    </div>
  )
}

function PositionRow({
  position,
  enriched,
  rootLogoUrl,
  v,
  taoPrice,
  isExpanded,
  onToggle,
  isColVisible,
  colSpan,
  showWalletBadge,
}: {
  position: PositionSummary
  enriched: EnrichedSubnet | null
  rootLogoUrl?: string | null
  v: VolatilePoolData | null
  taoPrice: number
  isExpanded: boolean
  onToggle: () => void
  isColVisible: (key: ColumnKey) => boolean
  colSpan: number
  showWalletBadge?: boolean
}) {
  const taoValue = safeFloat(position.tao_value_mid)

  // Use pre-computed yield and alpha P&L from backend (single source of truth)
  const yieldTao = safeFloat(position.unrealized_yield_tao)
  const alphaPnlTao = safeFloat(position.unrealized_alpha_pnl_tao)

  const currentValueUsd = taoValue * taoPrice
  const unrealizedPnl = safeFloat(position.unrealized_pnl_tao)
  const apy = safeFloat(position.current_apy)

  const pnlColor = (val: number) => val >= 0 ? 'text-green-400' : 'text-red-400'

  return (
    <>
      <tr
        className="cursor-pointer hover:bg-[#1e2128]/30 transition-colors"
        onClick={onToggle}
      >
        {/* Expand chevron */}
        <td className="px-2 py-2.5 text-center text-[#8a8f98]">
          {isExpanded ? <ChevronDown className="w-4 h-4 inline" /> : <ChevronRight className="w-4 h-4 inline" />}
        </td>

        {/* Logo + Name */}
        <td className="px-4 py-2.5">
          <div className="flex items-center gap-2.5">
            <SubnetLogo
              logoUrl={enriched?.identity?.logo_url}
              rootLogoUrl={rootLogoUrl}
              netuid={position.netuid}
            />
            <div>
              <div className="font-medium text-sm text-white truncate max-w-[140px]">{position.subnet_name || `SN${position.netuid}`}</div>
              <div className="text-xs text-[#8a8f98]">
                SN{position.netuid}
                {showWalletBadge && position.wallet_address && (
                  <span className="ml-1.5 text-[10px] text-[#6b7280]" title={position.wallet_address}>
                    {`${position.wallet_address.slice(0, 6)}…${position.wallet_address.slice(-5)}`}
                  </span>
                )}
              </div>
            </div>
          </div>
        </td>

        {/* Sparkline */}
        {isColVisible('sparkline') && (
          <td className="px-4 py-2.5 text-center">
            <div className="w-36 mx-auto">
              <SparklineCell data={v?.sparkline_7d} />
            </div>
          </td>
        )}

        {/* 24h / 7d Change */}
        {isColVisible('change') && (
          <td className="px-4 py-2.5 text-center">
            <PriceChangeCell
              change24h={v?.price_change_24h}
              change7d={v?.price_change_7d}
            />
          </td>
        )}

        {/* Value (USD) */}
        {isColVisible('value') && (
          <td className="px-4 py-2.5 text-center">
            <div className="text-sm tabular-nums text-[#8a8f98]">${currentValueUsd.toLocaleString(undefined, { minimumFractionDigits: 2, maximumFractionDigits: 2 })}</div>
          </td>
        )}

        {/* % of Stake */}
        {isColVisible('weight') && (
          <td className="px-4 py-2.5 text-center">
            <div className="text-sm tabular-nums text-[#8a8f98]">{safeFloat(position.weight_pct).toFixed(1)}%</div>
          </td>
        )}

        {/* TAO */}
        {isColVisible('tao') && (
          <td className="px-4 py-2.5 text-center">
            <div className="text-sm tabular-nums text-[#8a8f98]">{taoValue.toFixed(2)} τ</div>
          </td>
        )}

        {/* Yield */}
        {isColVisible('yield') && (
          <td className="px-4 py-2.5 text-center">
            <div className="text-sm tabular-nums text-[#8a8f98]">
              {yieldTao.toFixed(2)} τ
            </div>
          </td>
        )}

        {/* Alpha */}
        {isColVisible('alpha') && (
          <td className="px-4 py-2.5 text-center">
            <div className="text-sm tabular-nums text-[#8a8f98]">
              {alphaPnlTao.toFixed(2)} τ
            </div>
          </td>
        )}

        {/* P&L */}
        {isColVisible('pnl') && (
          <td className="px-4 py-2.5 text-center">
            <div className={`text-sm tabular-nums ${pnlColor(unrealizedPnl)}`}>
              {unrealizedPnl.toFixed(2)} τ
            </div>
          </td>
        )}

        {/* APY */}
        {isColVisible('apy') && (
          <td className="px-4 py-2.5 text-center">
            <div className="text-sm tabular-nums text-[#8a8f98]">{apy > 0 ? `${apy.toFixed(2)}%` : '--'}</div>
          </td>
        )}

        {/* Viability */}
        {isColVisible('viability') && (
          <td className="px-4 py-2.5 text-center">
            <ViabilityBadge tier={enriched?.viability_tier} score={enriched?.viability_score} />
          </td>
        )}

        {/* Regime */}
        {isColVisible('regime') && (
          <td className="px-4 py-2.5 text-center">
            <RegimeBadge regime={position.flow_regime} />
          </td>
        )}

        {/* Validator */}
        {isColVisible('validator') && (
          <td className="px-4 py-2.5 text-center">
            <span className="text-sm text-[#8a8f98] truncate max-w-[140px] inline-block">
              {position.validator_name || (position.validator_hotkey ? `${position.validator_hotkey.slice(0, 8)}...` : '--')}
            </span>
          </td>
        )}
      </tr>

      {/* Expanded detail */}
      {isExpanded && (
        <tr>
          <td colSpan={colSpan} className="p-0 border-t border-[#2a2f38]">
            <DashboardPositionDetail position={position} enriched={enriched} taoPrice={taoPrice} />
          </td>
        </tr>
      )}
    </>
  )
}

function ClosedPositionRow({
  position,
  enriched,
  rootLogoUrl,
}: {
  position: ClosedPosition
  enriched: EnrichedSubnet | null
  rootLogoUrl?: string | null
}) {
  const pnl = safeFloat(position.realized_pnl_tao)
  const staked = safeFloat(position.total_staked_tao)
  const pnlColor = pnl >= 0 ? 'text-green-400' : 'text-red-400'

  return (
    <tr>
      {/* Logo + Name */}
      <td className="px-4 py-2.5">
        <div className="flex items-center gap-2.5">
          <SubnetLogo
            logoUrl={enriched?.identity?.logo_url}
            rootLogoUrl={rootLogoUrl}
            netuid={position.netuid}
            dimmed
          />
          <div>
            <div className="font-medium text-sm text-white truncate max-w-[140px]">{position.subnet_name || `SN${position.netuid}`}</div>
            <div className="text-xs text-[#6b7280] flex items-center gap-1.5">
              SN{position.netuid}
              <span className="px-1.5 py-0.5 rounded bg-[#1e2128] text-[#8a8f98] text-[10px]">Closed</span>
            </div>
          </div>
        </div>
      </td>

      {/* Staked */}
      <td className="px-4 py-2.5 text-center">
        <div className="text-sm tabular-nums text-[#8a8f98]">{staked.toFixed(2)} τ</div>
      </td>

      {/* Returned */}
      <td className="px-4 py-2.5 text-center">
        <div className="text-sm tabular-nums text-[#8a8f98]">{safeFloat(position.total_unstaked_tao).toFixed(2)} τ</div>
      </td>

      {/* P&L */}
      <td className="px-4 py-2.5 text-center">
        <div className={`text-sm tabular-nums ${pnlColor}`}>
          {pnl.toFixed(2)} τ
        </div>
      </td>

      {/* Opened */}
      <td className="px-4 py-2.5 text-center">
        <div className="text-sm tabular-nums text-[#8a8f98]">
          {position.first_entry ? new Date(position.first_entry).toLocaleDateString() : '--'}
        </div>
      </td>

      {/* Closed */}
      <td className="px-4 py-2.5 text-center">
        <div className="text-sm tabular-nums text-[#8a8f98]">
          {position.last_trade ? new Date(position.last_trade).toLocaleDateString() : '--'}
        </div>
      </td>
    </tr>
  )
}

function DashboardPositionDetail({
  position,
  enriched,
  taoPrice,
}: {
  position: PositionSummary
  enriched: EnrichedSubnet | null
  taoPrice: number
}) {
  const v = enriched?.volatile
  const entryPrice = safeFloat(position.entry_price_tao)
  const currentPrice = enriched ? safeFloat(enriched.alpha_price_tao) : 0

  return (
    <div className="bg-[#0d0f12]/50 p-4 space-y-4">
      {/* Row 1: Position KPI Cards */}
      <PositionKPICards position={position} enriched={enriched} taoPrice={taoPrice} />

      {/* Row 2: Chart + Trading Activity */}
      <div className="grid grid-cols-1 lg:grid-cols-3 gap-4">
        {/* Price Chart - 2/3 width */}
        <div className="lg:col-span-2">
          <SubnetPriceChart
            netuid={position.netuid}
            entryPrice={entryPrice}
            currentPrice={currentPrice}
            high24h={v?.high_24h}
            low24h={v?.low_24h}
          />
        </div>

        {/* Flow Momentum - 1/3 width */}
        <div>
          <MomentumSignal volatile={v} enriched={enriched} />
        </div>
      </div>

      {/* Row 3: About (2/3) + Viability (1/3) */}
      <div className="grid grid-cols-1 lg:grid-cols-3 gap-4">
        <div className="lg:col-span-2">
          <SubnetAbout identity={enriched?.identity} enriched={enriched} />
        </div>
        <div>
          <ViabilityPanel enriched={enriched} />
        </div>
      </div>
    </div>
  )
}
