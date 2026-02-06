import { Github, Globe, MessageCircle, ExternalLink } from 'lucide-react'
import { formatTaoShort, formatCompact, getViabilityTierBgColor, formatViabilityTierLabel } from '../../utils/format'
import type { VolatilePoolData, SubnetIdentity } from '../../types'

interface SubnetExpandedRowProps {
  volatile: VolatilePoolData | null | undefined
  identity?: SubnetIdentity | null
  ownerAddress?: string | null
  ownerTake?: string | null
  feeRate?: string | null
  incentiveBurn?: string | null
  ageDays?: number
  holderCount?: number
  ineligibilityReasons?: string | null
  taoflow1d?: string
  taoflow3d?: string
  taoflow7d?: string
  taoflow14d?: string
  viabilityScore?: string | null
  viabilityTier?: string | null
  viabilityFactors?: string | null
  /** When false, Taoflow & Trading column is hidden (e.g. when rendered separately). Default true. */
  showTaoflow?: boolean
}

export default function SubnetExpandedRow({
  volatile,
  identity,
  ownerAddress,
  ownerTake,
  feeRate,
  incentiveBurn,
  ageDays,
  holderCount,
  ineligibilityReasons,
  taoflow1d,
  taoflow3d,
  taoflow7d,
  taoflow14d,
  viabilityScore,
  viabilityTier,
  viabilityFactors,
  showTaoflow = true,
}: SubnetExpandedRowProps) {
  // Parse viability factors JSON
  const factors = viabilityFactors ? (() => {
    try { return JSON.parse(viabilityFactors) } catch { return null }
  })() : null
  const hasViability = viabilityTier != null
  return (
    <div className="p-4 bg-[#050d15]/50 text-sm space-y-4">
      {/* About Section */}
      {identity && (identity.tagline || identity.summary || (identity.tags && identity.tags.length > 0)) && (
        <div className="space-y-2">
          <h4 className="text-xs font-semibold text-[#6f87a0] uppercase tracking-wider">About</h4>
          {identity.tagline && (
            <p className="text-[#a8c4d9] font-medium text-sm">{identity.tagline}</p>
          )}
          {identity.summary && (
            <p className="text-[#8faabe] leading-relaxed text-sm">{identity.summary}</p>
          )}
          {identity.tags && identity.tags.length > 0 && (
            <div className="flex flex-wrap gap-1.5">
              {identity.tags.map((tag) => (
                <span
                  key={tag}
                  className="px-2 py-0.5 rounded-full text-xs font-medium bg-tao-600/20 text-tao-300 border border-tao-600/30"
                >
                  {tag}
                </span>
              ))}
            </div>
          )}
          <div className="flex items-center gap-3 pt-1">
            {identity.github_repo && (
              <a href={identity.github_repo} target="_blank" rel="noopener noreferrer"
                 className="text-[#6f87a0] hover:text-white transition-colors" title="GitHub">
                <Github className="w-4 h-4" />
              </a>
            )}
            {identity.subnet_url && (
              <a href={identity.subnet_url.startsWith('http') ? identity.subnet_url : `https://${identity.subnet_url}`}
                 target="_blank" rel="noopener noreferrer"
                 className="text-[#6f87a0] hover:text-white transition-colors" title="Website">
                <Globe className="w-4 h-4" />
              </a>
            )}
            {identity.discord && (
              <a href={identity.discord.startsWith('http') ? identity.discord : `https://discord.gg/${identity.discord}`}
                 target="_blank" rel="noopener noreferrer"
                 className="text-[#6f87a0] hover:text-white transition-colors" title="Discord">
                <MessageCircle className="w-4 h-4" />
              </a>
            )}
            {identity.twitter && (
              <a href={identity.twitter.startsWith('http') ? identity.twitter : `https://twitter.com/${identity.twitter}`}
                 target="_blank" rel="noopener noreferrer"
                 className="text-[#6f87a0] hover:text-white transition-colors" title="Twitter/X">
                <ExternalLink className="w-4 h-4" />
              </a>
            )}
          </div>
        </div>
      )}

      {/* Grid: Pool Composition, Taoflow (optional), Subnet Info */}
      <div className={`grid grid-cols-1 ${showTaoflow ? 'md:grid-cols-3' : 'md:grid-cols-2'} gap-6`}>
        {/* Column 1: Pool Composition */}
        <div className="space-y-2">
          <h4 className="text-xs font-semibold text-[#6f87a0] uppercase tracking-wider">Pool Composition</h4>
          <div className="space-y-1">
            <Row label="Alpha in Pool" value={volatile?.alpha_in_pool != null ? formatCompact(volatile.alpha_in_pool) + ' α' : '--'} />
            <Row label="Alpha Staked" value={volatile?.alpha_staked != null ? formatCompact(volatile.alpha_staked) + ' α' : '--'} />
            <Row label="Total Alpha" value={volatile?.total_alpha != null ? formatCompact(volatile.total_alpha) + ' α' : '--'} />
            <Row label="Root Proportion" value={volatile?.root_prop != null ? `${(volatile.root_prop * 100).toFixed(1)}%` : '--'} />
            <Row
              label="Startup Mode"
              value={volatile?.startup_mode != null ? (volatile.startup_mode ? 'Yes' : 'No') : '--'}
              valueColor={volatile?.startup_mode ? 'text-yellow-400' : undefined}
            />
          </div>
        </div>

        {/* Column 2: Taoflow & Trading (optional) */}
        {showTaoflow && (
          <div className="space-y-2">
            <h4 className="text-xs font-semibold text-[#6f87a0] uppercase tracking-wider">Taoflow & Trading</h4>
            <div className="space-y-1">
              <FlowRow label="1d Flow" value={taoflow1d} />
              <FlowRow label="3d Flow" value={taoflow3d} />
              <FlowRow label="7d Flow" value={taoflow7d} />
              <FlowRow label="14d Flow" value={taoflow14d} />
              <div className="border-t border-[#1e3a5f] my-1" />
              <Row label="Buys (24h)" value={volatile?.buys_24h != null ? String(volatile.buys_24h) : '--'} />
              <Row label="Sells (24h)" value={volatile?.sells_24h != null ? String(volatile.sells_24h) : '--'} />
              <Row label="Buyers (24h)" value={volatile?.buyers_24h != null ? String(volatile.buyers_24h) : '--'} />
              <Row label="Sellers (24h)" value={volatile?.sellers_24h != null ? String(volatile.sellers_24h) : '--'} />
              <Row label="24h High" value={volatile?.high_24h != null ? volatile.high_24h.toFixed(6) + ' τ' : '--'} />
              <Row label="24h Low" value={volatile?.low_24h != null ? volatile.low_24h.toFixed(6) + ' τ' : '--'} />
            </div>
          </div>
        )}

        {/* Column 3 (or 2): Subnet Info */}
        <div className="space-y-2">
          <h4 className="text-xs font-semibold text-[#6f87a0] uppercase tracking-wider">Subnet Info</h4>
          <div className="space-y-1">
            <Row label="Owner" value={ownerAddress ? `${ownerAddress.slice(0, 8)}...${ownerAddress.slice(-6)}` : '--'} />
            <Row label="Owner Take" value={ownerTake != null ? `${(parseFloat(ownerTake) * 100).toFixed(2)}%` : '--'} />
            <Row
              label="Pool Fee (per swap)"
              value={feeRate != null ? `${(parseFloat(feeRate) * 100).toFixed(3)}%` : '--'}
            />
            <Row
              label="Incentive Burn"
              value={incentiveBurn != null ? `${(parseFloat(incentiveBurn) * 100).toFixed(1)}%` : '--'}
              valueColor={incentiveBurn != null && parseFloat(incentiveBurn) >= 1 ? 'text-red-400' : incentiveBurn != null && parseFloat(incentiveBurn) >= 0.5 ? 'text-yellow-400' : undefined}
            />
            <Row label="Age" value={ageDays != null ? `${ageDays} days` : '--'} />
            <Row label="Holders" value={holderCount != null ? holderCount.toLocaleString() : '--'} />
            {ineligibilityReasons && (
              <div className="mt-2 text-xs text-red-400 bg-red-900/20 rounded p-2">
                {ineligibilityReasons}
              </div>
            )}
          </div>
        </div>
      </div>

      {/* Viability Breakdown */}
      {hasViability && (
        <div className="space-y-2">
          <h4 className="text-xs font-semibold text-[#6f87a0] uppercase tracking-wider">Viability Assessment</h4>
          <div className="flex items-center gap-3">
            <span className={`inline-flex items-center gap-1 px-2 py-0.5 rounded-full text-xs font-medium ${getViabilityTierBgColor(viabilityTier)}`}>
              {formatViabilityTierLabel(viabilityTier)}
              {viabilityScore != null && <span className="opacity-70">({parseFloat(viabilityScore).toFixed(1)})</span>}
            </span>
          </div>
          {factors && !factors.hard_failures && (
            <div className="grid grid-cols-2 md:grid-cols-3 gap-x-6 gap-y-1 mt-2">
              <FactorRow label="TAO Reserve" raw={factors.tao_reserve_raw != null ? formatCompact(factors.tao_reserve_raw) + ' τ' : '--'} pctile={factors.tao_reserve_percentile} weighted={factors.tao_reserve_weighted} />
              <FactorRow label="Net Flow 7d" raw={factors.net_flow_7d_raw != null ? formatTaoShort(factors.net_flow_7d_raw) + ' τ' : '--'} pctile={factors.net_flow_7d_percentile} weighted={factors.net_flow_7d_weighted} />
              <FactorRow label="Emission Share" raw={factors.emission_share_raw != null ? (factors.emission_share_raw * 100).toFixed(2) + '%' : '--'} pctile={factors.emission_share_percentile} weighted={factors.emission_share_weighted} />
              <FactorRow label="Price Trend 7d" raw={factors.price_trend_7d_raw != null ? (factors.price_trend_7d_raw * 100).toFixed(2) + '%' : '--'} pctile={factors.price_trend_7d_percentile} weighted={factors.price_trend_7d_weighted} />
              <FactorRow label="Subnet Age" raw={factors.subnet_age_raw != null ? factors.subnet_age_raw + 'd' : '--'} pctile={factors.subnet_age_percentile} weighted={factors.subnet_age_weighted} />
              <FactorRow label="Max DD 30d" raw={factors.max_drawdown_30d_raw != null ? (factors.max_drawdown_30d_raw * 100).toFixed(1) + '%' : '--'} pctile={factors.max_drawdown_30d_percentile} weighted={factors.max_drawdown_30d_weighted} />
            </div>
          )}
          {factors && factors.hard_failures && factors.hard_failures.length > 0 && (
            <div className="text-xs text-red-400 bg-red-900/20 rounded p-2 mt-1">
              <span className="font-medium">Hard failures: </span>
              {factors.hard_failures.join(' · ')}
            </div>
          )}
        </div>
      )}
    </div>
  )
}

function FactorRow({ label, raw, pctile, weighted }: { label: string; raw: string; pctile?: number; weighted?: number }) {
  return (
    <div className="text-xs">
      <span className="text-[#5a7a94]">{label}:</span>{' '}
      <span className="tabular-nums text-[#8faabe]">{raw}</span>
      {pctile != null && (
        <span className="text-[#5a7a94] ml-1">(P{pctile.toFixed(0)} → {weighted?.toFixed(1)})</span>
      )}
    </div>
  )
}

function Row({ label, value, valueColor }: { label: string; value: string; valueColor?: string }) {
  return (
    <div className="flex justify-between">
      <span className="text-[#5a7a94]">{label}</span>
      <span className={`tabular-nums ${valueColor || 'text-[#8faabe]'}`}>{value}</span>
    </div>
  )
}

export function FlowRow({ label, value }: { label: string; value: string | undefined }) {
  if (!value) return <Row label={label} value="--" />
  const num = parseFloat(value)
  const color = num >= 0 ? 'text-green-400' : 'text-red-400'
  const prefix = num >= 0 ? '+' : ''
  return <Row label={label} value={`${prefix}${formatTaoShort(num)} τ`} valueColor={color} />
}
