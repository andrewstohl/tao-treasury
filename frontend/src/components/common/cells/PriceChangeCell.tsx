interface PriceChangeCellProps {
  change24h: number | null | undefined
  change7d?: number | null | undefined
}

function formatChange(val: number | null | undefined): string {
  if (val == null || isNaN(val)) return '--'
  return `${val >= 0 ? '+' : ''}${val.toFixed(2)}%`
}

function changeColor(val: number | null | undefined): string {
  if (val == null || isNaN(val)) return 'text-gray-600'
  return val >= 0 ? 'text-green-400' : 'text-red-400'
}

export default function PriceChangeCell({ change24h, change7d }: PriceChangeCellProps) {
  return (
    <div className="text-right text-sm tabular-nums leading-tight">
      <div className={changeColor(change24h)}>{formatChange(change24h)}</div>
      {change7d !== undefined && (
        <div className={`text-xs ${changeColor(change7d)}`}>{formatChange(change7d)}</div>
      )}
    </div>
  )
}
