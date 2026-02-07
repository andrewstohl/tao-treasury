import { Github, Globe, MessageCircle, Twitter, ExternalLink, User } from 'lucide-react'
import type { SubnetIdentity, EnrichedSubnet } from '../../../types'

interface SubnetAboutProps {
  identity: SubnetIdentity | null | undefined
  enriched: EnrichedSubnet | null
}

function SocialLink({
  href,
  icon: Icon,
  label,
}: {
  href: string
  icon: React.ComponentType<{ className?: string }>
  label: string
}) {
  return (
    <a
      href={href}
      target="_blank"
      rel="noopener noreferrer"
      className="flex items-center gap-2 px-3 py-2 bg-[#0d0f12] hover:bg-[#16181d] rounded-lg transition-colors group"
      title={label}
    >
      <Icon className="w-4 h-4 text-[#6b7280] group-hover:text-white transition-colors" />
      <span className="text-xs text-[#8a8f98] group-hover:text-white transition-colors">{label}</span>
    </a>
  )
}

export default function SubnetAbout({ identity, enriched }: SubnetAboutProps) {
  const hasContent = identity && (
    identity.tagline ||
    identity.summary ||
    (identity.tags && identity.tags.length > 0) ||
    identity.github_repo ||
    identity.subnet_url ||
    identity.discord ||
    identity.twitter
  )

  if (!hasContent && !enriched?.owner_address) {
    return null
  }

  return (
    <div className="bg-[#1e2128] rounded-lg p-4 space-y-4">
      <div className="text-xs text-[#6b7280] uppercase tracking-wider">About</div>

      {/* Tagline */}
      {identity?.tagline && (
        <p className="text-base font-medium text-white">{identity.tagline}</p>
      )}

      {/* Summary */}
      {identity?.summary && (
        <p className="text-sm text-[#8faabe] leading-relaxed">{identity.summary}</p>
      )}

      {/* Tags */}
      {identity?.tags && identity.tags.length > 0 && (
        <div className="flex flex-wrap gap-1.5">
          {identity.tags.map((tag) => (
            <span
              key={tag}
              className="px-2 py-0.5 rounded-full text-xs font-medium bg-[#2a3ded]/20 text-[#8faabe] border border-[#2a3ded]/30"
            >
              {tag}
            </span>
          ))}
        </div>
      )}

      {/* Links */}
      {(identity?.github_repo || identity?.subnet_url || identity?.discord || identity?.twitter) && (
        <div className="flex flex-wrap gap-2 pt-2">
          {identity?.github_repo && (
            <SocialLink href={identity.github_repo} icon={Github} label="GitHub" />
          )}
          {identity?.subnet_url && (
            <SocialLink
              href={identity.subnet_url.startsWith('http') ? identity.subnet_url : `https://${identity.subnet_url}`}
              icon={Globe}
              label="Website"
            />
          )}
          {identity?.discord && (
            <SocialLink
              href={identity.discord.startsWith('http') ? identity.discord : `https://discord.gg/${identity.discord}`}
              icon={MessageCircle}
              label="Discord"
            />
          )}
          {identity?.twitter && (
            <SocialLink
              href={identity.twitter.startsWith('http') ? identity.twitter : `https://twitter.com/${identity.twitter}`}
              icon={Twitter}
              label="Twitter"
            />
          )}
        </div>
      )}

      {/* Owner info */}
      {enriched?.owner_address && (
        <div className="pt-3 border-t border-[#2a2f38]">
          <div className="flex items-center gap-2">
            <User className="w-3.5 h-3.5 text-[#6b7280]" />
            <span className="text-xs text-[#6b7280]">Owner:</span>
            <code className="text-xs text-[#8faabe] font-mono">
              {enriched.owner_address.slice(0, 8)}...{enriched.owner_address.slice(-6)}
            </code>
            <a
              href={`https://taostats.io/account/${enriched.owner_address}`}
              target="_blank"
              rel="noopener noreferrer"
              className="text-[#6b7280] hover:text-white transition-colors"
              title="View on TaoStats"
            >
              <ExternalLink className="w-3 h-3" />
            </a>
          </div>
        </div>
      )}
    </div>
  )
}
