import { getRegimeBgColor, formatRegimeLabel } from '../../../utils/format'

interface RegimeBadgeProps {
  regime: string | null | undefined
}

export default function RegimeBadge({ regime }: RegimeBadgeProps) {
  if (!regime) {
    return <span className="text-[#4a6a80] text-sm">--</span>
  }

  return (
    <span className={`inline-block px-2 py-0.5 rounded-full text-xs font-medium capitalize ${getRegimeBgColor(regime)}`}>
      {formatRegimeLabel(regime)}
    </span>
  )
}
