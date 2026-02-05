import { useState } from 'react'
import { useQuery } from '@tanstack/react-query'
import {
  Zap,
  TrendingDown,
  TrendingUp,
  Shield,
  ChevronDown,
  ChevronUp,
} from 'lucide-react'
import { api } from '../../services/api'
import type { ScenarioAnalysis, SensitivityPoint, StressScenario } from '../../types'
import { formatTao, formatUsd, formatPercent, safeFloat } from '../../utils/format'

export default function PriceSensitivity() {
  const [expandedScenario, setExpandedScenario] = useState<string | null>(null)

  const { data: scenario, isLoading } = useQuery<ScenarioAnalysis>({
    queryKey: ['scenarios'],
    queryFn: () => api.getScenarios(),
    refetchInterval: 120000,
  })

  if (isLoading) {
    return (
      <div className="bg-gray-800 rounded-lg border border-gray-700 p-6 animate-pulse h-64" />
    )
  }

  if (!scenario) {
    return (
      <div className="bg-gray-800 rounded-lg border border-gray-700 p-6">
        <div className="text-sm text-gray-500 text-center py-8">
          Scenario analysis data unavailable.
        </div>
      </div>
    )
  }

  return (
    <div className="space-y-4">
      {/* Section header */}
      <h3 className="text-lg font-semibold flex items-center gap-2">
        <Zap className="w-5 h-5" />
        TAO Price Sensitivity &amp; Scenarios
      </h3>

      <div className="grid grid-cols-1 lg:grid-cols-3 gap-4">
        {/* Sensitivity Table */}
        <div className="lg:col-span-2 bg-gray-800 rounded-lg border border-gray-700 overflow-hidden">
          <div className="px-6 py-4 border-b border-gray-700 flex items-center justify-between">
            <div className="text-sm text-gray-400">Price Sensitivity Table</div>
            <div className="text-sm text-gray-500">
              TAO: {formatUsd(scenario.current_tao_price_usd)}
            </div>
          </div>

          <div className="overflow-x-auto">
            <table className="w-full">
              <thead className="bg-gray-900/50">
                <tr className="text-xs text-gray-500 uppercase tracking-wider">
                  <th className="px-4 py-2 text-left">Shock</th>
                  <th className="px-4 py-2 text-right">TAO Price</th>
                  <th className="px-4 py-2 text-right">NAV (TAO)</th>
                  <th className="px-4 py-2 text-right">NAV (USD)</th>
                  <th className="px-4 py-2 text-right">USD Change</th>
                  <th className="px-4 py-2 text-right">% Change</th>
                </tr>
              </thead>
              <tbody className="divide-y divide-gray-700">
                {scenario.sensitivity.map((pt) => (
                  <SensitivityRow key={pt.shock_pct} point={pt} />
                ))}
              </tbody>
            </table>
          </div>
        </div>

        {/* Risk Exposure Card */}
        <div className="bg-gray-800 rounded-lg border border-gray-700 p-6">
          <div className="text-sm text-gray-400 mb-4 flex items-center gap-2">
            <Shield className="w-4 h-4" />
            Risk Exposure
          </div>
          <RiskExposureCard scenario={scenario} />
        </div>
      </div>

      {/* Stress Scenarios */}
      {scenario.scenarios.length > 0 && (
        <div className="bg-gray-800 rounded-lg border border-gray-700 overflow-hidden">
          <div className="px-6 py-4 border-b border-gray-700 flex items-center justify-between">
            <div className="text-sm text-gray-400">Stress Scenarios</div>
            <div className="text-xs text-gray-500">
              {scenario.scenarios.length} scenarios
            </div>
          </div>
          <div className="divide-y divide-gray-700">
            {scenario.scenarios.map((sc) => (
              <ScenarioCard
                key={sc.id}
                scenario={sc}
                isExpanded={expandedScenario === sc.id}
                onToggle={() =>
                  setExpandedScenario(expandedScenario === sc.id ? null : sc.id)
                }
              />
            ))}
          </div>
        </div>
      )}
    </div>
  )
}

// ---------------------------------------------------------------------------
// Sub-components
// ---------------------------------------------------------------------------

