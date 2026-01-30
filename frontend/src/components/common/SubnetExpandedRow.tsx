import { Github, Globe, MessageCircle, ExternalLink } from 'lucide-react'
import { formatTaoShort, formatCompact } from '../../utils/format'
import type { VolatilePoolData, SubnetIdentity, DevActivity } from '../../types'

interface SubnetExpandedRowProps {
  volatile: VolatilePoolData | null | undefined
  identity?: SubnetIdentity | null
  devActivity?: DevActivity | null
  ownerAddress?: string | null
  ownerTake?: string | null
  ageDays?: number
  holderCount?: number
  ineligibilityReasons?: string | null
  taoflow1d?: string
  taoflow3d?: string
  taoflow7d?: string
  taoflow14d?: string
}

export default function SubnetExpandedRow({
  volatile,
  identity,
  devActivity,
  ownerAddress,
  ownerTake,
  ageDays,
  holderCount,
  ineligibilityReasons,
  taoflow1d,
  taoflow3d,
  taoflow7d,
  taoflow14d,
}: SubnetExpandedRowProps) {
  return (
    <div className="p-4 bg-gray-900/50 text-sm space-y-4">
      {/* About Section */}
      {identity && (identity.tagline || identity.summary || (identity.tags && identity.tags.length > 0)) && (
        <div className="space-y-2">
          <h4 className="text-xs font-semibold text-gray-400 uppercase tracking-wider">About</h4>
          {identity.tagline && (
            <p className="text-gray-200 font-medium text-sm">{identity.tagline}</p>
          )}
          {identity.summary && (
            <p className="text-gray-300 leading-relaxed text-sm">{identity.summary}</p>
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
                 className="text-gray-400 hover:text-white transition-colors" title="GitHub">
                <Github className="w-4 h-4" />
              </a>
            )}
            {identity.subnet_url && (
              <a href={identity.subnet_url.startsWith('http') ? identity.subnet_url : `https://${identity.subnet_url}`}
                 target="_blank" rel="noopener noreferrer"
                 className="text-gray-400 hover:text-white transition-colors" title="Website">
                <Globe className="w-4 h-4" />
              </a>
            )}
            {identity.discord && (
              <a href={identity.discord.startsWith('http') ? identity.discord : `https://discord.gg/${identity.discord}`}
                 target="_blank" rel="noopener noreferrer"
                 className="text-gray-400 hover:text-white transition-colors" title="Discord">
                <MessageCircle className="w-4 h-4" />
              </a>
            )}
            {identity.twitter && (
              <a href={identity.twitter.startsWith('http') ? identity.twitter : `https://twitter.com/${identity.twitter}`}
                 target="_blank" rel="noopener noreferrer"
                 className="text-gray-400 hover:text-white transition-colors" title="Twitter/X">
                <ExternalLink className="w-4 h-4" />
              </a>
            )}
          </div>
        </div>
      )}

      {/* Dev Activity Section */}
      {devActivity && devActivity.commits_30d != null && (
        <div className="space-y-2">
          <h4 className="text-xs font-semibold text-gray-400 uppercase tracking-wider">Developer Activity</h4>
          <div className="grid grid-cols-2 md:grid-cols-4 gap-4">
            <DevStat label="Commits (30d)" value={devActivity.commits_30d} />
            <DevStat label="Commits (7d)" value={devActivity.commits_7d} />
            <DevStat label="PRs Merged (7d)" value={devActivity.prs_merged_7d} />
            <DevStat label="Contributors (30d)" value={devActivity.unique_contributors_30d} />
          </div>
          {devActivity.days_since_last_event != null && (
            <div className="text-xs text-gray-500">
              Last activity: {devActivity.days_since_last_event === 0
                ? 'today'
                : `${devActivity.days_since_last_event} day${devActivity.days_since_last_event === 1 ? '' : 's'} ago`}
            </div>
          )}
        </div>
      )}

      {/* Original 3-column grid */}
      <div className="grid grid-cols-1 md:grid-cols-3 gap-6">
        {/* Column 1: Pool Composition */}
        <div className="space-y-2">
          <h4 className="text-xs font-semibold text-gray-400 uppercase tracking-wider">Pool Composition</h4>
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

        {/* Column 2: Taoflow & Trading */}
        <div className="space-y-2">
          <h4 className="text-xs font-semibold text-gray-400 uppercase tracking-wider">Taoflow & Trading</h4>
          <div className="space-y-1">
            <FlowRow label="1d Flow" value={taoflow1d} />
            <FlowRow label="3d Flow" value={taoflow3d} />
            <FlowRow label="7d Flow" value={taoflow7d} />
            <FlowRow label="14d Flow" value={taoflow14d} />
            <div className="border-t border-gray-700 my-1" />
            <Row label="Buys (24h)" value={volatile?.buys_24h != null ? String(volatile.buys_24h) : '--'} />
            <Row label="Sells (24h)" value={volatile?.sells_24h != null ? String(volatile.sells_24h) : '--'} />
            <Row label="Buyers (24h)" value={volatile?.buyers_24h != null ? String(volatile.buyers_24h) : '--'} />
            <Row label="Sellers (24h)" value={volatile?.sellers_24h != null ? String(volatile.sellers_24h) : '--'} />
            <Row label="24h High" value={volatile?.high_24h != null ? volatile.high_24h.toFixed(6) + ' τ' : '--'} />
            <Row label="24h Low" value={volatile?.low_24h != null ? volatile.low_24h.toFixed(6) + ' τ' : '--'} />
          </div>
        </div>

        {/* Column 3: Ownership & Info */}
        <div className="space-y-2">
          <h4 className="text-xs font-semibold text-gray-400 uppercase tracking-wider">Subnet Info</h4>
          <div className="space-y-1">
            <Row label="Owner" value={ownerAddress ? `${ownerAddress.slice(0, 8)}...${ownerAddress.slice(-6)}` : '--'} />
            <Row label="Owner Take" value={ownerTake != null ? `${(parseFloat(ownerTake) * 100).toFixed(2)}%` : '--'} />
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
    </div>
  )
}

function Row({ label, value, valueColor }: { label: string; value: string; valueColor?: string }) {
  return (
    <div className="flex justify-between">
      <span className="text-gray-500">{label}</span>
      <span className={`font-mono ${valueColor || 'text-gray-300'}`}>{value}</span>
    </div>
  )
}

function FlowRow({ label, value }: { label: string; value: string | undefined }) {
  if (!value) return <Row label={label} value="--" />
  const num = parseFloat(value)
  const color = num >= 0 ? 'text-green-400' : 'text-red-400'
  const prefix = num >= 0 ? '+' : ''
  return <Row label={label} value={`${prefix}${formatTaoShort(num)} τ`} valueColor={color} />
}

function DevStat({ label, value }: { label: string; value: number | null | undefined }) {
  return (
    <div>
      <div className="text-lg font-mono font-semibold text-white">
        {value != null ? value.toLocaleString() : '--'}
      </div>
      <div className="text-xs text-gray-500">{label}</div>
    </div>
  )
}
