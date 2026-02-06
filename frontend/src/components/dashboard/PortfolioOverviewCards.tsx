import { useQuery } from '@tanstack/react-query'
import {
  ArrowUpDown,
} from 'lucide-react'
import { api } from '../../services/api'
import { useCurrency } from '../../contexts/CurrencyContext'
import type { PortfolioOverview, DualCurrencyValue } from '../../types'
import { formatTao, formatTaoShort, formatUsd, formatApy, safeFloat } from '../../utils/format'

function DualValue({
  value,
  primaryCurrency,
  signColored = false,
  prefix = '',
  short = false,
}: {
  value: DualCurrencyValue
  primaryCurrency: 'tao' | 'usd'
  signColored?: boolean
  prefix?: string
  short?: boolean
}) {
  const primary = primaryCurrency === 'tao' ? value.tao : value.usd
  const secondary = primaryCurrency === 'tao' ? value.usd : value.tao
  const primaryNum = parseFloat(primary)
  const colorClass = signColored
    ? primaryNum >= 0
      ? 'text-green-400'
      : 'text-red-400'
    : 'text-white'

  const formatPrimary = primaryCurrency === 'tao' ? (short ? formatTaoShort : formatTao) : formatUsd
  const formatSecondary = primaryCurrency === 'tao' ? formatUsd : (short ? formatTaoShort : formatTao)
  const primarySuffix = primaryCurrency === 'tao' ? ' τ' : ''
  const secondarySuffix = primaryCurrency === 'usd' ? ' τ' : ''

  return (
    <div>
      <div className={`text-lg font-bold ${colorClass}`}>
        {prefix}{formatPrimary(primary)}{primarySuffix}
      </div>
      <div className="text-xs text-[#8a8f98]">
        {prefix}{formatSecondary(secondary)}{secondarySuffix}
      </div>
    </div>
  )
}

