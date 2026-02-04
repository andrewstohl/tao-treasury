import { useState } from 'react'
import { useQuery } from '@tanstack/react-query'
import {
  TrendingUp,
  TrendingDown,
  Coins,
  BarChart3,
  Receipt,
} from 'lucide-react'
import { api } from '../../services/api'
import type { Attribution, WaterfallStep } from '../../types'
import { formatTao, formatPercent, safeFloat } from '../../utils/format'

const PERIOD_OPTIONS = [
  { days: 1, label: '24h' },
  { days: 7, label: '7d' },
  { days: 30, label: '30d' },
]

export default function PerformanceAttribution() {
  const [days, setDays] = useState(7)

  const { data: attr, isLoading } = useQuery<Attribution>({
    queryKey: ['attribution', days],
    queryFn: () => api.getAttribution(days),
    refetchInterval: 60000,
  })

  if (isLoading) {
    return (
      <div className="bg-gray-800 rounded-lg border border-gray-700 p-6 animate-pulse h-64" />
    )
  }

  if (!attr) {
    return (
      <div className="bg-gray-800 rounded-lg border border-gray-700 p-6">
        <div className="text-sm text-gray-500 text-center py-8">
          Performance attribution data unavailable.
        </div>
      </div>
    )
  }

  const totalReturn = safeFloat(attr.total_return_tao)
  const totalPct = safeFloat(attr.total_return_pct)

  return (
    <div className="space-y-4">
      {/* Section header with period selector */}
      <div className="flex items-center justify-between">
        <h3 className="text-lg font-semibold flex items-center gap-2">
          <BarChart3 className="w-5 h-5" />
          Performance Attribution
        </h3>
        <div className="flex gap-1">
          {PERIOD_OPTIONS.map((opt) => (
            <button
              key={opt.days}
              onClick={() => setDays(opt.days)}
              className={`px-3 py-1 rounded text-xs font-medium transition-colors ${
                days === opt.days
                  ? 'bg-gray-600 text-white'
                  : 'text-gray-500 hover:text-gray-300'
              }`}
            >
              {opt.label}
            </button>
          ))}
        </div>
      </div>

      <div className="grid grid-cols-1 md:grid-cols-3 gap-4">
        {/* Waterfall breakdown */}
        <div className="md:col-span-2 bg-gray-800 rounded-lg border border-gray-700 p-6">
          <div className="flex items-center justify-between mb-4">
            <div className="text-sm text-gray-400">Return Decomposition</div>
            <div className={`text-lg font-bold font-mono ${totalReturn >= 0 ? 'text-green-400' : 'text-red-400'}`}>
              {totalReturn >= 0 ? '+' : ''}{formatTao(attr.total_return_tao)} τ
              <span className="text-sm ml-1">({formatPercent(totalPct)})</span>
            </div>
          </div>

          {/* Waterfall bars */}
          <WaterfallChart steps={attr.waterfall} />

          {/* Component summary row */}
          <div className="mt-4 grid grid-cols-3 gap-4 text-center border-t border-gray-700 pt-4">
            <AttributionPill
              label="Yield Income"
              tao={attr.yield_income_tao}
              pct={attr.yield_income_pct}
              icon={<Coins className="w-3.5 h-3.5" />}
              positive
            />
            <AttributionPill
              label="Price Effect"
              tao={attr.price_effect_tao}
              pct={attr.price_effect_pct}
              icon={
                safeFloat(attr.price_effect_tao) >= 0 ? (
                  <TrendingUp className="w-3.5 h-3.5" />
                ) : (
                  <TrendingDown className="w-3.5 h-3.5" />
                )
              }
            />
            <AttributionPill
              label="Fees & Costs"
              tao={attr.fees_tao}
              pct={attr.fees_pct}
              icon={<Receipt className="w-3.5 h-3.5" />}
              negative
            />
          </div>
        </div>

        {/* Income statement */}
        <div className="bg-gray-800 rounded-lg border border-gray-700 p-6">
          <div className="text-sm text-gray-400 mb-4">Income Statement</div>
          <IncomeStatementCard
            yieldTao={attr.income_statement.yield_income_tao}
            realizedTao={attr.income_statement.realized_gains_tao}
            feesTao={attr.income_statement.fees_tao}
            netIncomeTao={attr.income_statement.net_income_tao}
            periodLabel={PERIOD_OPTIONS.find((o) => o.days === days)?.label || `${days}d`}
          />
        </div>
      </div>

    </div>
  )
}

// ---------------------------------------------------------------------------
// Sub-components
// ---------------------------------------------------------------------------

