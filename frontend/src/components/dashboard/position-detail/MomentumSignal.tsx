import { TrendingUp, TrendingDown } from 'lucide-react'
import type { VolatilePoolData, EnrichedSubnet } from '../../../types'
import { formatTaoShort } from '../../../utils/format'

interface MomentumSignalProps {
  volatile: VolatilePoolData | null | undefined
  enriched: EnrichedSubnet | null
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
 * Slider bar component - consistent style throughout
 */
function SliderBar({
  label,
  value,
  subValue,
  percentage,
  color = 'blue',
  showZeroCenter = false,
}: {
  label: string
  value: string
  subValue?: string
  percentage: number // 0-100
  color?: 'blue' | 'green' | 'red' | 'gradient'
  showZeroCenter?: boolean
}) {
  const barColorClass = {
    blue: 'bg-[#2a3ded]',
    green: 'bg-green-500',
    red: 'bg-red-500',
    gradient: '', // handled separately
  }[color]

  return (
    <div className="space-y-1.5">
      <div className="flex justify-between items-baseline">
        <span className="text-xs text-[#6b7280]">{label}</span>
        <div className="text-right">
          <span className="text-sm font-medium text-white tabular-nums">{value}</span>
          {subValue && (
            <span className="text-xs text-[#6b7280] ml-1.5">{subValue}</span>
          )}
        </div>
      </div>
      <div className="h-1.5 bg-[#0d0f12] rounded-full overflow-hidden">
        {showZeroCenter ? (
          // Centered bar for values that can be positive/negative
          <div className="relative h-full">
            <div className="absolute left-1/2 top-0 bottom-0 w-px bg-[#2a2f38]" />
            {percentage >= 50 ? (
              <div
                className={`absolute left-1/2 h-full ${percentage > 50 ? 'bg-green-500' : ''} rounded-r-full`}
                style={{ width: `${Math.min(50, percentage - 50)}%` }}
              />
            ) : (
              <div
                className="absolute right-1/2 h-full bg-red-500 rounded-l-full"
                style={{ width: `${Math.min(50, 50 - percentage)}%` }}
              />
            )}
          </div>
        ) : color === 'gradient' ? (
          // Buy/Sell gradient bar
          <div className="flex h-full">
            <div className="bg-green-500" style={{ width: `${percentage}%` }} />
            <div className="bg-red-500" style={{ width: `${100 - percentage}%` }} />
          </div>
        ) : (
          // Standard left-to-right bar
          <div
            className={`h-full ${barColorClass} rounded-full transition-all`}
            style={{ width: `${Math.min(100, Math.max(0, percentage))}%` }}
          />
        )}
      </div>
    </div>
  )
}

export default function MomentumSignal({ volatile, enriched }: MomentumSignalProps) {
  // Flow data
  const flow1d = enriched?.taoflow_1d ? parseFloat(enriched.taoflow_1d) : 0
  const flow7d = enriched?.taoflow_7d ? parseFloat(enriched.taoflow_7d) : 0

  // Calculate FAI
  const fai = calculateFAI(flow1d, flow7d)

  // FAI percentage for slider (0 = -2, 50 = 1, 100 = 4+)
  // Maps FAI range of -2 to 4 onto 0-100%
  const faiPct = fai !== null ? Math.min(100, Math.max(0, ((fai + 2) / 6) * 100)) : 50

  // FAI quintile label
  const faiQuintile = fai !== null
    ? fai >= 1.5 ? 'Q5'
    : fai >= 1.2 ? 'Q4'
    : fai >= 0.8 ? 'Q3'
    : fai >= 0.5 ? 'Q2'
    : 'Q1'
    : '--'

  // 7D flow percentage (centered at 0, scale to reasonable range)
  // Assume ±500 TAO is full scale
  const flow7dPct = 50 + Math.min(50, Math.max(-50, (flow7d / 500) * 50))

  // 24h trading activity
  const buys = volatile?.buys_24h ?? 0
  const sells = volatile?.sells_24h ?? 0
  const buyVolume = volatile?.tao_buy_volume_24h ?? 0
  const sellVolume = volatile?.tao_sell_volume_24h ?? 0
  const totalTrades = buys + sells
  const buyPressurePct = totalTrades > 0 ? (buys / totalTrades) * 100 : 50
  const totalVolume = buyVolume + sellVolume
  const buyVolumePct = totalVolume > 0 ? (buyVolume / totalVolume) * 100 : 50

  return (
    <div className="bg-[#1e2128] rounded-lg p-4 flex flex-col" style={{ height: '282px' }}>
      {/* Header */}
      <div className="text-xs text-[#6b7280] uppercase tracking-wider mb-4">
        Flow Momentum
      </div>

      {/* Main metrics */}
      <div className="space-y-4 flex-1">
        {/* FAI - Primary signal */}
        <SliderBar
          label="Flow Acceleration (FAI)"
          value={fai !== null ? fai.toFixed(2) : '--'}
          subValue={faiQuintile}
          percentage={faiPct}
          color="blue"
        />

        {/* 7D Net Flow */}
        <SliderBar
          label="7D Net Flow"
          value={`${flow7d >= 0 ? '+' : ''}${formatTaoShort(flow7d)}τ`}
          percentage={flow7dPct}
          showZeroCenter
        />

        {/* 1D Flow */}
        <SliderBar
          label="1D Flow"
          value={`${flow1d >= 0 ? '+' : ''}${formatTaoShort(flow1d)}τ`}
          percentage={50 + Math.min(50, Math.max(-50, (flow1d / 100) * 50))}
          showZeroCenter
        />
      </div>

      {/* Divider */}
      <div className="border-t border-[#2a2f38] my-3" />

      {/* 24H Activity Section */}
      <div className="space-y-3">
        <div className="text-xs text-[#6b7280] uppercase tracking-wider">24H Activity</div>

        {/* Buy/Sell Trades */}
        <div className="space-y-1.5">
          <div className="flex justify-between text-xs">
            <span className="flex items-center gap-1 text-green-400">
              <TrendingUp className="w-3 h-3" />
              {buys} buys
            </span>
            <span className="flex items-center gap-1 text-red-400">
              {sells} sells
              <TrendingDown className="w-3 h-3" />
            </span>
          </div>
          <div className="h-1.5 bg-[#0d0f12] rounded-full overflow-hidden flex">
            <div className="bg-green-500" style={{ width: `${buyPressurePct}%` }} />
            <div className="bg-red-500" style={{ width: `${100 - buyPressurePct}%` }} />
          </div>
        </div>

        {/* Volume */}
        <div className="space-y-1.5">
          <div className="flex justify-between text-xs">
            <span className="text-green-400/70 tabular-nums">{formatTaoShort(buyVolume)}τ</span>
            <span className="text-red-400/70 tabular-nums">{formatTaoShort(sellVolume)}τ</span>
          </div>
          <div className="h-1.5 bg-[#0d0f12] rounded-full overflow-hidden flex">
            <div className="bg-green-600/50" style={{ width: `${buyVolumePct}%` }} />
            <div className="bg-red-600/50" style={{ width: `${100 - buyVolumePct}%` }} />
          </div>
        </div>
      </div>
    </div>
  )
}