export default function PortfolioOverviewCards() {
  const { currency, toggleCurrency } = useCurrency()

  const { data: overview, isLoading } = useQuery<PortfolioOverview>({
    queryKey: ['portfolio-overview'],
    queryFn: api.getPortfolioOverview,
    refetchInterval: 120000,  // 2 min - reduced to avoid rate limits
  })

  if (isLoading || !overview) {
    return (
      <div className="grid grid-cols-1 md:grid-cols-5 gap-3">
        {[...Array(5)].map((_, i) => (
          <div
            key={i}
            className="bg-[#16181d] rounded-lg p-4 border border-[#2a2f38] animate-pulse h-32"
          />
        ))}
      </div>
    )
  }

  // Core values
  const unrealizedTao = safeFloat(overview.pnl.unrealized.tao)
  const unrealizedUsd = safeFloat(overview.pnl.unrealized.usd)
  const realizedTao = safeFloat(overview.pnl.realized.tao)
  const realizedUsd = safeFloat(overview.pnl.realized.usd)
  const apyNum = safeFloat(overview.yield_income.portfolio_apy)

  // Yield/Alpha decomposition of unrealized P&L
  const yieldGainTao = safeFloat(overview.yield_income.unrealized_yield.tao)
  const yieldGainUsd = safeFloat(overview.yield_income.unrealized_yield.usd)
  const alphaPnlTao = unrealizedTao - yieldGainTao
  const alphaPnlUsd = unrealizedUsd - yieldGainUsd

  // Full alpha decomposition across realized + unrealized
  const realizedYieldTao = safeFloat(overview.yield_income.realized_yield.tao)
  const realizedYieldUsd = safeFloat(overview.yield_income.realized_yield.usd)
  const realizedAlphaTao = realizedTao - realizedYieldTao
  const realizedAlphaUsd = realizedUsd - realizedYieldUsd
  const unrealizedAlphaTao = alphaPnlTao
  const unrealizedAlphaUsd = alphaPnlUsd
  const totalAlphaTao = realizedAlphaTao + unrealizedAlphaTao
  const totalAlphaUsd = realizedAlphaUsd + unrealizedAlphaUsd

  const pnlColor = (v: number) => v >= 0 ? 'text-green-400' : 'text-red-400'

  return (
    <div className="space-y-3">
      {/* Currency Toggle - inline right */}
      <div className="flex items-center justify-start">
        <button
          onClick={toggleCurrency}
          className="flex items-center gap-1.5 px-3 py-1.5 rounded-lg bg-[#1e2128] hover:bg-[#262b33] text-sm text-[#9ca3af] transition-colors"
        >
          <ArrowUpDown className="w-4 h-4" />
          {currency === 'tao' ? 'τ TAO' : '$ USD'}
        </button>
      </div>

      {/* Cards Grid */}
      <div className="grid grid-cols-1 md:grid-cols-5 gap-3">
        {/* Card 1: Portfolio Value */}
        <div className="bg-[#16181d] rounded-lg p-4 border border-[#2a2f38]">
          <div className="flex items-start justify-between">
            <div className="text-base font-bold text-white">Current Value</div>
            <div className="text-right">
              <DualValue value={overview.nav_mid} primaryCurrency={currency} short />
            </div>
          </div>

          <div className="mt-2.5 pt-2.5 border-t border-[#2a2f38] flex justify-between">
            <div>
              <div className="text-xs text-[#8a8f98]">Realized</div>
              <div className={`tabular-nums text-sm ${pnlColor(realizedTao)}`}>
                {currency === 'tao' ? `${formatTaoShort(realizedTao)}τ` : formatUsd(realizedUsd)}
              </div>
            </div>
            <div>
              <div className="text-xs text-[#8a8f98]">Unrealized</div>
              <div className={`tabular-nums text-sm ${pnlColor(unrealizedTao)}`}>
                {currency === 'tao' ? `${formatTaoShort(unrealizedTao)}τ` : formatUsd(unrealizedUsd)}
              </div>
            </div>
            <div>
              <div className="text-xs text-[#8a8f98]">Total</div>
              <div className={`tabular-nums text-sm ${pnlColor(realizedTao + unrealizedTao)}`}>
                {currency === 'tao' ? `${formatTaoShort(realizedTao + unrealizedTao)}τ` : formatUsd(realizedUsd + unrealizedUsd)}
              </div>
            </div>
          </div>
        </div>

        {/* Card 2: Yield */}
        <div className="bg-[#16181d] rounded-lg p-4 border border-[#2a2f38]">
          <div className="flex items-start justify-between">
            <div className="text-base font-bold text-white">Yield</div>
            <div className="text-right">
              <DualValue value={overview.yield_income.total_yield} primaryCurrency={currency} short />
            </div>
          </div>

          <div className="mt-2.5 pt-2.5 border-t border-[#2a2f38] flex justify-between">
            <div>
              <div className="text-xs text-[#8a8f98]">Realized</div>
              <div className={`tabular-nums text-sm ${pnlColor(safeFloat(overview.yield_income.realized_yield.tao))}`}>
                {currency === 'tao'
                  ? `${formatTaoShort(overview.yield_income.realized_yield.tao)}τ`
                  : formatUsd(overview.yield_income.realized_yield.usd)}
              </div>
            </div>
            <div>
              <div className="text-xs text-[#8a8f98]">Unrealized</div>
              <div className={`tabular-nums text-sm ${pnlColor(safeFloat(overview.yield_income.unrealized_yield.tao))}`}>
                {currency === 'tao'
                  ? `${formatTaoShort(overview.yield_income.unrealized_yield.tao)}τ`
                  : formatUsd(overview.yield_income.unrealized_yield.usd)}
              </div>
            </div>
          </div>
        </div>

        {/* Card 3: Alpha */}
        <div className="bg-[#16181d] rounded-lg p-4 border border-[#2a2f38]">
          <div className="flex items-start justify-between">
            <div className="text-base font-bold text-white">Alpha</div>
            <div className="text-right">
              <DualValue
                value={{ tao: String(totalAlphaTao), usd: String(totalAlphaUsd) }}
                primaryCurrency={currency}
                short
              />
            </div>
          </div>

          <div className="mt-2.5 pt-2.5 border-t border-[#2a2f38] flex justify-between">
            <div>
              <div className="text-xs text-[#8a8f98]">Realized</div>
              <div className={`tabular-nums text-sm ${pnlColor(realizedAlphaTao)}`}>
                {currency === 'tao' ? `${formatTaoShort(realizedAlphaTao)}τ` : formatUsd(realizedAlphaUsd)}
              </div>
            </div>
            <div>
              <div className="text-xs text-[#8a8f98]">Unrealized</div>
              <div className={`tabular-nums text-sm ${pnlColor(unrealizedAlphaTao)}`}>
                {currency === 'tao' ? `${formatTaoShort(unrealizedAlphaTao)}τ` : formatUsd(unrealizedAlphaUsd)}
              </div>
            </div>
          </div>
        </div>

        {/* Card 4: APY */}
        <div className="bg-[#16181d] rounded-lg p-4 border border-[#2a2f38]">
          <div className="flex items-start justify-between">
            <div className="text-base font-bold text-white">APY</div>
            <div className="text-right">
              <div className="text-lg font-bold text-white">
                {formatApy(apyNum)}
              </div>
              <div className="text-xs text-[#8a8f98] tabular-nums">
                {formatTaoShort(overview.yield_income.daily.tao)}τ/day
              </div>
            </div>
          </div>

          <div className="mt-2.5 pt-2.5 border-t border-[#2a2f38] flex justify-between">
            <div>
              <div className="text-xs text-[#8a8f98]">7d Proj.</div>
              <div className="tabular-nums text-sm text-green-400">
                {formatTaoShort(overview.yield_income.weekly.tao)}τ
              </div>
            </div>
            <div>
              <div className="text-xs text-[#8a8f98]">30d Proj.</div>
              <div className="tabular-nums text-sm text-green-400">
                {formatTaoShort(overview.yield_income.monthly.tao)}τ
              </div>
            </div>
          </div>
        </div>

        {/* Card 5: FX Exposure */}
        <div className="bg-[#16181d] rounded-lg p-4 border border-[#2a2f38]">
          <div className="flex items-start justify-between">
            <div className="flex items-center gap-1.5">
              <div className="text-base font-bold text-white">FX Exposure</div>
              {!overview.conversion_exposure.has_complete_usd_history && (
                <span className="text-yellow-500/70 text-xs" title="Partial USD history available">*</span>
              )}
              {overview.conversion_exposure.positions_excluded_from_fx?.length > 0 && (
                <span
                  className="text-orange-400/70 text-xs"
                  title={`Positions excluded (no cost basis): SN${overview.conversion_exposure.positions_excluded_from_fx.join(', SN')}`}
                >†</span>
              )}
            </div>
            <div className="text-right">
              <div className="text-lg font-bold text-white">
                {formatUsd(overview.conversion_exposure.total_pnl_usd)}
              </div>
              <div className="text-xs text-[#8a8f98] tabular-nums">
                {safeFloat(overview.conversion_exposure.total_pnl_pct) >= 0 ? '+' : ''}
                {safeFloat(overview.conversion_exposure.total_pnl_pct).toFixed(1)}%
              </div>
            </div>
          </div>

          <div className="mt-2.5 pt-2.5 border-t border-[#2a2f38] flex justify-between">
            <div>
              <div className="text-xs text-[#8a8f98]">α/τ Effect</div>
              <div className={`tabular-nums text-sm ${pnlColor(safeFloat(overview.conversion_exposure.alpha_tao_effect_usd))}`}>
                {formatUsd(overview.conversion_exposure.alpha_tao_effect_usd)}
              </div>
            </div>
            <div>
              <div className="text-xs text-[#8a8f98]">τ/$ Effect</div>
              <div className={`tabular-nums text-sm ${pnlColor(safeFloat(overview.conversion_exposure.tao_usd_effect))}`}>
                {formatUsd(overview.conversion_exposure.tao_usd_effect)}
              </div>
            </div>
          </div>
        </div>
      </div>
    </div>
  )
}