function WaterfallChart({ steps }: { steps: WaterfallStep[] }) {
  // Find the max absolute value for scaling
  const maxVal = Math.max(
    ...steps.map((s) => Math.abs(safeFloat(s.value_tao))),
    1
  )

  return (
    <div className="space-y-2">
      {steps.map((step, idx) => {
        const val = safeFloat(step.value_tao)
        const barWidth = Math.min(Math.abs(val) / maxVal * 100, 100)
        const isPositive = val >= 0

        if (step.is_total) {
          // Total bars: full-width neutral color
          return (
            <div key={idx} className="flex items-center gap-3">
              <div className="w-24 text-xs text-gray-400 text-right flex-shrink-0">
                {step.label}
              </div>
              <div className="flex-1 relative h-7">
                <div
                  className="absolute inset-y-0 left-0 bg-gray-600 rounded"
                  style={{ width: `${barWidth}%` }}
                />
                <span className="absolute inset-y-0 flex items-center px-2 text-xs font-mono text-white z-10">
                  {formatTao(step.value_tao)} τ
                </span>
              </div>
            </div>
          )
        }

        // Component bars: colored by sign
        return (
          <div key={idx} className="flex items-center gap-3">
            <div className="w-24 text-xs text-gray-400 text-right flex-shrink-0">
              {step.label}
            </div>
            <div className="flex-1 relative h-7">
              <div
                className={`absolute inset-y-0 left-0 rounded ${
                  isPositive ? 'bg-green-600/40' : 'bg-red-600/40'
                }`}
                style={{ width: `${barWidth}%` }}
              />
              <span
                className={`absolute inset-y-0 flex items-center px-2 text-xs font-mono z-10 ${
                  isPositive ? 'text-green-400' : 'text-red-400'
                }`}
              >
                {isPositive ? '+' : ''}{formatTao(step.value_tao)} τ
              </span>
            </div>
          </div>
        )
      })}
    </div>
  )
}

function AttributionPill({
  label,
  tao,
  pct,
  icon,
  positive,
  negative,
}: {
  label: string
  tao: string
  pct: string
  icon: React.ReactNode
  positive?: boolean
  negative?: boolean
}) {
  const val = safeFloat(tao)
  const color = negative
    ? 'text-red-400'
    : positive
      ? 'text-green-400'
      : val >= 0
        ? 'text-green-400'
        : 'text-red-400'

  return (
    <div>
      <div className="flex items-center justify-center gap-1 text-xs text-gray-500 mb-1">
        {icon}
        {label}
      </div>
      <div className={`font-mono text-sm font-semibold ${color}`}>
        {negative ? '-' : val >= 0 ? '+' : ''}
        {formatTao(negative ? tao : Math.abs(val).toString())} τ
      </div>
      <div className={`text-xs font-mono ${color}`}>
        {formatPercent(pct)}
      </div>
    </div>
  )
}

function IncomeStatementCard({
  yieldTao,
  realizedTao,
  feesTao,
  netIncomeTao,
  periodLabel,
}: {
  yieldTao: string
  realizedTao: string
  feesTao: string
  netIncomeTao: string
  periodLabel: string
}) {
  const netVal = safeFloat(netIncomeTao)

  return (
    <div className="space-y-3">
      <div className="text-xs text-gray-500 uppercase tracking-wider">
        {periodLabel} Period
      </div>

      <IncomeRow label="Yield Income" value={yieldTao} positive />
      <IncomeRow label="Realized Gains" value={realizedTao} />
      <div className="border-t border-gray-700 my-2" />
      <IncomeRow label="Gross Income" value={formatTao(safeFloat(yieldTao) + safeFloat(realizedTao))} />
      <IncomeRow label="Fees & Costs" value={`-${feesTao}`} negative />
      <div className="border-t border-gray-700 my-2" />
      <div className="flex justify-between items-center font-semibold">
        <span className="text-gray-300">Net Income</span>
        <span className={`font-mono ${netVal >= 0 ? 'text-green-400' : 'text-red-400'}`}>
          {netVal >= 0 ? '+' : ''}{formatTao(netIncomeTao)} τ
        </span>
      </div>
    </div>
  )
}

function IncomeRow({
  label,
  value,
  positive,
  negative,
}: {
  label: string
  value: string
  positive?: boolean
  negative?: boolean
}) {
  const num = safeFloat(value)
  const color = negative
    ? 'text-red-400'
    : positive
      ? 'text-green-400'
      : num >= 0
        ? 'text-gray-300'
        : 'text-red-400'

  return (
    <div className="flex justify-between text-sm">
      <span className="text-gray-500">{label}</span>
      <span className={`font-mono ${color}`}>
        {positive && num >= 0 ? '+' : ''}
        {formatTao(value)} τ
      </span>
    </div>
  )
}

