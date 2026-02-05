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
      <div className={`text-xl font-bold ${colorClass}`}>
        {prefix}{formatPrimary(primary)}{primarySuffix}
      </div>
      <div className="text-sm text-gray-500">
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
    refetchInterval: 30000,
  })

  if (isLoading || !overview) {
    return (
      <div className="grid grid-cols-1 md:grid-cols-4 gap-3">
        {[...Array(4)].map((_, i) => (
          <div
            key={i}
            className="bg-gray-800 rounded-lg p-4 border border-gray-700 animate-pulse h-32"
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
          className="flex items-center gap-1.5 px-2.5 py-1 rounded-md bg-gray-700 hover:bg-gray-600 text-xs text-gray-300 transition-colors"
        >
          <ArrowUpDown className="w-3 h-3" />
          {currency === 'tao' ? 'τ TAO' : '$ USD'}
        </button>
      </div>

      {/* Cards Grid */}
      <div className="grid grid-cols-1 md:grid-cols-4 gap-3">
        {/* Card 1: Portfolio Value */}
        <div className="bg-gray-800 rounded-lg p-4 border border-gray-700">
          <div className="flex items-start justify-between">
            <div className="text-xl font-bold font-display text-white">Current Value</div>
            <div className="text-right">
              <DualValue value={overview.nav_mid} primaryCurrency={currency} short />
            </div>
          </div>

          <div className="mt-2.5 pt-2.5 border-t border-gray-700 flex justify-between">
            <div>
              <div className="text-xs text-gray-500">Realized</div>
              <div className={`tabular-nums text-sm ${pnlColor(realizedTao)}`}>
                {currency === 'tao' ? `${formatTaoShort(realizedTao)}τ` : formatUsd(realizedUsd)}
              </div>
            </div>
            <div>
              <div className="text-xs text-gray-500">Unrealized</div>
              <div className={`tabular-nums text-sm ${pnlColor(unrealizedTao)}`}>
                {currency === 'tao' ? `${formatTaoShort(unrealizedTao)}τ` : formatUsd(unrealizedUsd)}
              </div>
            </div>
            <div>
              <div className="text-xs text-gray-500">Total</div>
              <div className={`tabular-nums text-sm ${pnlColor(realizedTao + unrealizedTao)}`}>
                {currency === 'tao' ? `${formatTaoShort(realizedTao + unrealizedTao)}τ` : formatUsd(realizedUsd + unrealizedUsd)}
              </div>
            </div>
          </div>
        </div>

        {/* Card 2: Yield */}
        <div className="bg-gray-800 rounded-lg p-4 border border-gray-700">
          <div className="flex items-start justify-between">
            <div className="text-xl font-bold font-display text-white">Yield</div>
            <div className="text-right">
              <DualValue value={overview.yield_income.total_yield} primaryCurrency={currency} short />
            </div>
          </div>

          <div className="mt-2.5 pt-2.5 border-t border-gray-700 flex justify-between">
            <div>
              <div className="text-xs text-gray-500">Realized</div>
              <div className={`tabular-nums text-sm ${pnlColor(safeFloat(overview.yield_income.realized_yield.tao))}`}>
                {currency === 'tao'
                  ? `${formatTaoShort(overview.yield_income.realized_yield.tao)}τ`
                  : formatUsd(overview.yield_income.realized_yield.usd)}
              </div>
            </div>
            <div>
              <div className="text-xs text-gray-500">Unrealized</div>
              <div className={`tabular-nums text-sm ${pnlColor(safeFloat(overview.yield_income.unrealized_yield.tao))}`}>
                {currency === 'tao'
                  ? `${formatTaoShort(overview.yield_income.unrealized_yield.tao)}τ`
                  : formatUsd(overview.yield_income.unrealized_yield.usd)}
              </div>
            </div>
            <div>
              <div className="text-xs text-gray-500">Total</div>
              <div className={`tabular-nums text-sm ${pnlColor(safeFloat(overview.yield_income.total_yield.tao))}`}>
                {currency === 'tao'
                  ? `${formatTaoShort(overview.yield_income.total_yield.tao)}τ`
                  : formatUsd(overview.yield_income.total_yield.usd)}
              </div>
            </div>
          </div>
        </div>

        {/* Card 3: Alpha */}
        <div className="bg-gray-800 rounded-lg p-4 border border-gray-700">
          <div className="flex items-start justify-between">
            <div className="text-xl font-bold font-display text-white">Alpha</div>
            <div className="text-right">
              <DualValue
                value={{ tao: String(totalAlphaTao), usd: String(totalAlphaUsd) }}
                primaryCurrency={currency}
                short
              />
            </div>
          </div>

          <div className="mt-2.5 pt-2.5 border-t border-gray-700 flex justify-between">
            <div>
              <div className="text-xs text-gray-500">Realized</div>
              <div className={`tabular-nums text-sm ${pnlColor(realizedAlphaTao)}`}>
                {currency === 'tao' ? `${formatTaoShort(realizedAlphaTao)}τ` : formatUsd(realizedAlphaUsd)}
              </div>
            </div>
            <div>
              <div className="text-xs text-gray-500">Unrealized</div>
              <div className={`tabular-nums text-sm ${pnlColor(unrealizedAlphaTao)}`}>
                {currency === 'tao' ? `${formatTaoShort(unrealizedAlphaTao)}τ` : formatUsd(unrealizedAlphaUsd)}
              </div>
            </div>
            <div>
              <div className="text-xs text-gray-500">Total</div>
              <div className={`tabular-nums text-sm ${pnlColor(totalAlphaTao)}`}>
                {currency === 'tao' ? `${formatTaoShort(totalAlphaTao)}τ` : formatUsd(totalAlphaUsd)}
              </div>
            </div>
          </div>
        </div>

        {/* Card 4: APY */}
        <div className="bg-gray-800 rounded-lg p-4 border border-gray-700">
          <div className="flex items-start justify-between">
            <div className="text-xl font-bold font-display text-white">APY</div>
            <div className="text-right">
              <div className="text-xl font-bold text-white">
                {formatApy(apyNum)}
              </div>
              <div className="text-sm text-gray-500 tabular-nums">
                {formatTaoShort(overview.yield_income.daily.tao)}τ/day
              </div>
            </div>
          </div>

          <div className="mt-2.5 pt-2.5 border-t border-gray-700 flex justify-between">
            <div>
              <div className="text-xs text-gray-500">7d Proj.</div>
              <div className="tabular-nums text-sm text-green-400">
                {formatTaoShort(overview.yield_income.weekly.tao)}τ
              </div>
            </div>
            <div>
              <div className="text-xs text-gray-500">30d Proj.</div>
              <div className="tabular-nums text-sm text-green-400">
                {formatTaoShort(overview.yield_income.monthly.tao)}τ
              </div>
            </div>
            <div>
              <div className="text-xs text-gray-500">365d Proj.</div>
              <div className="tabular-nums text-sm text-green-400">
                {formatTaoShort(safeFloat(overview.yield_income.daily.tao) * 365)}τ
              </div>
            </div>
          </div>
        </div>
      </div>
    </div>
  )
}
