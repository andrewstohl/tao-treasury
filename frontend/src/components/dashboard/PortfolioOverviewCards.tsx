import { useState } from 'react'
import { useQuery } from '@tanstack/react-query'
import {
  ArrowUpDown,
  DollarSign,
  Coins,
  TrendingUp,
  TrendingDown,
  BarChart3,
  Zap,
} from 'lucide-react'
import { api } from '../../services/api'
import { useCurrency } from '../../contexts/CurrencyContext'
import type { PortfolioOverview, DualCurrencyValue } from '../../types'
import { formatTao, formatUsd, formatPercent, formatApy, safeFloat } from '../../utils/format'

function DualValue({
  value,
  primaryCurrency,
  signColored = false,
  prefix = '',
}: {
  value: DualCurrencyValue
  primaryCurrency: 'tao' | 'usd'
  signColored?: boolean
  prefix?: string
}) {
  const primary = primaryCurrency === 'tao' ? value.tao : value.usd
  const secondary = primaryCurrency === 'tao' ? value.usd : value.tao
  const primaryNum = parseFloat(primary)
  const colorClass = signColored
    ? primaryNum >= 0
      ? 'text-green-400'
      : 'text-red-400'
    : 'text-white'

  const formatPrimary = primaryCurrency === 'tao' ? formatTao : formatUsd
  const formatSecondary = primaryCurrency === 'tao' ? formatUsd : formatTao
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

/** Ledger row for P&L card */
function LedgerRow({
  label,
  value,
  isBold = false,
  isNeutral = false,
  currency,
}: {
  label: string
  value: number
  isBold?: boolean
  isNeutral?: boolean
  currency: 'tao' | 'usd'
}) {
  const formatted = currency === 'tao'
    ? `${formatTao(value)} τ`
    : formatUsd(value)
  const sign = value > 0 ? '+' : ''
  const colorClass = isNeutral
    ? 'text-white'
    : value > 0
      ? 'text-green-400'
      : value < 0
        ? 'text-red-400'
        : 'text-gray-400'

  return (
    <div className={`flex items-center justify-between text-xs ${isBold ? 'font-semibold' : ''}`}>
      <span className="text-gray-500">{label}</span>
      <span className={`font-mono ${colorClass}`}>
        {isNeutral ? '' : sign}{formatted}
      </span>
    </div>
  )
}

const RETURN_PERIODS = [
  { key: '1d', label: '24h' },
  { key: '7d', label: '7d' },
  { key: '30d', label: '30d' },
]

export default function PortfolioOverviewCards() {
  const { currency, toggleCurrency } = useCurrency()
  const [returnPeriod, setReturnPeriod] = useState('7d')

  const { data: overview, isLoading } = useQuery<PortfolioOverview>({
    queryKey: ['portfolio-overview'],
    queryFn: api.getPortfolioOverview,
    refetchInterval: 30000,
  })

  if (isLoading || !overview) {
    return (
      <div className="grid grid-cols-1 md:grid-cols-4 gap-4">
        {[...Array(4)].map((_, i) => (
          <div
            key={i}
            className="bg-gray-800 rounded-lg p-6 border border-gray-700 animate-pulse h-48"
          />
        ))}
      </div>
    )
  }

  const taoPrice = safeFloat(overview.tao_price.price_usd)
  const taoChange24h = overview.tao_price.change_24h_pct
    ? safeFloat(overview.tao_price.change_24h_pct)
    : null

  // Core values
  const navMidTao = safeFloat(overview.nav_mid.tao)
  const navMidUsd = safeFloat(overview.nav_mid.usd)
  const costBasisTao = safeFloat(overview.pnl.cost_basis.tao)
  const costBasisUsd = safeFloat(overview.pnl.cost_basis.usd)
  const unrealizedTao = safeFloat(overview.pnl.unrealized.tao)
  const unrealizedUsd = safeFloat(overview.pnl.unrealized.usd)
  const realizedTao = safeFloat(overview.pnl.realized.tao)
  const realizedUsd = safeFloat(overview.pnl.realized.usd)
  const totalPnlPct = safeFloat(overview.pnl.total_pnl_pct)
  const apyNum = safeFloat(overview.yield_income.portfolio_apy)

  // Yield/Alpha decomposition of unrealized P&L
  const yieldGainTao = safeFloat(overview.yield_income.cumulative_tao)
  const yieldGainUsd = yieldGainTao * taoPrice
  const alphaPnlTao = unrealizedTao - yieldGainTao
  const alphaPnlUsd = unrealizedUsd - yieldGainUsd

  // Rolling return for selected period
  const periodReturn = overview.returns_mid.find(r => r.period === returnPeriod)
  const periodReturnTao = safeFloat(periodReturn?.return_tao)
  const periodReturnPct = safeFloat(periodReturn?.return_pct)

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
          <DualValue value={overview.nav_mid} primaryCurrency={currency} />

          <div className="mt-3 pt-3 border-t border-gray-700 space-y-1.5">
            <LedgerRow
              label="Cost Basis"
              value={currency === 'tao' ? costBasisTao : costBasisUsd}
              currency={currency}
              isNeutral
            />
            <LedgerRow
              label="Realized P&L"
              value={currency === 'tao' ? realizedTao : realizedUsd}
              currency={currency}
            />
            <LedgerRow
              label="Yield Gain"
              value={currency === 'tao' ? yieldGainTao : yieldGainUsd}
              currency={currency}
            />
            <LedgerRow
              label="Alpha P&L"
              value={currency === 'tao' ? alphaPnlTao : alphaPnlUsd}
              currency={currency}
            />
          </div>

          <div className="mt-2 flex items-center justify-between text-xs text-gray-500">
            <span>Exec NAV</span>
            <span className="font-mono">
              {currency === 'tao'
                ? `${formatTao(overview.nav_exec.tao)} τ`
                : formatUsd(overview.nav_exec.usd)}
            </span>
          </div>
        </div>

        {/* Card 2: Yield & Emissions */}
        <div className="bg-gray-800 rounded-lg p-6 border border-gray-700">
          <div className="flex items-center gap-2 text-sm text-gray-400 mb-2">
            <Coins className="w-4 h-4" />
            <span>Yield</span>
          </div>

          <div className="text-2xl font-bold text-green-400">
            {formatApy(apyNum)}
          </div>
          <div className="text-sm text-gray-500 mt-0.5 font-mono">
            +{formatTao(overview.yield_income.daily.tao)} τ/day
          </div>

          <div className="mt-3 pt-3 border-t border-gray-700 space-y-1.5">
            <div className="text-xs text-gray-500 mb-1">Projected yield</div>
            {[
              { label: '7d', value: safeFloat(overview.yield_income.weekly.tao) },
              { label: '30d', value: safeFloat(overview.yield_income.monthly.tao) },
              { label: '1yr', value: safeFloat(overview.yield_income.annualized.tao) },
            ].map(({ label, value }) => (
              <div key={label} className="flex items-center justify-between text-xs">
                <span className="text-gray-500">{label}</span>
                <span className="font-mono text-green-400">
                  +{formatTao(value)} τ
                </span>
              </div>
            ))}
          </div>

          <div className="mt-2 flex items-center justify-between text-xs text-gray-500">
            <div className="flex items-center gap-1">
              <Zap className="w-3 h-3" />
              <span>12m compounded</span>
            </div>
            <span className="font-mono text-green-400">
              +{formatTao(overview.compounding.compounded_365d_tao)} τ
            </span>
          </div>
        </div>

        {/* Card 3: Returns (period-selectable rolling returns from NAV history) */}
        <div className="bg-gray-800 rounded-lg p-6 border border-gray-700">
          <div className="flex items-center justify-between mb-2">
            <div className="flex items-center gap-2 text-sm text-gray-400">
              {periodReturnTao >= 0 ? (
                <TrendingUp className="w-4 h-4 text-green-400" />
              ) : (
                <TrendingDown className="w-4 h-4 text-red-400" />
              )}
              <span>Returns</span>
            </div>
            <div className="flex gap-0.5">
              {RETURN_PERIODS.map(({ key, label }) => (
                <button
                  key={key}
                  onClick={() => setReturnPeriod(key)}
                  className={`px-1.5 py-0.5 rounded text-xs font-medium transition-colors ${
                    returnPeriod === key
                      ? 'bg-gray-600 text-white'
                      : 'text-gray-500 hover:text-gray-300'
                  }`}
                >
                  {label}
                </button>
              ))}
            </div>
          </div>

          <span
            className={`font-mono text-2xl font-bold ${
              periodReturnPct >= 0 ? 'text-green-400' : 'text-red-400'
            }`}
          >
            {formatPercent(periodReturnPct)}
          </span>
          <div className="text-sm text-gray-500 mt-0.5 font-mono">
            {periodReturnTao >= 0 ? '+' : ''}{formatTao(periodReturnTao)} τ
          </div>

          <div className="mt-3 pt-3 border-t border-gray-700 space-y-1.5">
            {overview.returns_mid
              .filter(r => r.period !== returnPeriod && r.period !== 'inception')
              .map((r) => (
                <div key={r.period} className="flex items-center justify-between text-xs">
                  <span className="text-gray-500">{r.period}</span>
                  <span className={`font-mono ${safeFloat(r.return_pct) >= 0 ? 'text-green-400' : 'text-red-400'}`}>
                    {formatPercent(r.return_pct ?? 0)}
                  </span>
                </div>
              ))}
            {(() => {
              const inception = overview.returns_mid.find(r => r.period === 'inception')
              if (!inception) return null
              return (
                <div className="flex items-center justify-between text-xs border-t border-gray-700 pt-1">
                  <span className="text-gray-500">Inception</span>
                  <span className={`font-mono font-semibold ${safeFloat(inception.return_pct) >= 0 ? 'text-green-400' : 'text-red-400'}`}>
                    {formatPercent(inception.return_pct ?? 0)}
                  </span>
                </div>
              )
            })()}
          </div>
        </div>

        {/* Card 4: P&L Summary */}
        <div className="bg-gray-800 rounded-lg p-6 border border-gray-700">
          <div className="flex items-center justify-between mb-2">
            <div className="flex items-center gap-2 text-sm text-gray-400">
              <BarChart3 className="w-4 h-4" />
              <span>P&L</span>
            </div>
            <span
              className={`font-mono text-xs font-semibold ${
                totalPnlPct >= 0 ? 'text-green-400' : 'text-red-400'
              }`}
            >
              {formatPercent(totalPnlPct)}
            </span>
          </div>

          <DualValue
            value={overview.pnl.total}
            primaryCurrency={currency}
            signColored
            prefix={safeFloat(overview.pnl.total.tao) >= 0 ? '+' : ''}
          />

          <div className="mt-3 pt-3 border-t border-gray-700 space-y-1.5">
            <LedgerRow
              label="Cost Basis"
              value={currency === 'tao' ? costBasisTao : costBasisUsd}
              currency={currency}
              isNeutral
            />
            <LedgerRow
              label="Unrealized"
              value={currency === 'tao' ? unrealizedTao : unrealizedUsd}
              currency={currency}
            />
            <LedgerRow
              label="Realized"
              value={currency === 'tao' ? realizedTao : realizedUsd}
              currency={currency}
            />
            <div className="border-t border-gray-700 pt-1">
              <LedgerRow
                label="Current Value"
                value={currency === 'tao' ? navMidTao : navMidUsd}
                currency={currency}
                isBold
                isNeutral
              />
            </div>
          </div>
        </div>
      </div>
    </div>
  )
}
