import { AlertTriangle, CheckCircle, Info, Shield } from 'lucide-react'
import { formatCompact, formatTaoShort, getViabilityTierBgColor, formatViabilityTierLabel } from '../../../utils/format'
import type { EnrichedSubnet } from '../../../types'

interface ViabilityPanelProps {
  enriched: EnrichedSubnet | null
}

interface ViabilityFactors {
  tao_reserve_raw?: number
  tao_reserve_percentile?: number
  tao_reserve_weighted?: number
  net_flow_7d_raw?: number
  net_flow_7d_percentile?: number
  net_flow_7d_weighted?: number
  emission_share_raw?: number
  emission_share_percentile?: number
  emission_share_weighted?: number
  price_trend_7d_raw?: number
  price_trend_7d_percentile?: number
  price_trend_7d_weighted?: number
  subnet_age_raw?: number
  subnet_age_percentile?: number
  subnet_age_weighted?: number
  max_drawdown_30d_raw?: number
  max_drawdown_30d_percentile?: number
  max_drawdown_30d_weighted?: number
  // Flow momentum (FAI)
  fai_raw?: number
  fai_percentile?: number
  fai_weighted?: number
  hard_failures?: string[]
}

/**
 * Calculate Flow Acceleration Index (FAI)
 * FAI = flow_1d / (flow_7d / 7)
 */
function calculateFAI(flow1d: number, flow7d: number): number | null {
  if (flow7d === 0) return null
  const avgDaily7d = flow7d / 7
  if (avgDaily7d === 0) return null
  return flow1d / avgDaily7d
}

/**
 * Get FAI percentile estimate based on value
 * Based on our backtest research findings
 */
function getFAIPercentile(fai: number | null): number {
  if (fai === null) return 50
  // FAI distribution: Q1 < 0.5, Q5 > 1.5
  if (fai >= 1.5) return 90  // Top quintile
  if (fai >= 1.2) return 75
  if (fai >= 0.8) return 50
  if (fai >= 0.5) return 25
  return 10  // Bottom quintile
}

function FactorBar({
  label,
  raw,
  percentile,
  weighted,
  isNegative = false,
}: {
  label: string
  raw: string
  percentile?: number
  weighted?: number
  isNegative?: boolean
}) {
  const pct = percentile ?? 0
  const barColor = isNegative
    ? pct >= 70 ? 'bg-red-500' : pct >= 40 ? 'bg-yellow-500' : 'bg-green-500'
    : pct >= 70 ? 'bg-green-500' : pct >= 40 ? 'bg-yellow-500' : 'bg-red-500'

  return (
    <div className="space-y-1">
      <div className="flex justify-between text-xs">
        <span className="text-[#8a8f98]">{label}</span>
        <span className="text-[#8faabe] tabular-nums">{raw}</span>
      </div>
      <div className="flex items-center gap-2">
        <div className="flex-1 h-1.5 bg-[#0d0f12] rounded-full overflow-hidden">
          <div
            className={`h-full ${barColor} transition-all duration-300`}
            style={{ width: `${pct}%` }}
          />
        </div>
        <span className="text-xs text-[#6b7280] w-8 text-right tabular-nums">P{pct.toFixed(0)}</span>
        {weighted != null && (
          <span className="text-xs text-[#8a8f98] w-8 text-right tabular-nums">{weighted.toFixed(1)}</span>
        )}
      </div>
    </div>
  )
}

