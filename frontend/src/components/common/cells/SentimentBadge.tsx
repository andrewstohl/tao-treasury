interface SentimentBadgeProps {
  sentiment: string | null | undefined
  index?: number | null | undefined
}

function sentimentColor(sentiment: string | null | undefined): string {
  switch (sentiment) {
    case 'Extreme Fear': return 'bg-red-600/20 text-red-400'
    case 'Fear': return 'bg-orange-600/20 text-orange-400'
    case 'Neutral': return 'bg-gray-600/20 text-gray-400'
    case 'Greed': return 'bg-green-600/20 text-green-400'
    case 'Extreme Greed': return 'bg-emerald-600/20 text-emerald-400'
    default: return 'bg-gray-700/30 text-gray-600'
  }
}

export default function SentimentBadge({ sentiment, index }: SentimentBadgeProps) {
  if (!sentiment) {
    return <span className="text-gray-600 text-sm">--</span>
  }

  return (
    <span className={`inline-flex items-center gap-1 px-2 py-0.5 rounded-full text-xs font-medium ${sentimentColor(sentiment)}`}>
      {sentiment}
      {index != null && <span className="opacity-70">({Math.round(index)})</span>}
    </span>
  )
}
