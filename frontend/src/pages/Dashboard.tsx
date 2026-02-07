import { useState, useMemo } from 'react'
import { useQuery, useMutation, useQueryClient } from '@tanstack/react-query'
import {
  Activity,
  ChevronRight,
  ChevronDown,
  Search,
  X,
  Loader2,
} from 'lucide-react'
import { api } from '../services/api'
import type { Dashboard as DashboardType, EnrichedSubnetListResponse, EnrichedSubnet, VolatilePoolData, PositionSummary, ClosedPosition } from '../types'
import { formatTao, safeFloat } from '../utils/format'
import SparklineCell from '../components/common/cells/SparklineCell'
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
type SortOption = 'value' | 'tao' | 'yield' | 'alpha' | 'pnl' | 'apy'

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
  const [sortOption, setSortOption] = useState<SortOption>('value')
  const [newWalletAddress, setNewWalletAddress] = useState('')

  const queryClient = useQueryClient()

  const { data, isLoading, error } = useQuery<DashboardType>({
    queryKey: ['dashboard'],
    queryFn: api.getDashboard,
    refetchInterval: 120000,  // 2 min - reduced to avoid rate limits
  })

  const [walletError, setWalletError] = useState<string | null>(null)

  const addWalletMutation = useMutation({
    mutationFn: (address: string) => api.addWallet(address),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ['dashboard'] })
      setNewWalletAddress('')
      setWalletError(null)
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
      queryClient.invalidateQueries({ queryKey: ['dashboard'] })
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

  // Sort open positions based on selected sort option
  const openPositions = useMemo(() => {
    const positions = data?.top_positions || []
    return [...positions].sort((a, b) => {
      switch (sortOption) {
        case 'value':
        case 'tao':
          // Both sort by TAO value (USD value is proportional)
          return safeFloat(b.tao_value_mid) - safeFloat(a.tao_value_mid)
        case 'yield':
          // Use pre-computed yield from backend (single source of truth)
          return safeFloat(b.unrealized_yield_tao) - safeFloat(a.unrealized_yield_tao)
        case 'alpha':
          // Use pre-computed alpha P&L from backend (single source of truth)
          return safeFloat(b.unrealized_alpha_pnl_tao) - safeFloat(a.unrealized_alpha_pnl_tao)
        case 'pnl':
          return safeFloat(b.unrealized_pnl_tao) - safeFloat(a.unrealized_pnl_tao)
        case 'apy':
          return safeFloat(b.current_apy) - safeFloat(a.current_apy)
        default:
          return safeFloat(b.tao_value_mid) - safeFloat(a.tao_value_mid)
      }
    })
  }, [data?.top_positions, sortOption])

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
    { key: 'open', label: 'Open Positions', count: openCount },
    { key: 'closed', label: 'Closed Positions', count: closedCount },
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
              className="flex-1 bg-transparent text-sm text-[#8faabe] placeholder-gray-500 outline-none"
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
            className="px-5 py-2.5 bg-[#2a3ded] hover:bg-[#3a4dff] disabled:opacity-50 disabled:cursor-not-allowed rounded-lg text-sm font-medium text-white transition-colors flex items-center gap-2"
          >
            {addWalletMutation.isPending && <Loader2 className="w-4 h-4 animate-spin" />}
            Add
          </button>
        </div>
        {walletError && (
          <p className="text-sm text-red-400">{walletError}</p>
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
      <PortfolioOverviewCards />

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

        {/* Filters */}
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
          <select className="bg-[#16181d] border border-[#2a2f38] rounded-lg px-4 py-2.5 text-sm text-[#8faabe]">
            <option value="all">Wallet: All</option>
            {walletAddresses.map(addr => (
              <option key={addr} value={addr}>{truncateAddress(addr)}</option>
            ))}
          </select>
          <select
            value={sortOption}
            onChange={(e) => setSortOption(e.target.value as SortOption)}
            className="bg-[#16181d] border border-[#2a2f38] rounded-lg px-4 py-2.5 text-sm text-[#8faabe]"
          >
            <option value="value">Sort: Value</option>
            <option value="tao">Sort: TAO</option>
            <option value="yield">Sort: Yield</option>
            <option value="alpha">Sort: Alpha</option>
            <option value="pnl">Sort: P&L</option>
            <option value="apy">Sort: APY</option>
          </select>
        </div>

        {/* Open Position Cards */}
        {(positionTab === 'open' || positionTab === 'all') && filteredOpen.length > 0 && (
          <div className="space-y-3">
            {positionTab === 'all' && (
              <div className="text-xs text-[#8a8f98] uppercase tracking-wider font-medium">
                Open Positions ({filteredOpen.length})
              </div>
            )}
            {filteredOpen.map((position) => {
              const enriched = enrichedLookup.get(position.netuid)
              const rootEnriched = enrichedLookup.get(0)
              const v = enriched?.volatile ?? null
              const isExpanded = expandedNetuid === position.netuid
              return (
                <PositionCard
                  key={position.netuid}
                  position={position}
                  enriched={enriched ?? null}
                  rootLogoUrl={rootEnriched?.identity?.logo_url}
                  v={v}
                  taoPrice={taoPrice}
                  isExpanded={isExpanded}
                  onToggle={() => setExpandedNetuid(isExpanded ? null : position.netuid)}
                />
              )
            })}
          </div>
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

        {/* Closed Position Cards */}
        {(positionTab === 'closed' || positionTab === 'all') && filteredClosed.length > 0 && (
          <div className="space-y-3">
            {positionTab === 'all' && (
              <div className="text-xs text-[#8a8f98] uppercase tracking-wider font-medium pt-2">
                Closed Positions ({filteredClosed.length})
              </div>
            )}
            {filteredClosed.map((position) => {
              const enriched = enrichedLookup.get(position.netuid)
              const rootEnriched = enrichedLookup.get(0)
              return (
                <ClosedPositionCard
                  key={position.netuid}
                  position={position}
                  enriched={enriched ?? null}
                  rootLogoUrl={rootEnriched?.identity?.logo_url}
                />
              )
            })}
          </div>
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

function PositionCard({
  position,
  enriched,
  rootLogoUrl,
  v,
  taoPrice,
  isExpanded,
  onToggle,
}: {
  position: PositionSummary
  enriched: EnrichedSubnet | null
  rootLogoUrl?: string | null
  v: VolatilePoolData | null
  taoPrice: number
  isExpanded: boolean
  onToggle: () => void
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
    <div className="bg-[#16181d] rounded-lg border border-[#2a2f38] overflow-hidden">
      {/* Single row layout */}
      <div
        className="flex items-center gap-3 px-4 py-2.5 cursor-pointer hover:bg-[#1e2128]/30 transition-colors"
        onClick={onToggle}
      >
        {/* Expand chevron */}
        <div className="text-[#8a8f98] flex-shrink-0">
          {isExpanded ? <ChevronDown className="w-4 h-4" /> : <ChevronRight className="w-4 h-4" />}
        </div>

        {/* Logo */}
        <SubnetLogo
          logoUrl={enriched?.identity?.logo_url}
          rootLogoUrl={rootLogoUrl}
          netuid={position.netuid}
        />

        {/* Name + SN */}
        <div className="w-28 flex-shrink-0">
          <div className="font-medium text-sm text-white truncate">{position.subnet_name || `SN${position.netuid}`}</div>
          <div className="text-xs text-[#8a8f98]">SN{position.netuid}</div>
        </div>

        {/* 7D Performance Sparkline - moved to front and wider */}
        <div className="w-44 flex-shrink-0">
          <SparklineCell data={v?.sparkline_7d} />
        </div>

        {/* Data columns - evenly spaced grid, all centered */}
        <div className="flex-1 grid grid-cols-8 gap-2">
          {/* Current Value */}
          <div className="text-center">
            <div className="text-xs text-[#8a8f98]">Value</div>
            <div className="text-sm tabular-nums text-white">${currentValueUsd.toLocaleString(undefined, { minimumFractionDigits: 2, maximumFractionDigits: 2 })}</div>
          </div>

          {/* TAO Value */}
          <div className="text-center">
            <div className="text-xs text-[#8a8f98]">TAO</div>
            <div className="text-sm tabular-nums text-white">{taoValue.toFixed(2)} τ</div>
          </div>

          {/* Yield */}
          <div className="text-center">
            <div className="text-xs text-[#8a8f98]">Yield</div>
            <div className={`text-sm tabular-nums ${pnlColor(yieldTao)}`}>
              {yieldTao >= 0 ? '+' : ''}{yieldTao.toFixed(2)} τ
            </div>
          </div>

          {/* Alpha */}
          <div className="text-center">
            <div className="text-xs text-[#8a8f98]">Alpha</div>
            <div className={`text-sm tabular-nums ${pnlColor(alphaPnlTao)}`}>
              {alphaPnlTao >= 0 ? '+' : ''}{alphaPnlTao.toFixed(2)} τ
            </div>
          </div>

          {/* Profit/Loss */}
          <div className="text-center">
            <div className="text-xs text-[#8a8f98]">P&L</div>
            <div className={`text-sm tabular-nums ${pnlColor(unrealizedPnl)}`}>
              {unrealizedPnl >= 0 ? '+' : ''}{unrealizedPnl.toFixed(2)} τ
            </div>
          </div>

          {/* APY */}
          <div className="text-center">
            <div className="text-xs text-[#8a8f98]">APY</div>
            <div className="text-sm tabular-nums text-white">{apy > 0 ? `${apy.toFixed(2)}%` : '--'}</div>
          </div>

          {/* Viability */}
          <div className="text-center">
            <div className="text-xs text-[#8a8f98]">Viability</div>
            <ViabilityBadge tier={enriched?.viability_tier} score={enriched?.viability_score} />
          </div>

          {/* Regime */}
          <div className="text-center">
            <div className="text-xs text-[#8a8f98]">Regime</div>
            <RegimeBadge regime={position.flow_regime} />
          </div>
        </div>
      </div>

      {/* Expanded detail */}
      {isExpanded && (
        <div className="border-t border-[#2a2f38]">
          <DashboardPositionDetail position={position} enriched={enriched} taoPrice={taoPrice} />
        </div>
      )}
    </div>
  )
}

function ClosedPositionCard({
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
    <div className="bg-[#16181d] rounded-lg border border-[#2a2f38] overflow-hidden opacity-70">
      {/* Single row layout */}
      <div className="flex items-center gap-3 px-4 py-2.5">
        {/* Spacer for alignment with open positions */}
        <div className="w-4 flex-shrink-0" />

        {/* Logo */}
        <SubnetLogo
          logoUrl={enriched?.identity?.logo_url}
          rootLogoUrl={rootLogoUrl}
          netuid={position.netuid}
          dimmed
        />

        {/* Name + SN + Closed badge */}
        <div className="w-28 flex-shrink-0">
          <div className="flex items-center gap-2">
            <span className="font-medium text-sm text-white truncate">{position.subnet_name || `SN${position.netuid}`}</span>
          </div>
          <div className="text-xs text-[#6b7280] flex items-center gap-1.5">
            SN{position.netuid}
            <span className="px-1.5 py-0.5 rounded bg-[#1e2128] text-[#8a8f98]">Closed</span>
          </div>
        </div>

        {/* Spacer to align with sparkline column */}
        <div className="w-44 flex-shrink-0" />

        {/* Data columns - evenly spaced grid (matching open positions), all centered */}
        <div className="flex-1 grid grid-cols-8 gap-2">
          {/* Total Staked */}
          <div className="text-center">
            <div className="text-xs text-[#8a8f98]">Staked</div>
            <div className="text-sm tabular-nums text-white">{staked.toFixed(2)} τ</div>
          </div>

          {/* Total Returned */}
          <div className="text-center">
            <div className="text-xs text-[#8a8f98]">Returned</div>
            <div className="text-sm tabular-nums text-white">{safeFloat(position.total_unstaked_tao).toFixed(2)} τ</div>
          </div>

          {/* Realized P&L */}
          <div className="text-center">
            <div className="text-xs text-[#8a8f98]">P&L</div>
            <div className={`text-sm tabular-nums ${pnlColor}`}>
              {pnl >= 0 ? '+' : ''}{pnl.toFixed(2)} τ
            </div>
          </div>

          {/* Opened Date */}
          <div className="text-center">
            <div className="text-xs text-[#8a8f98]">Opened</div>
            <div className="text-sm tabular-nums text-white">
              {position.first_entry ? new Date(position.first_entry).toLocaleDateString() : '--'}
            </div>
          </div>

          {/* Closed Date */}
          <div className="text-center">
            <div className="text-xs text-[#8a8f98]">Closed</div>
            <div className="text-sm tabular-nums text-white">
              {position.last_trade ? new Date(position.last_trade).toLocaleDateString() : '--'}
            </div>
          </div>

          {/* Empty columns to match open position grid */}
          <div />
          <div />
          <div />
        </div>
      </div>
    </div>
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
