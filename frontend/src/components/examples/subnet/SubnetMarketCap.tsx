import { useState } from 'react'
import { useQuery } from '@tanstack/react-query'
import { LineChart, Line, XAxis, YAxis, Tooltip, Legend, ResponsiveContainer } from 'recharts'
import ExampleWrapper from '../ExampleWrapper'
import { fetchFromProxy } from '../../../services/examplesApi'

export default function SubnetMarketCap() {
  const [netuid, setNetuid] = useState(3)

  const endTs = Math.floor(Date.now() / 1000)
  const startTs = endTs - 30 * 86400

  const { data: poolData, isLoading: loadingPool, error } = useQuery({
    queryKey: ['examples', 'pool-history', netuid],
    queryFn: () => fetchFromProxy('/api/dtao/pool/history/v1', {
      netuid,
      timestamp_start: startTs,
      timestamp_end: endTs,
      limit: 500,
    }),
    staleTime: 5 * 60 * 1000,
  })

  const { data: priceData, isLoading: loadingPrice } = useQuery({
    queryKey: ['examples', 'price-history-mcap'],
    queryFn: () => fetchFromProxy('/api/price/history/v1', { limit: 60 }),
    staleTime: 5 * 60 * 1000,
  })

  const isLoading = loadingPool || loadingPrice

  // Build TAO price by date lookup
  const priceByDate: Record<string, number> = {}
  for (const p of (priceData?.data || [])) {
    const date = (p.timestamp || p.date || '').split('T')[0]
    priceByDate[date] = parseFloat(p.close || p.price || '0')
  }

  // Build chart data from pool history
  const chartData = (poolData?.data || [])
    .map((d: any) => {
      const date = (d.timestamp || d.date || '').split('T')[0]
      const taoInPool = parseFloat(d.tao_in || d.tao_reserve || '0')
      const alphaInPool = parseFloat(d.alpha_in || d.alpha_reserve || '0')
      const price = taoInPool > 0 && alphaInPool > 0 ? taoInPool / alphaInPool : 0
      const totalAlpha = parseFloat(d.alpha_out || d.total_alpha || '0') || alphaInPool
      const mcapTao = price * totalAlpha
      const taoPrice = priceByDate[date] || 0
      const mcapUsd = mcapTao * taoPrice
      return { date, mcapTao: parseFloat(mcapTao.toFixed(2)), mcapUsd: parseFloat(mcapUsd.toFixed(2)) }
    })
    .filter((d: any) => d.date)
    .sort((a: any, b: any) => a.date.localeCompare(b.date))

  return (
    <ExampleWrapper
      title="Subnet Market Cap Over Time"
      description="Tracks market cap of alpha tokens in TAO and USD for a subnet."
      sourceNotebook="subnet market cap over time.ipynb"
      isLoading={isLoading}
      error={error as Error}
    >
      <div className="flex items-center gap-3 mb-4">
        <label className="text-xs text-[#6f87a0]">Subnet:</label>
        <input
          type="number"
          value={netuid}
          onChange={(e) => setNetuid(parseInt(e.target.value) || 1)}
          className="w-20 px-2 py-1 bg-[#1a2d42] border border-[#2a4a66] rounded text-xs text-white"
          min={1}
        />
      </div>

      {chartData.length === 0 ? (
        <p className="text-[#5a7a94] text-sm">No pool history available for SN{netuid}.</p>
      ) : (
        <ResponsiveContainer width="100%" height={400}>
          <LineChart data={chartData}>
            <XAxis dataKey="date" tick={{ fontSize: 10, fill: '#9ca3af' }} />
            <YAxis yAxisId="tao" tick={{ fontSize: 10, fill: '#06b6d4' }} />
            <YAxis yAxisId="usd" orientation="right" tick={{ fontSize: 10, fill: '#f59e0b' }} />
            <Tooltip
              contentStyle={{ backgroundColor: '#1f2937', border: '1px solid #374151', borderRadius: 8 }}
              labelStyle={{ color: '#9ca3af' }}
            />
            <Legend />
            <Line yAxisId="tao" type="monotone" dataKey="mcapTao" stroke="#06b6d4" strokeWidth={2} dot={false} name="Market Cap (τ)" />
            <Line yAxisId="usd" type="monotone" dataKey="mcapUsd" stroke="#f59e0b" strokeWidth={2} dot={false} name="Market Cap ($)" />
          </LineChart>
        </ResponsiveContainer>
      )}
    </ExampleWrapper>
  )
}
