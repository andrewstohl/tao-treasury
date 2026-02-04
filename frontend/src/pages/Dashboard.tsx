import { useState, useMemo } from 'react'
import { useQuery } from '@tanstack/react-query'
import {
  Activity,
  BarChart3,
  Shield,
  ChevronRight,
  ChevronDown,
} from 'lucide-react'
import { api } from '../services/api'
import type { Dashboard as DashboardType, EnrichedSubnetListResponse, EnrichedSubnet, VolatilePoolData, PositionSummary } from '../types'
import { formatTao, formatTaoShort, formatPercent, formatCompact, safeFloat } from '../utils/format'
import SortableHeader, { useSortToggle, type SortDirection } from '../components/common/SortableHeader'
import SparklineCell from '../components/common/cells/SparklineCell'
import PriceChangeCell from '../components/common/cells/PriceChangeCell'
import SentimentBadge from '../components/common/cells/SentimentBadge'
import RegimeBadge from '../components/common/cells/RegimeBadge'
import SubnetExpandedRow from '../components/common/SubnetExpandedRow'
import PortfolioOverviewCards from '../components/dashboard/PortfolioOverviewCards'

type DashboardSortKey =
  | 'subnet_name'
  | 'tao_value_mid'
  | 'weight_pct'
  | 'price_change_24h'
  | 'current_apy'
  | 'cost_basis_tao'
  | 'unrealized_pnl_pct'
  | 'flow_regime'

