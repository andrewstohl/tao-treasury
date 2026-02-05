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

export default function Dashboard() {
  const [expandedNetuid, setExpandedNetuid] = useState<number | null>(null)
  const [positionTab, setPositionTab] = useState<PositionTab>('open')
  const [searchQuery, setSearchQuery] = useState('')

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

  // Sort open positions by TAO value descending
  const openPositions = useMemo(() => {
    const positions = data?.top_positions || []
    return [...positions].sort(
      (a, b) => safeFloat(b.tao_value_mid) - safeFloat(a.tao_value_mid)
    )
  }, [data?.top_positions])

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
        <div className="animate-spin rounded-full h-8 w-8 border-b-2 border-tao-400"></div>
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
          <div className="flex-1 flex items-center gap-2 bg-gray-800 border border-gray-700 rounded-lg px-4 py-2.5">
            <Search className="w-4 h-4 text-gray-500 flex-shrink-0" />
            <input
              type="text"
              placeholder="Add address"
              className="flex-1 bg-transparent text-sm text-gray-300 placeholder-gray-500 outline-none"
              onKeyDown={(e) => {
                if (e.key === 'Enter') {
                  // Future: trigger add wallet address
                }
              }}
            />
          </div>
          <button className="px-5 py-2.5 bg-tao-600 hover:bg-tao-500 rounded-lg text-sm font-medium text-white transition-colors">
            Add
          </button>
        </div>
        {walletAddresses.length > 0 && (
          <div className="flex flex-wrap gap-2">
            {walletAddresses.map((addr) => (
              <div
                key={addr}
                className="flex items-center gap-2 px-3 py-1.5 bg-gray-700/60 rounded-full text-sm"
              >
                <span className="font-mono text-gray-300">{truncateAddress(addr)}</span>
                <button className="text-gray-500 hover:text-gray-300 transition-colors">
                  <X className="w-3.5 h-3.5" />
                </button>
              </div>
            ))}
          </div>
        )}
      </div>

      {/* Action Items */}
      {action_items && action_items.length > 0 && (
        <div className="bg-gray-800 rounded-lg border border-gray-700">
          <div className="px-6 py-4 border-b border-gray-700 flex items-center justify-between">
            <h3 className="text-lg font-semibold flex items-center gap-2">
              <Activity className="w-5 h-5" />
              Action Items
            </h3>
            <span className="text-sm text-gray-500">{action_items.length} items</span>
          </div>
          <div className="divide-y divide-gray-700">
            {action_items.slice(0, 5).map((item, idx) => (
              <div key={idx} className="px-6 py-4 flex items-start gap-4">
                <div className={`px-2 py-1 rounded text-xs font-semibold ${
                  item.priority === 'high' ? 'bg-red-600/20 text-red-400' :
                  item.priority === 'medium' ? 'bg-yellow-600/20 text-yellow-400' :
                  'bg-blue-600/20 text-blue-400'
                }`}>
                  {item.priority.toUpperCase()}
                </div>
                <div className="flex-1">
                  <div className="font-medium">{item.title}</div>
                  <div className="text-sm text-gray-400">{item.description}</div>
                </div>
                {item.potential_gain_tao && (
                  <div className="text-right text-sm">
                    <div className="text-green-400">+{safeFloat(item.potential_gain_tao).toFixed(2)} τ</div>
                    <div className="text-xs text-gray-500">potential</div>
                  </div>
                )}
              </div>
            ))}
          </div>
        </div>
      )}

      {/* Portfolio Overview Cards */}
      <div className="mb-3">
        <PortfolioOverviewCards />
      </div>

      {/* Positions Section */}
      <div className="space-y-4">
        {/* Tabs */}
        <div className="flex items-center border-b border-gray-700">
          {tabs.map((tab) => (
            <button
              key={tab.key}
              onClick={() => setPositionTab(tab.key)}
              className={`px-1 pb-2.5 mr-6 text-sm font-medium transition-colors border-b-2 ${
                positionTab === tab.key
                  ? 'text-white border-tao-400'
                  : 'text-gray-500 hover:text-gray-300 border-transparent'
              }`}
            >
              {tab.label}
              <span className="ml-1.5 text-xs text-gray-600">({tab.count})</span>
            </button>
          ))}
        </div>

        {/* Filters */}
        <div className="flex items-center gap-3">
          <div className="flex items-center gap-2 bg-gray-800 border border-gray-700 rounded-lg px-3 py-2 w-64">
            <Search className="w-4 h-4 text-gray-500 flex-shrink-0" />
            <input
              type="text"
              placeholder="Search subnets..."
              value={searchQuery}
              onChange={(e) => setSearchQuery(e.target.value)}
              className="flex-1 bg-transparent text-sm text-gray-300 placeholder-gray-500 outline-none"
            />
            {searchQuery && (
              <button onClick={() => setSearchQuery('')} className="text-gray-500 hover:text-gray-300">
                <X className="w-3.5 h-3.5" />
              </button>
            )}
          </div>
          <select className="bg-gray-800 border border-gray-700 rounded-lg px-3 py-2 text-sm text-gray-300">
            <option value="all">Wallet: All</option>
            {walletAddresses.map(addr => (
              <option key={addr} value={addr}>{truncateAddress(addr)}</option>
            ))}
          </select>
        </div>

        {/* Open Position Cards */}
        {(positionTab === 'open' || positionTab === 'all') && filteredOpen.length > 0 && (
          <div className="space-y-3">
            {positionTab === 'all' && (
              <div className="text-xs text-gray-500 uppercase tracking-wider font-medium">
                Open Positions ({filteredOpen.length})
              </div>
            )}
            {filteredOpen.map((position) => {
              const enriched = enrichedLookup.get(position.netuid)
              const v = enriched?.volatile ?? null
              const isExpanded = expandedNetuid === position.netuid
              return (
                <PositionCard
                  key={position.netuid}
                  position={position}
                  enriched={enriched ?? null}
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
          <div className="bg-gray-800/50 rounded-lg border border-gray-700 px-5 py-3 flex items-center justify-between">
            <div className="flex items-center gap-3">
              <div className="w-8 h-8 rounded-full bg-green-900/40 flex items-center justify-center text-green-500 text-sm font-bold">τ</div>
              <div>
                <div className="font-medium text-sm text-gray-400">Free TAO</div>
                <div className="text-xs text-gray-600">Unstaked buffer</div>
              </div>
            </div>
            <div className="tabular-nums text-sm text-gray-400">{formatTao(data?.free_tao_balance ?? '0')} τ</div>
          </div>
        )}

        {/* Closed Position Cards */}
        {(positionTab === 'closed' || positionTab === 'all') && filteredClosed.length > 0 && (
          <div className="space-y-3">
            {positionTab === 'all' && (
              <div className="text-xs text-gray-500 uppercase tracking-wider font-medium pt-2">
                Closed Positions ({filteredClosed.length})
              </div>
            )}
            {filteredClosed.map((position) => {
              const enriched = enrichedLookup.get(position.netuid)
              return (
                <ClosedPositionCard
                  key={position.netuid}
                  position={position}
                  enriched={enriched ?? null}
                />
              )
            })}
          </div>
        )}

        {/* Empty state */}
        {((positionTab === 'open' && filteredOpen.length === 0) ||
          (positionTab === 'closed' && filteredClosed.length === 0) ||
          (positionTab === 'all' && filteredOpen.length === 0 && filteredClosed.length === 0)) && (
          <div className="text-center py-8 text-gray-500">
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
  v,
  taoPrice,
  isExpanded,
  onToggle,
}: {
  position: PositionSummary
  enriched: EnrichedSubnet | null
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

  // Viability label
  const viabilityLabel = enriched?.viability_tier
    ? `${enriched.viability_tier === 'tier_1' ? 'Prime' : enriched.viability_tier === 'tier_2' ? 'Eligible' : enriched.viability_tier === 'tier_3' ? 'Watchlist' : 'Excluded'}${enriched.viability_score ? ` - ${parseFloat(enriched.viability_score).toFixed(0)}` : ''}`
    : null

  return (
    <div className="bg-gray-800 rounded-lg border border-gray-700 overflow-hidden">
      {/* Upper half */}
      <div
        className="flex items-center gap-4 px-5 py-3 cursor-pointer hover:bg-gray-700/30 transition-colors"
        onClick={onToggle}
      >
        <div className="text-gray-500 flex-shrink-0">
          {isExpanded ? <ChevronDown className="w-4 h-4" /> : <ChevronRight className="w-4 h-4" />}
        </div>
        {enriched?.identity?.logo_url ? (
          <img
            src={enriched.identity.logo_url}
            alt=""
            className="w-7 h-7 rounded-full flex-shrink-0 bg-gray-700"
            onError={(e) => { (e.target as HTMLImageElement).style.display = 'none' }}
          />
        ) : (
          <div className="w-7 h-7 rounded-full bg-gray-700 flex items-center justify-center text-xs text-gray-400 font-bold flex-shrink-0">
            {position.netuid}
          </div>
        )}
        <span className="font-semibold text-base font-display text-white">{position.subnet_name || `SN${position.netuid}`}</span>
        <span className="text-xs text-gray-500">SN{position.netuid}</span>
      </div>

      {/* Divider */}
      <div className="border-t border-gray-700" />

      {/* Lower half */}
      <div
        className="flex items-center gap-2 px-5 py-3 cursor-pointer hover:bg-gray-700/30 transition-colors"
        onClick={onToggle}
      >
        <div className="w-8 flex-shrink-0" />
        <div className="flex-1">
          <MetricCell
            label="Current Value"
            value={`$${currentValueUsd.toLocaleString(undefined, { minimumFractionDigits: 2, maximumFractionDigits: 2 })}`}
          />
        </div>
        <div className="flex-1">
          <MetricCell
            label="TAO Value"
            value={`${formatTao(taoValue)} τ`}
          />
        </div>
        <div className="flex-1">
          <MetricCell
            label="Yield"
            value={`${yieldTao >= 0 ? '+' : ''}${yieldTao.toFixed(4)} τ`}
            valueColor={pnlColor(yieldTao)}
          />
        </div>
        <div className="flex-1">
          <MetricCell
            label="Alpha"
            value={`${alphaPnlTao >= 0 ? '+' : ''}${alphaPnlTao.toFixed(4)} τ`}
            valueColor={pnlColor(alphaPnlTao)}
          />
        </div>
        <div className="flex-1">
          <MetricCell
            label="Profit/Loss"
            value={`${unrealizedPnl >= 0 ? '+' : ''}${formatTao(unrealizedPnl)} τ`}
            valueColor={pnlColor(unrealizedPnl)}
          />
        </div>
        <div className="flex-1">
          <MetricCell
            label="APY"
            value={apy > 0 ? `${apy.toFixed(1)}%` : '--'}
          />
        </div>
        <div className="flex-1">
          <div className="text-center">
            <div className="text-xs text-gray-500 mb-0.5">Viability</div>
            <div>{viabilityLabel ? (
              <ViabilityBadge tier={enriched?.viability_tier} score={enriched?.viability_score} />
            ) : <span className="text-sm text-gray-300">--</span>}</div>
          </div>
        </div>
        <div className="flex-1">
          <div className="text-center">
            <div className="text-xs text-gray-500 mb-0.5">Regime</div>
            <div><RegimeBadge regime={position.flow_regime} /></div>
          </div>
        </div>
        <div className="w-64 flex-shrink-0">
          <div className="text-center">
            <div className="text-xs text-gray-500 mb-0.5">7D Performance</div>
            <div><SparklineCell data={v?.sparkline_7d} /></div>
          </div>
        </div>
      </div>

      {/* Expanded detail */}
      {isExpanded && (
        <div className="border-t border-gray-700">
          <DashboardPositionDetail position={position} enriched={enriched} />
        </div>
      )}
    </div>
  )
}

function ClosedPositionCard({
  position,
  enriched,
}: {
  position: ClosedPosition
  enriched: EnrichedSubnet | null
}) {
  const pnl = safeFloat(position.realized_pnl_tao)
  const staked = safeFloat(position.total_staked_tao)
  const pnlColor = pnl >= 0 ? 'text-green-400' : 'text-red-400'

  return (
    <div className="bg-gray-800 rounded-lg border border-gray-700 overflow-hidden opacity-70">
      {/* Upper half */}
      <div className="flex items-center gap-4 px-5 py-3">
        {enriched?.identity?.logo_url ? (
          <img
            src={enriched.identity.logo_url}
            alt=""
            className="w-7 h-7 rounded-full flex-shrink-0 bg-gray-700 opacity-60"
            onError={(e) => { (e.target as HTMLImageElement).style.display = 'none' }}
          />
        ) : (
          <div className="w-7 h-7 rounded-full bg-gray-700 flex items-center justify-center text-xs text-gray-500 font-bold flex-shrink-0">
            {position.netuid}
          </div>
        )}
        <span className="font-medium text-sm text-gray-400">{position.subnet_name || `SN${position.netuid}`}</span>
        <span className="text-xs text-gray-600">SN{position.netuid}</span>
        <span className="text-xs px-2 py-0.5 rounded bg-gray-700 text-gray-500">Closed</span>
      </div>

      {/* Divider */}
      <div className="border-t border-gray-700" />

      {/* Lower half */}
      <div className="grid grid-cols-5 gap-4 px-5 py-3">
        <MetricCell
          label="Total Staked"
          value={`${formatTao(staked)} τ`}
        />
        <MetricCell
          label="Total Returned"
          value={`${formatTao(position.total_unstaked_tao)} τ`}
        />
        <MetricCell
          label="Realized P&L"
          value={`${pnl >= 0 ? '+' : ''}${formatTao(pnl)} τ`}
          valueColor={pnlColor}
        />
        <MetricCell
          label="Opened"
          value={position.first_entry ? new Date(position.first_entry).toLocaleDateString() : '--'}
        />
        <MetricCell
          label="Last Trade"
          value={position.last_trade ? new Date(position.last_trade).toLocaleDateString() : '--'}
        />
      </div>
    </div>
  )
}

function MetricCell({
  label,
  value,
  valueColor,
}: {
  label: string
  value: string
  valueColor?: string
}) {
  return (
    <div className="text-center">
      <div className="text-xs text-gray-500 mb-0.5">{label}</div>
      <div className={`tabular-nums text-sm ${valueColor || 'text-white'}`}>{value}</div>
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
    <div className="bg-gray-900/50">
      {/* Row 1: Performance (left) + Taoflow & Trading (right) */}
      <div className="grid grid-cols-1 md:grid-cols-2 gap-6 p-4 text-sm border-b border-gray-800">
        {/* Performance */}
        <div className="space-y-2">
          <h4 className="text-xs font-semibold text-gray-400 uppercase tracking-wider">Performance</h4>
          <div className="space-y-1">
            <DashDetailRow label="Entry Date" value={position.entry_date ? new Date(position.entry_date).toLocaleDateString() : '--'} />
            <DashDetailRow label="Cost Basis" value={`${formatTao(position.cost_basis_tao)} τ`} />
            <DashDetailRow label="Entry Price" value={`${entryPrice.toFixed(6)} τ`} />
            <DashDetailRow
              label="Current Price"
              value={currentPrice > 0 ? `${currentPrice.toFixed(6)} τ` : '--'}
            />
            <div className="border-t border-gray-700 my-1" />
            <DashDetailRow label="Alpha Purchased" value={`${originalAlpha.toFixed(2)} α`} />
            <DashDetailRow
              label="Alpha from Yield"
              value={`+${yieldAlpha.toFixed(2)} α`}
              valueColor="text-green-400"
            />
            <DashDetailRow label="Total Alpha" value={`${alphaBalance.toFixed(2)} α`} />
            <div className="border-t border-gray-700 my-1" />
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
            <div className="border-t border-gray-700 my-1" />
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
          <h4 className="text-xs font-semibold text-gray-400 uppercase tracking-wider">Taoflow & Trading</h4>
          <div className="space-y-1">
            <FlowRow label="1d Flow" value={enriched?.taoflow_1d} />
            <FlowRow label="3d Flow" value={enriched?.taoflow_3d} />
            <FlowRow label="7d Flow" value={enriched?.taoflow_7d} />
            <FlowRow label="14d Flow" value={enriched?.taoflow_14d} />
            <div className="border-t border-gray-700 my-1" />
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
      <span className="text-gray-500">{label}</span>
      <span className={`tabular-nums ${valueColor || 'text-gray-300'}`}>{value}</span>
    </div>
  )
}