function SensitivityRow({
  point,
}: {
  point: SensitivityPoint
}) {
  const shock = point.shock_pct
  const usdChange = safeFloat(point.usd_change)
  const isBase = shock === 0
  const isPositive = shock > 0

  // Background highlight for base row
  const rowClass = isBase
    ? 'bg-gray-700/30 font-semibold'
    : 'hover:bg-gray-700/20'

  // Color for shock column
  const shockColor = isBase
    ? 'text-gray-300'
    : isPositive
      ? 'text-green-400'
      : 'text-red-400'

  return (
    <tr className={rowClass}>
      <td className={`px-4 py-2.5 tabular-nums text-sm ${shockColor}`}>
        {isBase ? 'Current' : `${shock > 0 ? '+' : ''}${shock}%`}
      </td>
      <td className="px-4 py-2.5 text-right tabular-nums text-sm text-gray-300">
        {formatUsd(point.tao_price_usd)}
      </td>
      <td className="px-4 py-2.5 text-right tabular-nums text-sm text-gray-400">
        {formatTao(point.nav_tao)} τ
      </td>
      <td className="px-4 py-2.5 text-right tabular-nums text-sm text-gray-300">
        {formatUsd(point.nav_usd)}
      </td>
      <td className="px-4 py-2.5 text-right">
        {isBase ? (
          <span className="text-gray-600 text-sm">--</span>
        ) : (
          <span
            className={`tabular-nums text-sm ${
              usdChange >= 0 ? 'text-green-400' : 'text-red-400'
            }`}
          >
            {usdChange >= 0 ? '+' : ''}
            {formatUsd(point.usd_change)}
          </span>
        )}
      </td>
      <td className="px-4 py-2.5 text-right">
        {isBase ? (
          <span className="text-gray-600 text-sm">--</span>
        ) : (
          <span
            className={`tabular-nums text-sm ${
              usdChange >= 0 ? 'text-green-400' : 'text-red-400'
            }`}
          >
            {formatPercent(point.usd_change_pct)}
          </span>
        )}
      </td>
    </tr>
  )
}

function ScenarioCard({
  scenario,
  isExpanded,
  onToggle,
}: {
  scenario: StressScenario
  isExpanded: boolean
  onToggle: () => void
}) {
  const usdImpact = safeFloat(scenario.usd_impact)
  const taoImpact = safeFloat(scenario.tao_impact)
  const isNegative = usdImpact < 0

  // Icon based on scenario type
  const Icon = isNegative ? TrendingDown : TrendingUp
  const iconColor = isNegative ? 'text-red-400' : 'text-green-400'
  const impactBg = isNegative ? 'bg-red-600/10' : 'bg-green-600/10'

  return (
    <div>
      <button
        onClick={onToggle}
        className="w-full px-6 py-4 flex items-center justify-between hover:bg-gray-700/20 transition-colors"
      >
        <div className="flex items-center gap-3">
          <Icon className={`w-5 h-5 flex-shrink-0 ${iconColor}`} />
          <div className="text-left">
            <div className="font-medium text-sm">{scenario.name}</div>
            <div className="text-xs text-gray-500 flex gap-3 mt-0.5">
              <span>TAO: {scenario.tao_price_change_pct > 0 ? '+' : ''}{scenario.tao_price_change_pct}%</span>
              {scenario.alpha_impact_pct !== 0 && (
                <span>Alpha: {scenario.alpha_impact_pct > 0 ? '+' : ''}{scenario.alpha_impact_pct}%</span>
              )}
            </div>
          </div>
        </div>

        <div className="flex items-center gap-4">
          {/* Impact badge */}
          <div className={`px-3 py-1 rounded ${impactBg}`}>
            <span className={`tabular-nums text-sm font-semibold ${isNegative ? 'text-red-400' : 'text-green-400'}`}>
              {usdImpact >= 0 ? '+' : ''}{formatUsd(scenario.usd_impact)}
            </span>
            <span className={`text-xs ml-1 ${isNegative ? 'text-red-400/70' : 'text-green-400/70'}`}>
              ({formatPercent(scenario.usd_impact_pct)})
            </span>
          </div>
          {isExpanded ? (
            <ChevronUp className="w-4 h-4 text-gray-500" />
          ) : (
            <ChevronDown className="w-4 h-4 text-gray-500" />
          )}
        </div>
      </button>

      {isExpanded && (
        <div className="px-6 pb-4 pt-0">
          <div className="bg-gray-900/50 rounded-lg p-4 space-y-3">
            <p className="text-sm text-gray-400">{scenario.description}</p>

            <div className="grid grid-cols-2 md:grid-cols-4 gap-4 text-sm">
              <div>
                <div className="text-xs text-gray-500">New TAO Price</div>
                <div className="tabular-nums text-gray-300">
                  {formatUsd(scenario.new_tao_price_usd)}
                </div>
              </div>
              <div>
                <div className="text-xs text-gray-500">NAV (TAO)</div>
                <div className="tabular-nums text-gray-300">
                  {formatTao(scenario.nav_tao)} τ
                </div>
              </div>
              <div>
                <div className="text-xs text-gray-500">TAO Impact</div>
                <div className={`tabular-nums ${taoImpact >= 0 ? 'text-green-400' : 'text-red-400'}`}>
                  {taoImpact >= 0 ? '+' : ''}{formatTao(scenario.tao_impact)} τ
                </div>
              </div>
              <div>
                <div className="text-xs text-gray-500">NAV (USD)</div>
                <div className="tabular-nums text-gray-300">
                  {formatUsd(scenario.nav_usd)}
                </div>
              </div>
            </div>
          </div>
        </div>
      )}
    </div>
  )
}

