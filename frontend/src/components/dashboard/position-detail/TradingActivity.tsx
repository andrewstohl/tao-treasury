import { TrendingUp, TrendingDown } from 'lucide-react'
import type { VolatilePoolData, EnrichedSubnet } from '../../../types'
import { formatTaoShort } from '../../../utils/format'

interface TradingActivityProps {
  volatile: VolatilePoolData | null | undefined
  enriched: EnrichedSubnet | null
}

export default function TradingActivity({ volatile, enriched }: TradingActivityProps) {
  const v = volatile

  // 24h data
  const buys = v?.buys_24h ?? 0
  const sells = v?.sells_24h ?? 0
  const buyVolume = v?.tao_buy_volume_24h ?? 0
  const sellVolume = v?.tao_sell_volume_24h ?? 0

  // Calculate buy pressure percentage
  const totalTrades = buys + sells
  const buyPressurePct = totalTrades > 0 ? (buys / totalTrades) * 100 : 50

  // Volume-based pressure
  const totalVolumeCalc = buyVolume + sellVolume
  const buyVolumePct = totalVolumeCalc > 0 ? (buyVolume / totalVolumeCalc) * 100 : 50

  // Net flow data
  const flow1d = enriched?.taoflow_1d ? parseFloat(enriched.taoflow_1d) : null
  const flow7d = enriched?.taoflow_7d ? parseFloat(enriched.taoflow_7d) : null

  return (
    <div className="bg-[#1e2128] rounded-lg p-4 flex flex-col" style={{ height: '282px' }}>
      {/* 24H Section */}
      <div className="space-y-2">
        <div className="text-xs text-[#6b7280] uppercase tracking-wider">24H Trading</div>

        {/* Buy/Sell Trades Bar */}
        <div className="space-y-1">
          <div className="flex justify-between text-xs">
            <div className="flex items-center gap-1">
              <TrendingUp className="w-3 h-3 text-green-400" />
              <span className="text-green-400 tabular-nums">{buys}</span>
            </div>
            <div className="flex items-center gap-1">
              <span className="text-red-400 tabular-nums">{sells}</span>
              <TrendingDown className="w-3 h-3 text-red-400" />
            </div>
          </div>

          <div className="relative h-2 rounded-full overflow-hidden flex bg-[#0d0f12]">
            <div
              className="bg-green-500 transition-all duration-300"
              style={{ width: `${buyPressurePct}%` }}
            />
            <div
              className="bg-red-500 transition-all duration-300"
              style={{ width: `${100 - buyPressurePct}%` }}
            />
            {/* Center percentage label */}
            <div className="absolute inset-0 flex items-center justify-center">
              <span className="text-[10px] text-white font-medium drop-shadow-md">
                {buyPressurePct.toFixed(0)}% / {(100 - buyPressurePct).toFixed(0)}%
              </span>
            </div>
          </div>

          <div className="flex justify-between text-[10px] text-[#6b7280]">
            <span>Buys</span>
            <span>Sells</span>
          </div>
        </div>

        {/* Volume Bar with Net Flow */}
        <div className="space-y-1 pt-1">
          <div className="flex justify-between text-xs">
            <span className="text-green-400 tabular-nums">{formatTaoShort(buyVolume)}τ</span>
            <span className="text-red-400 tabular-nums">{formatTaoShort(sellVolume)}τ</span>
          </div>

          <div className="relative h-2 rounded-full overflow-hidden flex bg-[#0d0f12]">
            <div
              className="bg-green-600/70 transition-all duration-300"
              style={{ width: `${buyVolumePct}%` }}
            />
            <div
              className="bg-red-600/70 transition-all duration-300"
              style={{ width: `${100 - buyVolumePct}%` }}
            />
            {/* Center net flow label */}
            {flow1d != null && (
              <div className="absolute inset-0 flex items-center justify-center">
                <span className={`text-[10px] font-medium drop-shadow-md ${flow1d >= 0 ? 'text-green-300' : 'text-red-300'}`}>
                  {flow1d >= 0 ? '+' : ''}{formatTaoShort(flow1d)}τ
                </span>
              </div>
            )}
          </div>

          <div className="flex justify-between text-[10px] text-[#6b7280]">
            <span>Buy Vol</span>
            <span>Sell Vol</span>
          </div>
        </div>
      </div>

      {/* Divider */}
      <div className="border-t border-[#2a2f38] my-3" />

      {/* 7D Section */}
      <div className="space-y-2 flex-1">
        <div className="text-xs text-[#6b7280] uppercase tracking-wider">7D Net Flow</div>

        {flow7d != null ? (
          <div className="space-y-1">
            {/* 7D Flow visualization */}
            <div className="relative h-2 rounded-full overflow-hidden bg-[#0d0f12]">
              {flow7d >= 0 ? (
                <>
                  <div className="absolute left-1/2 h-full w-px bg-[#2a2f38]" />
                  <div
                    className="absolute left-1/2 h-full bg-green-500/70 transition-all duration-300"
                    style={{ width: `${Math.min(50, Math.abs(flow7d) / 100 * 50)}%` }}
                  />
                </>
              ) : (
                <>
                  <div className="absolute left-1/2 h-full w-px bg-[#2a2f38]" />
                  <div
                    className="absolute right-1/2 h-full bg-red-500/70 transition-all duration-300 origin-right"
                    style={{ width: `${Math.min(50, Math.abs(flow7d) / 100 * 50)}%` }}
                  />
                </>
              )}
              {/* Center value */}
              <div className="absolute inset-0 flex items-center justify-center">
                <span className={`text-[10px] font-medium drop-shadow-md ${flow7d >= 0 ? 'text-green-300' : 'text-red-300'}`}>
                  {flow7d >= 0 ? '+' : ''}{formatTaoShort(flow7d)}τ
                </span>
              </div>
            </div>

            <div className="flex justify-between text-[10px] text-[#6b7280]">
              <span>Outflow</span>
              <span>Inflow</span>
            </div>

            {/* Flow indicator */}
            <div className="flex items-center justify-center pt-1">
              <div className={`flex items-center gap-1.5 px-2 py-1 rounded ${flow7d >= 0 ? 'bg-green-500/10' : 'bg-red-500/10'}`}>
                {flow7d >= 0 ? (
                  <TrendingUp className="w-3.5 h-3.5 text-green-400" />
                ) : (
                  <TrendingDown className="w-3.5 h-3.5 text-red-400" />
                )}
                <span className={`text-xs font-medium ${flow7d >= 0 ? 'text-green-400' : 'text-red-400'}`}>
                  Net {flow7d >= 0 ? 'Inflow' : 'Outflow'}
                </span>
              </div>
            </div>
          </div>
        ) : (
          <div className="text-xs text-[#6b7280] text-center py-2">No flow data</div>
        )}
      </div>
    </div>
  )
}
