import { useEffect, useRef, useState } from 'react'
import { useQuery } from '@tanstack/react-query'
import { createChart, ColorType, LineStyle, IChartApi, CandlestickSeries, Time } from 'lightweight-charts'
import { api } from '../../../services/api'

interface SubnetPriceChartProps {
  netuid: number
  entryPrice: number
  currentPrice: number
  high24h?: number | null
  low24h?: number | null
}

type TimeRange = '24h' | '7d' | '30d'

interface OHLCCandle {
  time: number
  open: number
  high: number
  low: number
  close: number
  volume?: number
}

interface ChartResponse {
  netuid: number
  resolution: string
  status: string
  candles: OHLCCandle[]
}

export default function SubnetPriceChart({
  netuid,
  entryPrice,
  currentPrice,
  high24h,
  low24h,
}: SubnetPriceChartProps) {
  const chartContainerRef = useRef<HTMLDivElement>(null)
  const chartRef = useRef<IChartApi | null>(null)
  const [timeRange, setTimeRange] = useState<TimeRange>('30d')

  // Map time range to resolution and days
  const getChartParams = (range: TimeRange) => {
    switch (range) {
      case '24h':
        return { resolution: '15', days: 1 }  // 15-minute candles
      case '7d':
        return { resolution: '60', days: 7 }  // 1-hour candles
      case '30d':
        return { resolution: '240', days: 30 } // 4-hour candles
    }
  }

  const { resolution, days } = getChartParams(timeRange)

  // Fetch OHLC data from backend
  const { data: chartData, isLoading } = useQuery<ChartResponse>({
    queryKey: ['subnet-chart', netuid, resolution, days],
    queryFn: () => api.getSubnetChart(netuid, resolution, days),
    refetchInterval: 300000, // 5 minutes
    staleTime: 60000, // 1 minute
  })

  useEffect(() => {
    if (!chartContainerRef.current) return

    // Create chart
    const chart = createChart(chartContainerRef.current, {
      layout: {
        background: { type: ColorType.Solid, color: 'transparent' },
        textColor: '#8a8f98',
        fontFamily: 'inherit',
      },
      grid: {
        vertLines: { color: '#1e2128', style: LineStyle.Solid },
        horzLines: { color: '#1e2128', style: LineStyle.Solid },
      },
      width: chartContainerRef.current.clientWidth,
      height: 170,
      rightPriceScale: {
        borderColor: '#2a2f38',
        scaleMargins: { top: 0.1, bottom: 0.1 },
      },
      timeScale: {
        borderColor: '#2a2f38',
        timeVisible: true,
        secondsVisible: false,
      },
      crosshair: {
        vertLine: { color: '#2a3ded', width: 1, style: LineStyle.Dashed },
        horzLine: { color: '#2a3ded', width: 1, style: LineStyle.Dashed },
      },
      handleScale: false,
      handleScroll: false,
    })

    chartRef.current = chart

    // Add candlestick series
    const candleSeries = chart.addSeries(CandlestickSeries, {
      upColor: '#10b981',
      downColor: '#ef4444',
      borderUpColor: '#10b981',
      borderDownColor: '#ef4444',
      wickUpColor: '#10b981',
      wickDownColor: '#ef4444',
      priceLineVisible: false,
    })

    // Set OHLC data
    if (chartData?.status === 'ok' && chartData.candles?.length > 0) {
      const formattedCandles = chartData.candles.map(c => ({
        time: c.time as Time,
        open: c.open,
        high: c.high,
        low: c.low,
        close: c.close,
      }))
      candleSeries.setData(formattedCandles)
    }

    // Add entry price line if available
    if (entryPrice > 0) {
      candleSeries.createPriceLine({
        price: entryPrice,
        color: '#2a3ded',
        lineWidth: 1,
        lineStyle: LineStyle.Dashed,
        axisLabelVisible: true,
        title: 'Entry',
      })
    }

    // Fit content
    chart.timeScale().fitContent()

    // Handle resize
    const handleResize = () => {
      if (chartContainerRef.current) {
        chart.applyOptions({ width: chartContainerRef.current.clientWidth })
      }
    }

    window.addEventListener('resize', handleResize)

    return () => {
      window.removeEventListener('resize', handleResize)
      chart.remove()
    }
  }, [chartData, entryPrice, timeRange])

  const priceChange = currentPrice - entryPrice
  const priceChangePct = entryPrice > 0 ? (priceChange / entryPrice) * 100 : 0
  const isPriceUp = priceChange >= 0

  return (
    <div className="bg-[#1e2128] rounded-lg p-4 h-[282px] flex flex-col">
      {/* Header */}
      <div className="flex items-center justify-between mb-3">
        <div className="flex items-center gap-4">
          <div>
            <div className="text-xs text-[#6b7280] uppercase tracking-wider">Price</div>
            <div className="text-lg font-semibold text-white tabular-nums">
              {currentPrice.toFixed(6)} τ
            </div>
          </div>
          <div className={`text-sm tabular-nums ${isPriceUp ? 'text-green-400' : 'text-red-400'}`}>
            {isPriceUp ? '+' : ''}{priceChange.toFixed(6)} τ
            <span className="text-xs ml-1">({isPriceUp ? '+' : ''}{priceChangePct.toFixed(2)}%)</span>
          </div>
        </div>

        {/* Time range selector */}
        <div className="flex gap-1">
          {(['24h', '7d', '30d'] as TimeRange[]).map((range) => (
            <button
              key={range}
              onClick={() => setTimeRange(range)}
              className={`px-2 py-1 text-xs rounded transition-colors ${
                timeRange === range
                  ? 'bg-[#2a3ded] text-white'
                  : 'bg-[#0d0f12] text-[#8a8f98] hover:text-white'
              }`}
            >
              {range.toUpperCase()}
            </button>
          ))}
        </div>
      </div>

      {/* Chart */}
      <div ref={chartContainerRef} className="w-full relative flex-1 min-h-0">
        {isLoading && (
          <div className="absolute inset-0 flex items-center justify-center bg-[#1e2128]/80">
            <div className="text-sm text-[#8a8f98]">Loading chart...</div>
          </div>
        )}
      </div>

      {/* 24h Range */}
      {(high24h != null || low24h != null) && (
        <div className="mt-2 pt-2 border-t border-[#2a2f38]">
          <div className="flex items-center justify-between text-xs">
            <span className="text-[#6b7280]">24h Range</span>
            <div className="flex items-center gap-2">
              <span className="text-red-400 tabular-nums">{low24h?.toFixed(6) ?? '--'}</span>
              <div className="w-20 h-1.5 bg-[#0d0f12] rounded-full relative">
                {high24h != null && low24h != null && high24h > low24h && (
                  <div
                    className="absolute h-full bg-[#2a3ded] rounded-full"
                    style={{
                      left: '0%',
                      width: `${Math.min(100, Math.max(0, ((currentPrice - low24h) / (high24h - low24h)) * 100))}%`,
                    }}
                  />
                )}
              </div>
              <span className="text-green-400 tabular-nums">{high24h?.toFixed(6) ?? '--'}</span>
            </div>
          </div>
        </div>
      )}
    </div>
  )
}