function RiskExposureCard({ scenario }: { scenario: ScenarioAnalysis }) {
  const { risk_exposure: risk, allocation } = scenario
  const dtaoWeight = safeFloat(risk.dtao_weight_pct)
  const rootWeight = safeFloat(risk.root_weight_pct)
  const slippagePct = safeFloat(risk.total_exit_slippage_pct)

  return (
    <div className="space-y-4">
      {/* Allocation donut-style bars */}
      <div className="space-y-2">
        <div className="text-xs text-gray-500 uppercase tracking-wider">Allocation</div>
        <AllocationBar
          label="Root"
          tao={allocation.root_tao}
          pct={rootWeight}
          color="bg-blue-500"
        />
        <AllocationBar
          label="dTAO"
          tao={allocation.dtao_tao}
          pct={dtaoWeight}
          color="bg-tao-500"
        />
        <AllocationBar
          label="Unstaked"
          tao={allocation.unstaked_tao}
          pct={100 - rootWeight - dtaoWeight}
          color="bg-green-500"
        />
      </div>

      <div className="border-t border-gray-700 pt-3 space-y-3">
        {/* TAO Beta */}
        <div className="flex justify-between items-center">
          <span className="text-sm text-gray-400">TAO Beta</span>
          <span className="tabular-nums text-sm text-gray-300">
            {safeFloat(risk.tao_beta).toFixed(1)}x
          </span>
        </div>

        {/* Exit Slippage */}
        <div>
          <div className="flex justify-between items-center mb-1">
            <span className="text-sm text-gray-400">Exit Slippage</span>
            <span
              className={`tabular-nums text-sm ${
                slippagePct < 2
                  ? 'text-green-400'
                  : slippagePct < 5
                    ? 'text-yellow-400'
                    : 'text-red-400'
              }`}
            >
              {slippagePct.toFixed(2)}%
            </span>
          </div>
          <div className="text-xs text-gray-500">
            {formatTao(risk.total_exit_slippage_tao)} τ total slippage
          </div>
        </div>

        {/* dTAO Weight indicator */}
        <div>
          <div className="flex justify-between items-center mb-1">
            <span className="text-sm text-gray-400">Alpha Risk</span>
            <span
              className={`tabular-nums text-sm ${
                dtaoWeight < 30
                  ? 'text-green-400'
                  : dtaoWeight < 60
                    ? 'text-yellow-400'
                    : 'text-red-400'
              }`}
            >
              {dtaoWeight.toFixed(1)}%
            </span>
          </div>
          <div className="relative w-full bg-gray-700 rounded-full h-1.5">
            <div
              className="bg-tao-500 h-1.5 rounded-full transition-all"
              style={{ width: `${Math.min(dtaoWeight, 100)}%` }}
            />
          </div>
        </div>
      </div>

      {/* Note */}
      <div className="text-xs text-gray-500 leading-relaxed pt-1">
        {risk.note}
      </div>
    </div>
  )
}

function AllocationBar({
  label,
  tao,
  pct,
  color,
}: {
  label: string
  tao: string
  pct: number
  color: string
}) {
  return (
    <div>
      <div className="flex justify-between text-xs mb-0.5">
        <span className="text-gray-400">{label}</span>
        <span className="text-gray-400 tabular-nums">
          {formatTao(tao)} τ ({pct.toFixed(1)}%)
        </span>
      </div>
      <div className="relative w-full bg-gray-700 rounded-full h-1.5">
        <div
          className={`${color} h-1.5 rounded-full`}
          style={{ width: `${Math.min(Math.max(pct, 0), 100)}%` }}
        />
      </div>
    </div>
  )
}
