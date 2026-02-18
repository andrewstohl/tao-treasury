import { useCurrency } from '../../../contexts/CurrencyContext'
import { formatTaoShort, formatUsd, formatApy, safeFloat } from '../../../utils/format'
import type { PositionSummary, EnrichedSubnet } from '../../../types'

interface PositionKPICardsProps {
  position: PositionSummary
  enriched: EnrichedSubnet | null
  taoPrice: number
}

export default function PositionKPICards({ position, enriched, taoPrice }: PositionKPICardsProps) {
  const { currency } = useCurrency()

  // Core values from position
  const taoValue = safeFloat(position.tao_value_mid)
  const unrealizedPnl = safeFloat(position.unrealized_pnl_tao)
  const realizedPnl = safeFloat(position.realized_pnl_tao)
  const apy = safeFloat(position.current_apy)
  const dailyYield = safeFloat(position.daily_yield_tao)

  // Use pre-computed yield and alpha P&L from backend (single source of truth)
  const yieldValueTao = safeFloat(position.unrealized_yield_tao)
  const realizedYieldTao = safeFloat(position.realized_yield_tao)
  const alphaPnlTao = safeFloat(position.unrealized_alpha_pnl_tao)
  const realizedAlphaPnlTao = safeFloat(position.realized_alpha_pnl_tao)

  // Totals (matching portfolio-level cards: headline = realized + unrealized)
  const totalYieldTao = realizedYieldTao + yieldValueTao
  const totalAlphaPnlTao = realizedAlphaPnlTao + alphaPnlTao

  // USD conversions
  const taoValueUsd = taoValue * taoPrice
  const unrealizedPnlUsd = unrealizedPnl * taoPrice
  const realizedPnlUsd = realizedPnl * taoPrice
  const yieldValueUsd = yieldValueTao * taoPrice
  const alphaPnlUsd = alphaPnlTao * taoPrice
  const realizedYieldUsd = realizedYieldTao * taoPrice
  const realizedAlphaPnlUsd = realizedAlphaPnlTao * taoPrice
  const totalYieldUsd = totalYieldTao * taoPrice
  const totalAlphaPnlUsd = totalAlphaPnlTao * taoPrice

  // Projections
  const weeklyYield = dailyYield * 7
  const monthlyYield = dailyYield * 30

  const pnlColor = (v: number) => v >= 0 ? 'text-green-400' : 'text-red-400'

  const formatPrimary = (tao: number, usd: number) =>
    currency === 'tao' ? `${formatTaoShort(tao)}τ` : formatUsd(usd)

  return (
    <div className="grid grid-cols-1 md:grid-cols-5 gap-3">
      {/* Card 1: Current Value */}
      <div className="bg-[#1e2128] rounded-lg p-4">
        <div className="flex items-start justify-between">
          <div className="text-sm font-medium text-white">Current Value</div>
          <div className="text-right">
            <div className="text-sm font-bold text-white">
              {currency === 'tao' ? `${formatTaoShort(taoValue)}τ` : formatUsd(taoValueUsd)}
            </div>
            <div className="text-xs text-[#8a8f98]">
              {currency === 'tao' ? formatUsd(taoValueUsd) : `${formatTaoShort(taoValue)}τ`}
            </div>
          </div>
        </div>

        <div className="mt-2.5 pt-2.5 border-t border-[#2a2f38] flex justify-between">
          <div>
            <div className="text-xs text-[#8a8f98]">Realized</div>
            <div className={`tabular-nums text-sm ${pnlColor(realizedPnl)}`}>
              {formatPrimary(realizedPnl, realizedPnlUsd)}
            </div>
          </div>
          <div>
            <div className="text-xs text-[#8a8f98]">Unrealized</div>
            <div className={`tabular-nums text-sm ${pnlColor(unrealizedPnl)}`}>
              {formatPrimary(unrealizedPnl, unrealizedPnlUsd)}
            </div>
          </div>
          <div>
            <div className="text-xs text-[#8a8f98]">Total</div>
            <div className={`tabular-nums text-sm ${pnlColor(realizedPnl + unrealizedPnl)}`}>
              {formatPrimary(realizedPnl + unrealizedPnl, realizedPnlUsd + unrealizedPnlUsd)}
            </div>
          </div>
        </div>
      </div>

      {/* Card 2: Yield */}
      <div className="bg-[#1e2128] rounded-lg p-4">
        <div className="flex items-start justify-between">
          <div className="text-sm font-medium text-white">Yield</div>
          <div className="text-right">
            <div className="text-sm font-bold text-white">
              {currency === 'tao' ? `${formatTaoShort(totalYieldTao)}τ` : formatUsd(totalYieldUsd)}
            </div>
            <div className="text-xs text-[#8a8f98]">
              {currency === 'tao' ? formatUsd(totalYieldUsd) : `${formatTaoShort(totalYieldTao)}τ`}
            </div>
          </div>
        </div>

        <div className="mt-2.5 pt-2.5 border-t border-[#2a2f38] flex justify-between">
          <div>
            <div className="text-xs text-[#8a8f98]">Realized</div>
            <div className="tabular-nums text-sm text-white">
              {formatPrimary(realizedYieldTao, realizedYieldUsd)}
            </div>
          </div>
          <div>
            <div className="text-xs text-[#8a8f98]">Unrealized</div>
            <div className="tabular-nums text-sm text-white">
              {formatPrimary(yieldValueTao, yieldValueUsd)}
            </div>
          </div>
        </div>
      </div>

      {/* Card 3: Alpha (Price) */}
      <div className="bg-[#1e2128] rounded-lg p-4">
        <div className="flex items-start justify-between">
          <div className="text-sm font-medium text-white">Alpha</div>
          <div className="text-right">
            <div className="text-sm font-bold text-white">
              {currency === 'tao' ? `${formatTaoShort(totalAlphaPnlTao)}τ` : formatUsd(totalAlphaPnlUsd)}
            </div>
            <div className="text-xs text-[#8a8f98]">
              {currency === 'tao' ? formatUsd(totalAlphaPnlUsd) : `${formatTaoShort(totalAlphaPnlTao)}τ`}
            </div>
          </div>
        </div>

        <div className="mt-2.5 pt-2.5 border-t border-[#2a2f38] flex justify-between">
          <div>
            <div className="text-xs text-[#8a8f98]">Realized</div>
            <div className="tabular-nums text-sm text-white">
              {formatPrimary(realizedAlphaPnlTao, realizedAlphaPnlUsd)}
            </div>
          </div>
          <div>
            <div className="text-xs text-[#8a8f98]">Unrealized</div>
            <div className="tabular-nums text-sm text-white">
              {formatPrimary(alphaPnlTao, alphaPnlUsd)}
            </div>
          </div>
        </div>
      </div>

      {/* Card 4: APY */}
      <div className="bg-[#1e2128] rounded-lg p-4">
        <div className="flex items-start justify-between">
          <div className="text-sm font-medium text-white">APY</div>
          <div className="text-right">
            <div className="text-sm font-bold text-white">
              {formatApy(apy)}
            </div>
            <div className="text-xs text-[#8a8f98] tabular-nums">
              {formatTaoShort(dailyYield)}τ/day
            </div>
          </div>
        </div>

        <div className="mt-2.5 pt-2.5 border-t border-[#2a2f38] flex justify-between">
          <div>
            <div className="text-xs text-[#8a8f98]">7d Proj.</div>
            <div className="tabular-nums text-sm text-green-400">
              {formatTaoShort(weeklyYield)}τ
            </div>
          </div>
          <div>
            <div className="text-xs text-[#8a8f98]">30d Proj.</div>
            <div className="tabular-nums text-sm text-green-400">
              {formatTaoShort(monthlyYield)}τ
            </div>
          </div>
        </div>
      </div>

      {/* Card 5: Position Details */}
      <div className="bg-[#1e2128] rounded-lg p-4">
        <div className="flex items-start justify-between">
          <div className="text-sm font-medium text-white">Position</div>
          <div className="text-right">
            <div className="text-sm font-bold text-white">
              {safeFloat(position.weight_pct).toFixed(1)}%
            </div>
            <div className="text-xs text-[#8a8f98]">
              of portfolio
            </div>
          </div>
        </div>

        <div className="mt-2.5 pt-2.5 border-t border-[#2a2f38] flex justify-between">
          <div>
            <div className="text-xs text-[#8a8f98]">Entry Date</div>
            <div className="tabular-nums text-sm text-white">
              {position.entry_date ? new Date(position.entry_date).toLocaleDateString() : '--'}
            </div>
          </div>
          <div>
            <div className="text-xs text-[#8a8f98]">Holding</div>
            <div className="tabular-nums text-sm text-white">
              {position.entry_date
                ? `${Math.floor((Date.now() - new Date(position.entry_date).getTime()) / (1000 * 60 * 60 * 24))}d`
                : '--'}
            </div>
          </div>
        </div>
      </div>
    </div>
  )
}