export default function Dashboard() {
  const [sortKey, setSortKey] = useState<DashboardSortKey | null>('tao_value_mid')
  const [sortDirection, setSortDirection] = useState<SortDirection>('desc')
  const [expandedNetuid, setExpandedNetuid] = useState<number | null>(null)

  const handleSort = useSortToggle(sortKey, sortDirection, setSortKey, setSortDirection)

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

  const sortedPositions = useMemo(() => {
    const positions = data?.top_positions || []
    if (!sortKey || !sortDirection) return positions

    return [...positions].sort((a, b) => {
      let aVal: number | string
      let bVal: number | string

      switch (sortKey as DashboardSortKey) {
        case 'subnet_name':
          aVal = a.subnet_name || `SN${a.netuid}`
          bVal = b.subnet_name || `SN${b.netuid}`
          break
        case 'tao_value_mid':
          aVal = safeFloat(a.tao_value_mid)
          bVal = safeFloat(b.tao_value_mid)
          break
        case 'weight_pct':
          aVal = safeFloat(a.weight_pct)
          bVal = safeFloat(b.weight_pct)
          break
        case 'price_change_24h': {
          const aV = enrichedLookup.get(a.netuid)?.volatile?.price_change_24h
          const bV = enrichedLookup.get(b.netuid)?.volatile?.price_change_24h
          aVal = aV ?? 0
          bVal = bV ?? 0
          break
        }
        case 'current_apy':
          aVal = safeFloat(a.current_apy)
          bVal = safeFloat(b.current_apy)
          break
        case 'cost_basis_tao':
          aVal = safeFloat(a.cost_basis_tao)
          bVal = safeFloat(b.cost_basis_tao)
          break
        case 'unrealized_pnl_pct':
          aVal = safeFloat(a.unrealized_pnl_pct)
          bVal = safeFloat(b.unrealized_pnl_pct)
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
  }, [data?.top_positions, sortKey, sortDirection, enrichedLookup])

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

  const { portfolio, action_items, market_pulse } = data

  // Compute Portfolio Risk metrics
  const drawdownPct = Math.abs(safeFloat(portfolio.executable_drawdown_pct))
  const drawdownLimit = 15
  const drawdownColor =
    drawdownPct < 5 ? 'bg-green-500' : drawdownPct < 10 ? 'bg-yellow-500' : 'bg-red-500'
  const drawdownTextColor =
    drawdownPct < 5 ? 'text-green-400' : drawdownPct < 10 ? 'text-yellow-400' : 'text-red-400'

  // Compute HHI from position weights
  const positions = data.top_positions || []
  const hhi = positions.reduce((sum, p) => {
    const w = safeFloat(p.weight_pct)
    return sum + w * w
  }, 0)
  const hhiLabel =
    hhi < 1500 ? 'Well Diversified' : hhi < 2500 ? 'Moderate' : 'Concentrated'
  const hhiColor =
    hhi < 1500 ? 'text-green-400' : hhi < 2500 ? 'text-yellow-400' : 'text-red-400'

  // Largest position
  const largestPos = positions.length > 0
    ? positions.reduce((max, p) =>
        safeFloat(p.weight_pct) > safeFloat(max.weight_pct) ? p : max
      , positions[0])
    : null

  // Slippage risk: (nav_mid - nav_exec_100pct) / nav_mid
  const navMid = safeFloat(portfolio.nav_mid)
  const navExec = safeFloat(portfolio.nav_exec_100pct)
  const slippagePct = navMid > 0 ? ((navMid - navExec) / navMid) * 100 : 0
  const slippageColor =
    slippagePct < 2 ? 'text-green-400' : slippagePct < 5 ? 'text-yellow-400' : 'text-red-400'

  return (
    <div className="space-y-6">
      <div className="flex items-center justify-between">
        <h1 className="text-2xl font-bold">Dashboard</h1>
        <div className="text-sm text-gray-500">
          Last updated: {new Date(data.generated_at).toLocaleTimeString()}
        </div>
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

      {/* Portfolio Overview – dual currency, rolling returns, projections */}
      <PortfolioOverviewCards />

      {/* Portfolio Risk & Market Pulse */}
      <div className="grid grid-cols-1 md:grid-cols-2 gap-4">
        {/* Portfolio Risk Card */}
        <div className="bg-gray-800 rounded-lg p-6 border border-gray-700">
          <h3 className="text-lg font-semibold mb-4 flex items-center gap-2">
            <Shield className="w-5 h-5" />
            Portfolio Risk
          </h3>
          <div className="space-y-4">
            {/* Drawdown */}
            <div>
              <div className="flex justify-between items-center mb-1">
                <span className="text-sm text-gray-400">Drawdown</span>
                <span className={`font-mono text-sm ${drawdownTextColor}`}>
                  {drawdownPct.toFixed(1)}%
                </span>
              </div>
              <div className="relative w-full bg-gray-700 rounded-full h-2.5">
                <div
                  className={`${drawdownColor} h-2.5 rounded-full transition-all`}
                  style={{ width: `${Math.min((drawdownPct / drawdownLimit) * 100, 100)}%` }}
                />
                {/* Limit marker at 15% */}
                <div
                  className="absolute top-0 h-2.5 w-0.5 bg-white/60"
                  style={{ left: '100%' }}
                  title={`Limit: ${drawdownLimit}%`}
                />
              </div>
              <div className="flex justify-between text-xs text-gray-600 mt-0.5">
                <span>0%</span>
                <span>{drawdownLimit}% limit</span>
              </div>
            </div>

            {/* Concentration */}
            <div>
              <div className="flex justify-between items-center mb-1">
                <span className="text-sm text-gray-400">Concentration</span>
                <span className={`font-mono text-sm ${hhiColor}`}>
                  {hhiLabel}
                </span>
              </div>
              <div className="text-xs text-gray-500">
                HHI: {Math.round(hhi).toLocaleString()}
                {largestPos && (
                  <span className="ml-2">
                    · Largest: {largestPos.subnet_name || `SN${largestPos.netuid}`} ({safeFloat(largestPos.weight_pct).toFixed(1)}%)
                  </span>
                )}
              </div>
            </div>

            {/* Slippage Risk */}
            <div>
              <div className="flex justify-between items-center">
                <span className="text-sm text-gray-400">Exit Slippage (100%)</span>
                <span className={`font-mono text-sm ${slippageColor}`}>
                  {slippagePct.toFixed(2)}%
                </span>
              </div>
              <div className="text-xs text-gray-500 mt-0.5">
                NAV impact: {formatTaoShort(navMid - navExec)} τ
              </div>
            </div>
          </div>
        </div>

        {/* Market Pulse Card */}
        <div className="bg-gray-800 rounded-lg p-6 border border-gray-700">
          <h3 className="text-lg font-semibold mb-4 flex items-center gap-2">
            <BarChart3 className="w-5 h-5" />
            Market Pulse
          </h3>
          {market_pulse && market_pulse.taostats_available ? (
            <div className="space-y-4">
              {/* Portfolio 24h Change */}
              <div className="flex justify-between items-center">
                <span className="text-sm text-gray-400">Portfolio 24h</span>
                {market_pulse.portfolio_24h_change_pct != null ? (
                  <span className={`text-xl font-bold font-mono ${
                    safeFloat(market_pulse.portfolio_24h_change_pct) >= 0
                      ? 'text-green-400'
                      : 'text-red-400'
                  }`}>
                    {formatPercent(market_pulse.portfolio_24h_change_pct)}
                  </span>
                ) : (
                  <span className="text-gray-600 font-mono">--</span>
                )}
              </div>

              {/* Sentiment */}
              <div className="flex justify-between items-center">
                <span className="text-sm text-gray-400">Sentiment</span>
                <div className="flex items-center gap-2">
                  {market_pulse.avg_sentiment_index != null && (
                    <span className="text-sm font-mono text-gray-300">
                      {Math.round(market_pulse.avg_sentiment_index)}
                    </span>
                  )}
                  <SentimentBadge
                    sentiment={market_pulse.avg_sentiment_label}
                    index={market_pulse.avg_sentiment_index}
                  />
                </div>
              </div>

              {/* 24h Volume */}
              <div className="flex justify-between items-center">
                <span className="text-sm text-gray-400">24h Volume</span>
                <span className="font-mono text-sm text-gray-300">
                  {market_pulse.total_volume_24h_tao != null
                    ? formatCompact(safeFloat(market_pulse.total_volume_24h_tao)) + ' τ'
                    : '--'}
                </span>
              </div>
              {market_pulse.net_buy_pressure_pct != null && (
                <div className="flex justify-between items-center">
                  <span className="text-sm text-gray-400">Buy Pressure</span>
                  <span className={`font-mono text-sm ${
                    safeFloat(market_pulse.net_buy_pressure_pct) >= 0
                      ? 'text-green-400'
                      : 'text-red-400'
                  }`}>
                    {formatPercent(market_pulse.net_buy_pressure_pct)}
                  </span>
                </div>
              )}

              {/* Top Mover */}
              {market_pulse.top_mover_name && (
                <div className="flex justify-between items-center">
                  <span className="text-sm text-gray-400">Top Mover</span>
                  <div className="text-right">
                    <span className="text-sm text-gray-300">{market_pulse.top_mover_name}</span>
                    {market_pulse.top_mover_change_24h != null && (
                      <span className={`ml-2 font-mono text-sm ${
                        safeFloat(market_pulse.top_mover_change_24h) >= 0
                          ? 'text-green-400'
                          : 'text-red-400'
                      }`}>
                        {formatPercent(market_pulse.top_mover_change_24h)}
                      </span>
                    )}
                  </div>
                </div>
              )}
            </div>
          ) : (
            <div className="flex items-center justify-center h-32 text-gray-500 text-sm">
              Market data temporarily unavailable
            </div>
          )}
        </div>
      </div>

      {/* Allocation */}
      <div className="bg-gray-800 rounded-lg p-6 border border-gray-700">
        <h3 className="text-lg font-semibold mb-4">Allocation</h3>
        <div className="space-y-3">
          <div>
            <div className="flex justify-between text-sm mb-1">
              <span className="text-gray-400">Root (SN0)</span>
              <span>{formatTao(portfolio.allocation.root_tao)} ({safeFloat(portfolio.allocation.root_pct).toFixed(1)}%)</span>
            </div>
            <div className="w-full bg-gray-700 rounded-full h-2">
              <div
                className="bg-blue-500 h-2 rounded-full"
                style={{ width: `${Math.min(safeFloat(portfolio.allocation.root_pct), 100)}%` }}
              ></div>
            </div>
          </div>
          <div>
            <div className="flex justify-between text-sm mb-1">
              <span className="text-gray-400">dTAO Sleeve</span>
              <span>{formatTao(portfolio.allocation.dtao_tao)} ({safeFloat(portfolio.allocation.dtao_pct).toFixed(1)}%)</span>
            </div>
            <div className="w-full bg-gray-700 rounded-full h-2">
              <div
                className="bg-tao-500 h-2 rounded-full"
                style={{ width: `${Math.min(safeFloat(portfolio.allocation.dtao_pct), 100)}%` }}
              ></div>
            </div>
          </div>
          <div>
            <div className="flex justify-between text-sm mb-1">
              <span className="text-gray-400">Unstaked Buffer</span>
              <span>{formatTao(portfolio.allocation.unstaked_tao)} ({safeFloat(portfolio.allocation.unstaked_pct).toFixed(1)}%)</span>
            </div>
            <div className="w-full bg-gray-700 rounded-full h-2">
              <div
                className="bg-green-500 h-2 rounded-full"
                style={{ width: `${Math.min(safeFloat(portfolio.allocation.unstaked_pct), 100)}%` }}
              ></div>
            </div>
          </div>
        </div>
      </div>


      {/* All Positions Table */}
      {sortedPositions.length > 0 && (
        <div className="bg-gray-800 rounded-lg border border-gray-700 overflow-hidden">
          <div className="px-6 py-4 border-b border-gray-700 flex items-center justify-between">
            <h3 className="text-lg font-semibold">All Positions</h3>
            <span className="text-sm text-gray-500">{sortedPositions.length} positions</span>
          </div>
          <div className="overflow-x-auto">
            <table className="w-full min-w-[1200px]">
              <thead className="bg-gray-900/50">
                <tr className="text-sm text-gray-400">
                  {/* Expand toggle */}
                  <th className="w-8 px-2 py-3" />
                  <SortableHeader<DashboardSortKey>
                    label="Subnet"
                    sortKey="subnet_name"
                    currentSortKey={sortKey}
                    currentDirection={sortDirection}
                    onSort={handleSort}
                  />
                  <th className="px-4 py-3 text-xs font-medium text-gray-400 uppercase tracking-wider">
                    7d Chart
                  </th>
                  <SortableHeader<DashboardSortKey>
                    label="TAO Value"
                    sortKey="tao_value_mid"
                    currentSortKey={sortKey}
                    currentDirection={sortDirection}
                    onSort={handleSort}
                    align="right"
                  />
                  <SortableHeader<DashboardSortKey>
                    label="Weight"
                    sortKey="weight_pct"
                    currentSortKey={sortKey}
                    currentDirection={sortDirection}
                    onSort={handleSort}
                    align="right"
                  />
                  <SortableHeader<DashboardSortKey>
                    label="Price / 24h"
                    sortKey="price_change_24h"
                    currentSortKey={sortKey}
                    currentDirection={sortDirection}
                    onSort={handleSort}
                    align="right"
                  />
                  <SortableHeader<DashboardSortKey>
                    label="APY / Yield"
                    sortKey="current_apy"
                    currentSortKey={sortKey}
                    currentDirection={sortDirection}
                    onSort={handleSort}
                    align="right"
                  />
                  <SortableHeader<DashboardSortKey>
                    label="Cost / Entry"
                    sortKey="cost_basis_tao"
                    currentSortKey={sortKey}
                    currentDirection={sortDirection}
                    onSort={handleSort}
                    align="right"
                  />
                  <SortableHeader<DashboardSortKey>
                    label="P&L"
                    sortKey="unrealized_pnl_pct"
                    currentSortKey={sortKey}
                    currentDirection={sortDirection}
                    onSort={handleSort}
                    align="right"
                  />
                  <th className="px-4 py-3 text-xs font-medium text-gray-400 uppercase tracking-wider">
                    Sentiment
                  </th>
                  <SortableHeader<DashboardSortKey>
                    label="Regime"
                    sortKey="flow_regime"
                    currentSortKey={sortKey}
                    currentDirection={sortDirection}
                    onSort={handleSort}
                  />
                </tr>
              </thead>
              <tbody className="divide-y divide-gray-700">
                {sortedPositions.map((position) => {
                  const enriched = enrichedLookup.get(position.netuid)
                  const v = enriched?.volatile ?? null
                  const isExpanded = expandedNetuid === position.netuid
                  return (
                    <DashboardPositionRow
                      key={position.netuid}
                      position={position}
                      enriched={enriched ?? null}
                      v={v}
                      isExpanded={isExpanded}
                      onToggle={() => setExpandedNetuid(isExpanded ? null : position.netuid)}
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

function DashboardPositionRow({
  position,
  enriched,
  v,
  isExpanded,
  onToggle,
}: {
  position: PositionSummary
  enriched: EnrichedSubnet | null
  v: VolatilePoolData | null
  isExpanded: boolean
  onToggle: () => void
}) {
  return (
    <>
      <tr
        className="hover:bg-gray-700/30 cursor-pointer"
        onClick={onToggle}
      >
        {/* Expand chevron */}
        <td className="px-2 py-3 text-gray-500">
          {isExpanded ? <ChevronDown className="w-4 h-4" /> : <ChevronRight className="w-4 h-4" />}
        </td>

        {/* Subnet name + logo */}
        <td className="px-4 py-3">
          <div className="flex items-center gap-2">
            {enriched?.identity?.logo_url && (
              <img
                src={enriched.identity.logo_url}
                alt=""
                className="w-6 h-6 rounded-full flex-shrink-0 bg-gray-700"
                onError={(e) => { (e.target as HTMLImageElement).style.display = 'none' }}
              />
            )}
            <div className="min-w-0">
              <div className="font-medium text-sm">{position.subnet_name || `SN${position.netuid}`}</div>
              <div className="text-xs text-gray-500">SN{position.netuid}</div>
            </div>
          </div>
        </td>

        {/* 7d Sparkline */}
        <td className="px-2 py-3 align-middle">
          <SparklineCell data={v?.sparkline_7d} />
        </td>

        {/* TAO Value + alpha */}
        <td className="px-4 py-3 text-right">
          <div className="font-mono text-sm">{formatTao(position.tao_value_mid)} τ</div>
          <div className="text-xs text-gray-500 font-mono">{formatTao(position.alpha_balance)} α</div>
        </td>

        {/* Weight */}
        <td className="px-4 py-3 text-right font-mono text-sm">
          {safeFloat(position.weight_pct).toFixed(1)}%
        </td>

        {/* Price + 24h Change */}
        <td className="px-4 py-3">
          <div className="text-right">
            {enriched ? (
              <div className="text-sm font-mono">{safeFloat(enriched.alpha_price_tao).toFixed(6)} τ</div>
            ) : (
              <div className="text-sm text-gray-600">--</div>
            )}
            <PriceChangeCell change24h={v?.price_change_24h} />
          </div>
        </td>

        {/* APY + Daily Yield */}
        <td className="px-4 py-3 text-right">
          {position.current_apy ? (
            <>
              <div className="font-mono text-sm text-green-400">
                {safeFloat(position.current_apy).toFixed(1)}%
              </div>
              <div className="text-xs text-gray-400 font-mono">
                +{position.daily_yield_tao ? safeFloat(position.daily_yield_tao).toFixed(4) : '0'} τ/d
              </div>
            </>
          ) : (
            <span className="text-gray-600 text-sm">--</span>
          )}
        </td>

        {/* Cost Basis + Entry Price */}
        <td className="px-4 py-3 text-right">
          <div className="font-mono text-sm">{formatTao(position.cost_basis_tao)} τ</div>
          <div className="text-xs text-gray-500 font-mono">
            @ {safeFloat(position.entry_price_tao).toFixed(6)}
          </div>
        </td>

        {/* Unrealized P&L */}
        <td className="px-4 py-3 text-right">
          <span className={`font-mono text-sm ${safeFloat(position.unrealized_pnl_tao) >= 0 ? 'text-green-400' : 'text-red-400'}`}>
            {formatTao(position.unrealized_pnl_tao)} τ
          </span>
          <div className={`text-xs font-mono ${safeFloat(position.unrealized_pnl_pct) >= 0 ? 'text-green-400' : 'text-red-400'}`}>
            {formatPercent(position.unrealized_pnl_pct)}
          </div>
        </td>

        {/* Sentiment */}
        <td className="px-4 py-3">
          <SentimentBadge
            sentiment={v?.fear_greed_sentiment}
            index={v?.fear_greed_index}
          />
        </td>

        {/* Regime */}
        <td className="px-4 py-3">
          <RegimeBadge regime={position.flow_regime} />
        </td>
      </tr>

      {/* Expanded detail row */}
      {isExpanded && (
        <tr>
          <td colSpan={11} className="p-0">
            <DashboardPositionDetail position={position} enriched={enriched} />
          </td>
        </tr>
      )}
    </>
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

  return (
    <div className="bg-gray-900/50">
      {/* Position-specific details */}
      <div className="grid grid-cols-1 md:grid-cols-3 gap-6 p-4 text-sm border-b border-gray-800">
        {/* Column 1: Position Details */}
        <div className="space-y-2">
          <h4 className="text-xs font-semibold text-gray-400 uppercase tracking-wider">Position Details</h4>
          <div className="space-y-1">
            <DashDetailRow label="Entry Date" value={position.entry_date ? new Date(position.entry_date).toLocaleDateString() : '--'} />
            <DashDetailRow label="Entry Price" value={`${safeFloat(position.entry_price_tao).toFixed(6)} τ`} />
            <DashDetailRow
              label="Current Price"
              value={enriched ? `${safeFloat(enriched.alpha_price_tao).toFixed(6)} τ` : '--'}
            />
            <DashDetailRow label="Cost Basis" value={`${formatTao(position.cost_basis_tao)} τ`} />
            <DashDetailRow label="Realized P&L" value={`${formatTao(position.realized_pnl_tao)} τ`} />
            {position.validator_hotkey && (
              <DashDetailRow
                label="Validator"
                value={`${position.validator_hotkey.slice(0, 8)}...${position.validator_hotkey.slice(-6)}`}
              />
            )}
          </div>
        </div>

        {/* Column 2: Exit Analysis */}
        <div className="space-y-2">
          <h4 className="text-xs font-semibold text-gray-400 uppercase tracking-wider">Exit Analysis</h4>
          <div className="space-y-1">
            <DashDetailRow label="Mid NAV" value={`${formatTao(position.tao_value_mid)} τ`} />
            <DashDetailRow label="Exec NAV (50%)" value={`${formatTao(position.tao_value_exec_50pct)} τ`} />
            <DashDetailRow label="Exec NAV (100%)" value={`${formatTao(position.tao_value_exec_100pct)} τ`} />
            <DashDetailRow
              label="Slippage (50%)"
              value={`${safeFloat(position.exit_slippage_50pct).toFixed(2)}%`}
              valueColor={safeFloat(position.exit_slippage_50pct) > 5 ? 'text-red-400' : 'text-gray-300'}
            />
            <DashDetailRow
              label="Slippage (100%)"
              value={`${safeFloat(position.exit_slippage_100pct).toFixed(2)}%`}
              valueColor={safeFloat(position.exit_slippage_100pct) > 10 ? 'text-red-400' : 'text-gray-300'}
            />
          </div>
        </div>

        {/* Column 3: Recommendation */}
        <div className="space-y-2">
          <h4 className="text-xs font-semibold text-gray-400 uppercase tracking-wider">Recommendation</h4>
          <div className="space-y-1">
            {position.recommended_action ? (
              <>
                <div className="flex items-center gap-2 mb-2">
                  <span className={`px-2 py-0.5 rounded text-xs font-medium ${
                    position.recommended_action === 'sell' ? 'bg-red-600/20 text-red-400' :
                    position.recommended_action === 'buy' ? 'bg-green-600/20 text-green-400' :
                    'bg-yellow-600/20 text-yellow-400'
                  }`}>
                    {position.recommended_action.toUpperCase()}
                  </span>
                </div>
                {position.action_reason && (
                  <p className="text-xs text-gray-400 leading-relaxed">{position.action_reason}</p>
                )}
              </>
            ) : (
              <p className="text-xs text-gray-500">No action recommended</p>
            )}
          </div>
        </div>
      </div>

      {/* Market context: SubnetExpandedRow */}
      <SubnetExpandedRow
        volatile={v}
        identity={enriched?.identity}
        devActivity={enriched?.dev_activity}
        ownerAddress={enriched?.owner_address}
        ownerTake={enriched?.owner_take}
        ageDays={enriched?.age_days}
        holderCount={enriched?.holder_count}
        ineligibilityReasons={enriched?.ineligibility_reasons}
        taoflow1d={enriched?.taoflow_1d}
        taoflow3d={enriched?.taoflow_3d}
        taoflow7d={enriched?.taoflow_7d}
        taoflow14d={enriched?.taoflow_14d}
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
      <span className={`font-mono ${valueColor || 'text-gray-300'}`}>{value}</span>
    </div>
  )
}
