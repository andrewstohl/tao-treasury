import { useState, useMemo } from 'react'
import { useQuery } from '@tanstack/react-query'
import {
  Activity,
  ChevronRight,
  ChevronDown,
} from 'lucide-react'
import { api } from '../services/api'
import type { Dashboard as DashboardType, EnrichedSubnetListResponse, EnrichedSubnet, VolatilePoolData, PositionSummary, ClosedPosition } from '../types'
import { formatTao, formatPercent, safeFloat } from '../utils/format'
import SortableHeader, { useSortToggle, type SortDirection } from '../components/common/SortableHeader'
import SparklineCell from '../components/common/cells/SparklineCell'
import PriceChangeCell from '../components/common/cells/PriceChangeCell'
import RegimeBadge from '../components/common/cells/RegimeBadge'
import ViabilityBadge from '../components/common/cells/ViabilityBadge'
import SubnetExpandedRow, { FlowRow } from '../components/common/SubnetExpandedRow'
import PortfolioOverviewCards from '../components/dashboard/PortfolioOverviewCards'
import PerformanceRisk from '../components/dashboard/PerformanceRisk'

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

  const { portfolio, action_items } = data

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

      {/* Allocation & Market Pulse */}
      <div className="grid grid-cols-1 md:grid-cols-2 gap-4">
        {/* Allocation Card */}
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

        {/* Performance & Risk Card */}
        <PerformanceRisk />
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
                    Viability
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

                {/* Free TAO balance row */}
                {safeFloat(data?.free_tao_balance) > 0 && (
                  <tr className="bg-gray-900/30 text-gray-500">
                    <td className="px-2 py-2.5" />
                    <td className="px-4 py-2.5">
                      <div className="flex items-center gap-2">
                        <div className="w-6 h-6 rounded-full flex-shrink-0 bg-green-900/40 flex items-center justify-center text-green-500 text-xs font-bold">τ</div>
                        <div className="min-w-0">
                          <div className="font-medium text-sm text-gray-400">Free TAO</div>
                          <div className="text-xs text-gray-600">Unstaked buffer</div>
                        </div>
                      </div>
                    </td>
                    <td className="px-2 py-2.5" />
                    <td className="px-4 py-2.5 text-right">
                      <div className="font-mono text-sm text-gray-400">{formatTao(data?.free_tao_balance ?? '0')} τ</div>
                    </td>
                    <td colSpan={7} />
                  </tr>
                )}

                {/* Closed positions */}
                {(data?.closed_positions ?? []).length > 0 && (
                  <>
                    <tr className="bg-gray-900/50">
                      <td colSpan={11} className="px-4 py-2 text-xs text-gray-500 uppercase tracking-wider font-medium">
                        Closed Positions ({data!.closed_positions.length})
                      </td>
                    </tr>
                    {data!.closed_positions.map((cp) => (
                      <ClosedPositionRow key={cp.netuid} position={cp} enrichedLookup={enrichedLookup} />
                    ))}
                  </>
                )}
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

        {/* Viability */}
        <td className="px-4 py-3">
          <ViabilityBadge
            tier={enriched?.viability_tier}
            score={enriched?.viability_score}
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

function ClosedPositionRow({
  position,
  enrichedLookup,
}: {
  position: ClosedPosition
  enrichedLookup: Map<number, EnrichedSubnet>
}) {
  const enriched = enrichedLookup.get(position.netuid)
  const pnl = safeFloat(position.realized_pnl_tao)

  return (
    <tr className="text-gray-500 hover:bg-gray-700/20">
      <td className="px-2 py-2" />
      <td className="px-4 py-2">
        <div className="flex items-center gap-2">
          {enriched?.identity?.logo_url && (
            <img
              src={enriched.identity.logo_url}
              alt=""
              className="w-5 h-5 rounded-full flex-shrink-0 bg-gray-700 opacity-50"
              onError={(e) => { (e.target as HTMLImageElement).style.display = 'none' }}
            />
          )}
          <div className="min-w-0">
            <div className="text-sm text-gray-500">{position.subnet_name}</div>
            <div className="text-xs text-gray-600">SN{position.netuid}</div>
          </div>
        </div>
      </td>
      <td className="px-2 py-2" />
      <td className="px-4 py-2 text-right font-mono text-sm text-gray-600">0 τ</td>
      <td className="px-4 py-2" />
      <td className="px-4 py-2" />
      <td className="px-4 py-2" />
      <td className="px-4 py-2 text-right">
        <div className="font-mono text-sm text-gray-600">{formatTao(position.total_staked_tao)} τ</div>
        <div className="text-xs text-gray-600">closed</div>
      </td>
      <td className="px-4 py-2 text-right">
        <span className={`font-mono text-sm ${pnl >= 0 ? 'text-green-400/70' : 'text-red-400/70'}`}>
          {formatTao(position.realized_pnl_tao)} τ
        </span>
        <div className="text-xs text-gray-600">realized</div>
      </td>
      <td className="px-4 py-2" />
      <td className="px-4 py-2" />
    </tr>
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

      {/* Row 2+3: About, then Pool Composition + Subnet Info (via SubnetExpandedRow with taoflow hidden) */}
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
      <span className={`font-mono ${valueColor || 'text-gray-300'}`}>{value}</span>
    </div>
  )
}
