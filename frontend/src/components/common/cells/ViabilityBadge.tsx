import { getViabilityTierBgColor, formatViabilityTierLabel } from '../../../utils/format'

interface ViabilityBadgeProps {
  tier: string | null | undefined
  score?: string | number | null | undefined
}

export default function ViabilityBadge({ tier, score }: ViabilityBadgeProps) {
  if (!tier) {
    return <span className="text-gray-600 text-sm">--</span>
  }

  const label = formatViabilityTierLabel(tier)
  const numScore = score != null ? (typeof score === 'string' ? parseFloat(score) : score) : null

  return (
    <span className={`inline-flex items-center gap-1 px-2 py-0.5 rounded-full text-xs font-medium ${getViabilityTierBgColor(tier)}`}>
      {label}
      {numScore != null && !isNaN(numScore) && <span className="opacity-70">({Math.round(numScore)})</span>}
    </span>
  )
}
