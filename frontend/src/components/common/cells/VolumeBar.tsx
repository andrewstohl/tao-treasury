import { formatCompact } from '../../../utils/format'

interface VolumeBarProps {
  volume24h: number | null | undefined
  buyVolume: number | null | undefined
  sellVolume: number | null | undefined
}

export default function VolumeBar({ volume24h, buyVolume, sellVolume }: VolumeBarProps) {
  if (volume24h == null || isNaN(volume24h) || volume24h === 0) {
    return <span className="text-gray-600 text-sm">--</span>
  }

  const total = (buyVolume || 0) + (sellVolume || 0)
  const buyPct = total > 0 ? ((buyVolume || 0) / total) * 100 : 50

  return (
    <div className="text-right">
      <div className="text-sm font-mono">{formatCompact(volume24h)} τ</div>
      <div className="w-full h-1.5 bg-gray-700 rounded-full mt-1 overflow-hidden flex">
        <div
          className="bg-green-500 h-full"
          style={{ width: `${buyPct}%` }}
        />
        <div
          className="bg-red-500 h-full"
          style={{ width: `${100 - buyPct}%` }}
        />
      </div>
    </div>
  )
}
