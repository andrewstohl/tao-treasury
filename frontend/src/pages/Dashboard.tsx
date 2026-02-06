import { useState, useMemo } from 'react'
import { useQuery } from '@tanstack/react-query'
import {
  Activity,
  ChevronRight,
  ChevronDown,
  Search,
  X,
} from 'lucide-react'
import { api } from '../services/api'
import type { Dashboard as DashboardType, EnrichedSubnetListResponse, EnrichedSubnet, VolatilePoolData, PositionSummary, ClosedPosition } from '../types'
import { formatTao, safeFloat } from '../utils/format'
import SparklineCell from '../components/common/cells/SparklineCell'
import RegimeBadge from '../components/common/cells/RegimeBadge'
import ViabilityBadge from '../components/common/cells/ViabilityBadge'
import SubnetExpandedRow, { FlowRow } from '../components/common/SubnetExpandedRow'
import PortfolioOverviewCards from '../components/dashboard/PortfolioOverviewCards'

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

  const { data, isLoading, error } = useQuery<DashboardType>({
    queryKey: ['dashboard'],
    queryFn: api.getDashboard,
    refetchInterval: 30000,
  })

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
      // Helper to calculate yield and alpha for a position
      const getYieldAndAlpha = (p: PositionSummary) => {
        const enriched = enrichedLookup.get(p.netuid)
        const entryPrice = safeFloat(p.entry_price_tao)
        const costBasis = safeFloat(p.cost_basis_tao)
        const alphaBalance = safeFloat(p.alpha_balance)
        const currentPrice = enriched ? safeFloat(enriched.alpha_price_tao) : 0
        const originalAlpha = entryPrice > 0 ? costBasis / entryPrice : 0
        const yieldAlpha = alphaBalance - originalAlpha
        const yieldTao = yieldAlpha * currentPrice
        const alphaPnlTao = originalAlpha * (currentPrice - entryPrice)
        return { yieldTao, alphaPnlTao }
      }

      switch (sortOption) {
        case 'value':
        case 'tao':
          // Both sort by TAO value (USD value is proportional)
          return safeFloat(b.tao_value_mid) - safeFloat(a.tao_value_mid)
        case 'yield': {
          const aYield = getYieldAndAlpha(a).yieldTao
          const bYield = getYieldAndAlpha(b).yieldTao
          return bYield - aYield
        }
        case 'alpha': {
          const aAlpha = getYieldAndAlpha(a).alphaPnlTao
          const bAlpha = getYieldAndAlpha(b).alphaPnlTao
          return bAlpha - aAlpha
        }
        case 'pnl':
          return safeFloat(b.unrealized_pnl_tao) - safeFloat(a.unrealized_pnl_tao)
        case 'apy':
          return safeFloat(b.current_apy) - safeFloat(a.current_apy)
        default:
          return safeFloat(b.tao_value_mid) - safeFloat(a.tao_value_mid)
      }
    })
  }, [data?.top_positions, sortOption, enrichedLookup])

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

  const { portfolio, action_items } = data
  const taoPrice = safeFloat(portfolio.tao_price_usd)
  const walletAddresses = portfolio?.wallet_address ? [portfolio.wallet_address] : []
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
        <h1 className="text-2xl font-bold">Dashboard</h1>
      </div>

      {/* Wallet Address Bar */}
      <div className="space-y-3">
        <div className="flex items-center gap-3">
          <div className="flex-1 flex items-center gap-2 bg-[#16181d] border border-[#2a2f38] rounded-lg px-4 py-2.5">
            <Search className="w-4 h-4 text-[#8a8f98] flex-shrink-0" />
            <input
              type="text"
              placeholder="Add address"
              className="flex-1 bg-transparent text-sm text-[#8faabe] placeholder-gray-500 outline-none"
              onKeyDown={(e) => {
                if (e.key === 'Enter') {
                  // Future: trigger add wallet address
                }
              }}
            />
          </div>
          <button className="px-5 py-2.5 bg-[#2a3ded] hover:bg-[#3a4dff] rounded-lg text-sm font-medium text-white transition-colors">
            Add
          </button>
        </div>
        {walletAddresses.length > 0 && (
          <div className="flex flex-wrap gap-2">
            {walletAddresses.map((addr) => (
              <div
                key={addr}
                className="flex items-center gap-2 px-3 py-1.5 bg-[#1e2128]/60 rounded-full text-sm"
              >
                <span className="font-mono text-[#8faabe]">{truncateAddress(addr)}</span>
                <button className="text-[#8a8f98] hover:text-[#8faabe] transition-colors">
                  <X className="w-4 h-4" />
                </button>
              </div>
            ))}
          </div>
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
  const entryPrice = safeFloat(position.entry_price_tao)
  const costBasis = safeFloat(position.cost_basis_tao)
  const alphaBalance = safeFloat(position.alpha_balance)
  const currentPrice = enriched ? safeFloat(enriched.alpha_price_tao) : 0
  const taoValue = safeFloat(position.tao_value_mid)

  // Yield: alpha earned from emissions, valued at current price
  const originalAlpha = entryPrice > 0 ? costBasis / entryPrice : 0
  const yieldAlpha = alphaBalance - originalAlpha
  const yieldTao = yieldAlpha * currentPrice

  // Alpha: price appreciation on original position
  const alphaPnlTao = originalAlpha * (currentPrice - entryPrice)

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
          <DashboardPositionDetail position={position} enriched={enriched} />
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
}: {
  position: PositionSummary
  enriched: EnrichedSubnet | null
}) {
  const v = enriched?.volatile

  // Compute P&L breakdown
  const costBasis = safeFloat(position.cost_basis_tao)
  const entryPrice = safeFloat(position.entry_price_tao)
  const currentPrice = enriched ? safeFloat(enriched.alpha_price_tao) : 0
  const alphaBalance = safeFloat(position.alpha_balance)
  const unrealizedPnl = safeFloat(position.unrealized_pnl_tao)
  const unrealizedPct = safeFloat(position.unrealized_pnl_pct)

  // Alpha originally purchased (cost / entry price)
  const originalAlpha = entryPrice > 0 ? costBasis / entryPrice : 0
  // Alpha earned from yield/emissions
  const yieldAlpha = alphaBalance - originalAlpha
  // Value of earned alpha at current price
  const yieldValueTao = yieldAlpha * currentPrice
  // Price change component (original alpha * price delta)
  const priceChangeTao = originalAlpha * (currentPrice - entryPrice)

  const pnlColor = (val: number) => val >= 0 ? 'text-green-400' : 'text-red-400'

  return (
    <div className="bg-[#0d0f12]/50">
      {/* Row 1: Performance (left) + Taoflow & Trading (right) */}
      <div className="grid grid-cols-1 md:grid-cols-2 gap-6 p-4 text-sm border-b border-[#23272e]">
        {/* Performance */}
        <div className="space-y-2">
          <h4 className="text-xs font-semibold text-[#9ca3af] uppercase tracking-wider">Performance</h4>
          <div className="space-y-1">
            <DashDetailRow label="Entry Date" value={position.entry_date ? new Date(position.entry_date).toLocaleDateString() : '--'} />
            <DashDetailRow label="Cost Basis" value={`${formatTao(position.cost_basis_tao)} τ`} />
            <DashDetailRow label="Entry Price" value={`${entryPrice.toFixed(6)} τ`} />
            <DashDetailRow
              label="Current Price"
              value={currentPrice > 0 ? `${currentPrice.toFixed(6)} τ` : '--'}
            />
            <div className="border-t border-[#2a2f38] my-1" />
            <DashDetailRow label="Alpha Purchased" value={`${originalAlpha.toFixed(2)} α`} />
            <DashDetailRow
              label="Alpha from Yield"
              value={`+${yieldAlpha.toFixed(2)} α`}
              valueColor="text-green-400"
            />
            <DashDetailRow label="Total Alpha" value={`${alphaBalance.toFixed(2)} α`} />
            <div className="border-t border-[#2a2f38] my-1" />
            <DashDetailRow
              label="Price Impact"
              value={`${priceChangeTao >= 0 ? '+' : ''}${priceChangeTao.toFixed(4)} τ`}
              valueColor={pnlColor(priceChangeTao)}
            />
            <DashDetailRow
              label="Yield Earned"
              value={`+${yieldValueTao.toFixed(4)} τ`}
              valueColor="text-green-400"
            />
            <DashDetailRow
              label="Unrealized P&L"
              value={`${unrealizedPnl >= 0 ? '+' : ''}${unrealizedPnl.toFixed(4)} τ (${unrealizedPct >= 0 ? '+' : ''}${unrealizedPct.toFixed(2)}%)`}
              valueColor={pnlColor(unrealizedPnl)}
            />
            {safeFloat(position.realized_pnl_tao) !== 0 && (
              <DashDetailRow
                label="Realized P&L"
                value={`${formatTao(position.realized_pnl_tao)} τ`}
                valueColor={pnlColor(safeFloat(position.realized_pnl_tao))}
              />
            )}
            <div className="border-t border-[#2a2f38] my-1" />
            <DashDetailRow
              label="Current APY"
              value={safeFloat(position.current_apy) > 0 ? `${safeFloat(position.current_apy).toFixed(1)}%` : '--'}
              valueColor="text-green-400"
            />
            <DashDetailRow
              label="Daily Yield"
              value={safeFloat(position.daily_yield_tao) > 0 ? `+${safeFloat(position.daily_yield_tao).toFixed(4)} τ` : '--'}
              valueColor="text-green-400"
            />
            {position.validator_hotkey && (
              <DashDetailRow
                label="Validator"
                value={`${position.validator_hotkey.slice(0, 8)}...${position.validator_hotkey.slice(-6)}`}
              />
            )}
          </div>
        </div>

        {/* Taoflow & Trading */}
        <div className="space-y-2">
          <h4 className="text-xs font-semibold text-[#9ca3af] uppercase tracking-wider">Taoflow & Trading</h4>
          <div className="space-y-1">
            <FlowRow label="1d Flow" value={enriched?.taoflow_1d} />
            <FlowRow label="3d Flow" value={enriched?.taoflow_3d} />
            <FlowRow label="7d Flow" value={enriched?.taoflow_7d} />
            <FlowRow label="14d Flow" value={enriched?.taoflow_14d} />
            <div className="border-t border-[#2a2f38] my-1" />
            <DashDetailRow label="Buys (24h)" value={v?.buys_24h != null ? String(v.buys_24h) : '--'} />
            <DashDetailRow label="Sells (24h)" value={v?.sells_24h != null ? String(v.sells_24h) : '--'} />
            <DashDetailRow label="Buyers (24h)" value={v?.buyers_24h != null ? String(v.buyers_24h) : '--'} />
            <DashDetailRow label="Sellers (24h)" value={v?.sellers_24h != null ? String(v.sellers_24h) : '--'} />
            <DashDetailRow label="24h High" value={v?.high_24h != null ? v.high_24h.toFixed(6) + ' τ' : '--'} />
            <DashDetailRow label="24h Low" value={v?.low_24h != null ? v.low_24h.toFixed(6) + ' τ' : '--'} />
          </div>
        </div>
      </div>

      {/* Row 2+3: About, then Pool Composition + Subnet Info */}
      <SubnetExpandedRow
        volatile={v}
        identity={enriched?.identity}
        ownerAddress={enriched?.owner_address}
        ownerTake={enriched?.owner_take}
        feeRate={enriched?.fee_rate}
        incentiveBurn={enriched?.incentive_burn}
        ageDays={enriched?.age_days}
        holderCount={enriched?.holder_count}
        ineligibilityReasons={enriched?.ineligibility_reasons}
        taoflow1d={enriched?.taoflow_1d}
        taoflow3d={enriched?.taoflow_3d}
        taoflow7d={enriched?.taoflow_7d}
        taoflow14d={enriched?.taoflow_14d}
        viabilityScore={enriched?.viability_score}
        viabilityTier={enriched?.viability_tier}
        viabilityFactors={enriched?.viability_factors}
        showTaoflow={false}
      />
    </div>
  )
}

function DashDetailRow({
  label,
  value,
  valueColor,
}: {
  label: string
  value: string
  valueColor?: string
}) {
  return (
    <div className="flex justify-between">
      <span className="text-[#8a8f98]">{label}</span>
      <span className={`tabular-nums ${valueColor || 'text-[#8faabe]'}`}>{value}</span>
    </div>
  )
}