export default function ViabilityPanel({ enriched }: ViabilityPanelProps) {
  const viabilityScore = enriched?.viability_score ? parseFloat(enriched.viability_score) : null
  const viabilityTier = enriched?.viability_tier

  // Parse viability factors
  const factors: ViabilityFactors | null = enriched?.viability_factors
    ? (() => {
        try {
          return JSON.parse(enriched.viability_factors)
        } catch {
          return null
        }
      })()
    : null

  // Calculate FAI from flow data
  const flow1d = enriched?.taoflow_1d ? parseFloat(enriched.taoflow_1d) : 0
  const flow7d = enriched?.taoflow_7d ? parseFloat(enriched.taoflow_7d) : 0
  const fai = calculateFAI(flow1d, flow7d)
  const faiPercentile = getFAIPercentile(fai)

  const hasHardFailures = factors?.hard_failures && factors.hard_failures.length > 0
  const ineligibilityReasons = enriched?.ineligibility_reasons

  return (
    <div className="bg-[#1e2128] rounded-lg p-4 space-y-4">
      {/* Header with score badge */}
      <div className="flex items-center justify-between">
        <div className="flex items-center gap-2">
          <Shield className="w-4 h-4 text-[#6b7280]" />
          <span className="text-xs text-[#6b7280] uppercase tracking-wider">Viability Assessment</span>
        </div>
        {viabilityTier && (
          <span className={`inline-flex items-center gap-1.5 px-2.5 py-1 rounded-full text-xs font-medium ${getViabilityTierBgColor(viabilityTier)}`}>
            {formatViabilityTierLabel(viabilityTier)}
            {viabilityScore != null && (
              <span className="opacity-70">({viabilityScore.toFixed(1)})</span>
            )}
          </span>
        )}
      </div>

      {/* Hard Failures Warning */}
      {hasHardFailures && (
        <div className="flex items-start gap-2 p-3 bg-red-900/20 border border-red-700/50 rounded-lg">
          <AlertTriangle className="w-4 h-4 text-red-400 flex-shrink-0 mt-0.5" />
          <div>
            <div className="text-sm font-medium text-red-400">Hard Failures Detected</div>
            <div className="text-xs text-red-300/80 mt-1">
              {factors?.hard_failures?.join(' · ')}
            </div>
          </div>
        </div>
      )}

      {/* Ineligibility Reasons */}
      {ineligibilityReasons && !hasHardFailures && (
        <div className="flex items-start gap-2 p-3 bg-yellow-900/20 border border-yellow-700/50 rounded-lg">
          <Info className="w-4 h-4 text-yellow-400 flex-shrink-0 mt-0.5" />
          <div>
            <div className="text-sm font-medium text-yellow-400">Ineligible</div>
            <div className="text-xs text-yellow-300/80 mt-1">{ineligibilityReasons}</div>
          </div>
        </div>
      )}

      {/* Factor Bars - only show if no hard failures */}
      {factors && !hasHardFailures && (
        <div className="space-y-3">
          <FactorBar
            label="Flow Momentum (FAI)"
            raw={fai !== null ? fai.toFixed(2) : '--'}
            percentile={faiPercentile}
          />
          <FactorBar
            label="TAO Reserve"
            raw={factors.tao_reserve_raw != null ? formatCompact(factors.tao_reserve_raw) + ' τ' : '--'}
            percentile={factors.tao_reserve_percentile}
            weighted={factors.tao_reserve_weighted}
          />
          <FactorBar
            label="Net Flow (7d)"
            raw={factors.net_flow_7d_raw != null ? formatTaoShort(factors.net_flow_7d_raw) + ' τ' : '--'}
            percentile={factors.net_flow_7d_percentile}
            weighted={factors.net_flow_7d_weighted}
          />
          <FactorBar
            label="Emission Share"
            raw={factors.emission_share_raw != null ? (factors.emission_share_raw * 100).toFixed(2) + '%' : '--'}
            percentile={factors.emission_share_percentile}
            weighted={factors.emission_share_weighted}
          />
          <FactorBar
            label="Max Drawdown (30d)"
            raw={factors.max_drawdown_30d_raw != null ? (factors.max_drawdown_30d_raw * 100).toFixed(1) + '%' : '--'}
            percentile={factors.max_drawdown_30d_percentile}
            weighted={factors.max_drawdown_30d_weighted}
            isNegative
          />
        </div>
      )}

      {/* Key Subnet Metrics */}
      <div className="pt-3 border-t border-[#2a2f38] space-y-2">
        <div className="text-xs text-[#6b7280] uppercase tracking-wider mb-2">Key Metrics</div>
        <div className="grid grid-cols-2 gap-2 text-xs">
          <div className="flex justify-between">
            <span className="text-[#8a8f98]">Age</span>
            <span className="text-[#8faabe] tabular-nums">{enriched?.age_days ?? '--'} days</span>
          </div>
          <div className="flex justify-between">
            <span className="text-[#8a8f98]">Holders</span>
            <span className="text-[#8faabe] tabular-nums">{enriched?.holder_count?.toLocaleString() ?? '--'}</span>
          </div>
          <div className="flex justify-between">
            <span className="text-[#8a8f98]">Owner Take</span>
            <span className="text-[#8faabe] tabular-nums">
              {enriched?.owner_take != null ? `${(parseFloat(enriched.owner_take) * 100).toFixed(2)}%` : '--'}
            </span>
          </div>
          <div className="flex justify-between">
            <span className="text-[#8a8f98]">Pool Fee</span>
            <span className="text-[#8faabe] tabular-nums">
              {enriched?.fee_rate != null ? `${(parseFloat(enriched.fee_rate) * 100).toFixed(3)}%` : '--'}
            </span>
          </div>
        </div>
      </div>

      {/* Healthy indicator for high-tier subnets */}
      {viabilityTier === 'tier1' && !hasHardFailures && (
        <div className="flex items-center gap-2 p-2 bg-green-900/20 border border-green-700/30 rounded-lg">
          <CheckCircle className="w-4 h-4 text-green-400" />
          <span className="text-xs text-green-400">Strong viability indicators</span>
        </div>
      )}
    </div>
  )
}
