import { useQuery } from '@tanstack/react-query'
import {
  ArrowUpDown,
  DollarSign,
  Coins,
  TrendingUp,
  TrendingDown,
  Zap,
} from 'lucide-react'
import { api } from '../../services/api'
import { useCurrency } from '../../contexts/CurrencyContext'
import type { PortfolioOverview, DualCurrencyValue } from '../../types'
import { formatTao, formatTaoShort, formatUsd, formatPercent, formatApy, safeFloat } from '../../utils/format'

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
      <div className={`text-2xl font-bold ${colorClass}`}>
        {prefix}{formatPrimary(primary)}{primarySuffix}
      </div>
      <div className="text-sm text-gray-500 mt-0.5">
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
      <div className="space-y-4">
        <div className="grid grid-cols-1 md:grid-cols-4 gap-4">
          {[...Array(4)].map((_, i) => (
            <div
              key={i}
              className="bg-gray-800 rounded-lg p-6 border border-gray-700 animate-pulse h-48"
            />
          ))}
        </div>
      </div>
    )
  }

  const taoPrice = safeFloat(overview.tao_price.price_usd)
  const taoChange24h = overview.tao_price.change_24h_pct
    ? safeFloat(overview.tao_price.change_24h_pct)
    : null

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

  return (
    <div className="space-y-4">
      {/* TAO Price Strip + Currency Toggle */}
      <div className="flex items-center justify-between">
        <div className="flex items-center gap-4 text-sm">
          <div className="flex items-center gap-2 text-gray-400">
            <DollarSign className="w-4 h-4" />
            <span>TAO</span>
            <span className="font-mono text-white font-semibold">
              {formatUsd(taoPrice)}
            </span>
            {taoChange24h != null && (
              <span
                className={`font-mono text-xs ${
                  taoChange24h >= 0 ? 'text-green-400' : 'text-red-400'
                }`}
              >
                {formatPercent(taoChange24h)}
              </span>
            )}
          </div>
          {overview.tao_price.change_7d_pct && (
            <span className="text-gray-600">
              7d:{' '}
              <span
                className={`font-mono text-xs ${
                  parseFloat(overview.tao_price.change_7d_pct) >= 0
                    ? 'text-green-400'
                    : 'text-red-400'
                }`}
              >
                {formatPercent(overview.tao_price.change_7d_pct)}
              </span>
            </span>
          )}
        </div>

        <button
          onClick={toggleCurrency}
          className="flex items-center gap-1.5 px-3 py-1.5 rounded-lg bg-gray-700 hover:bg-gray-600 text-sm text-gray-300 transition-colors"
        >
          <ArrowUpDown className="w-3.5 h-3.5" />
          {currency === 'tao' ? 'τ TAO' : '$ USD'}
        </button>
      </div>

      {/* Cards Grid */}
      <div className="grid grid-cols-1 md:grid-cols-4 gap-4">
        {/* Card 1: Portfolio Value */}
        <div className="bg-gray-800 rounded-lg p-6 border border-gray-700">
          <div className="text-sm text-gray-400 mb-2">Portfolio Value</div>
          <DualValue value={overview.nav_mid} primaryCurrency={currency} short />

          <div className="mt-3 pt-3 border-t border-gray-700">
            <div className="grid grid-cols-2 gap-2">
              <div className="text-left">
                <div className="text-sm text-gray-500 mb-1">Realized</div>
                <div className={`font-mono text-sm ${realizedTao >= 0 ? 'text-green-400' : 'text-red-400'}`}>
                  {currency === 'tao' ? `${formatTaoShort(realizedTao)}τ` : formatUsd(realizedUsd)}
                </div>
              </div>
              <div className="text-right">
                <div className="text-sm text-gray-500 mb-1">Unrealized</div>
                <div className={`font-mono text-sm ${unrealizedTao >= 0 ? 'text-green-400' : 'text-red-400'}`}>
                  {currency === 'tao' ? `${formatTaoShort(unrealizedTao)}τ` : formatUsd(unrealizedUsd)}
                </div>
              </div>
            </div>
          </div>
        </div>

        {/* Card 2: Yield */}
        <div className="bg-gray-800 rounded-lg p-6 border border-gray-700">
          <div className="flex items-center gap-2 text-sm text-gray-400 mb-2">
            <Coins className="w-4 h-4" />
            <span>Yield</span>
          </div>

          <DualValue value={overview.yield_income.total_yield} primaryCurrency={currency} short />

          <div className="mt-3 pt-3 border-t border-gray-700">
            <div className="grid grid-cols-2 gap-2">
              <div className="text-left">
                <div className="text-sm text-gray-500 mb-1">Realized</div>
                <div className={`font-mono text-sm ${safeFloat(overview.yield_income.realized_yield.tao) >= 0 ? 'text-green-400' : 'text-red-400'}`}>
                  {currency === 'tao'
                    ? `${formatTaoShort(overview.yield_income.realized_yield.tao)}τ`
                    : formatUsd(overview.yield_income.realized_yield.usd)}
                </div>
              </div>
              <div className="text-right">
                <div className="text-sm text-gray-500 mb-1">Unrealized</div>
                <div className={`font-mono text-sm ${safeFloat(overview.yield_income.unrealized_yield.tao) >= 0 ? 'text-green-400' : 'text-red-400'}`}>
                  {currency === 'tao'
                    ? `${formatTaoShort(overview.yield_income.unrealized_yield.tao)}τ`
                    : formatUsd(overview.yield_income.unrealized_yield.usd)}
                </div>
              </div>
            </div>
          </div>
        </div>

        {/* Card 3: Alpha */}
        <div className="bg-gray-800 rounded-lg p-6 border border-gray-700">
          <div className="flex items-center gap-2 text-sm text-gray-400 mb-2">
            {totalAlphaTao >= 0 ? (
              <TrendingUp className="w-4 h-4 text-green-400" />
            ) : (
              <TrendingDown className="w-4 h-4 text-red-400" />
            )}
            <span>Alpha</span>
          </div>

          <DualValue
            value={{ tao: String(totalAlphaTao), usd: String(totalAlphaUsd) }}
            primaryCurrency={currency}
            short
          />

          <div className="mt-3 pt-3 border-t border-gray-700">
            <div className="grid grid-cols-2 gap-2">
              <div className="text-left">
                <div className="text-sm text-gray-500 mb-1">Realized</div>
                <div className={`font-mono text-sm ${realizedAlphaTao >= 0 ? 'text-green-400' : 'text-red-400'}`}>
                  {currency === 'tao' ? `${formatTaoShort(realizedAlphaTao)}τ` : formatUsd(realizedAlphaUsd)}
                </div>
              </div>
              <div className="text-right">
                <div className="text-sm text-gray-500 mb-1">Unrealized</div>
                <div className={`font-mono text-sm ${unrealizedAlphaTao >= 0 ? 'text-green-400' : 'text-red-400'}`}>
                  {currency === 'tao' ? `${formatTaoShort(unrealizedAlphaTao)}τ` : formatUsd(unrealizedAlphaUsd)}
                </div>
              </div>
            </div>
          </div>
        </div>

        {/* Card 4: APY */}
        <div className="bg-gray-800 rounded-lg p-6 border border-gray-700">
          <div className="flex items-center gap-2 text-sm text-gray-400 mb-2">
            <Zap className="w-4 h-4" />
            <span>APY</span>
          </div>

          <div className="text-2xl font-bold text-white">
            {formatApy(apyNum)}
          </div>
          <div className="text-sm text-gray-500 mt-0.5 font-mono">
            {formatTaoShort(overview.yield_income.daily.tao)}τ/day
          </div>

          <div className="mt-3 pt-3 border-t border-gray-700">
            <div className="grid grid-cols-2 gap-2">
              <div className="text-left">
                <div className="text-sm text-gray-500 mb-1">7D Proj.</div>
                <div className="font-mono text-sm text-green-400">
                  {formatTaoShort(overview.yield_income.weekly.tao)}τ
                </div>
              </div>
              <div className="text-right">
                <div className="text-sm text-gray-500 mb-1">30D Proj.</div>
                <div className="font-mono text-sm text-green-400">
                  {formatTaoShort(overview.yield_income.monthly.tao)}τ
                </div>
              </div>
            </div>
          </div>
        </div>
      </div>
    </div>
  )
}
