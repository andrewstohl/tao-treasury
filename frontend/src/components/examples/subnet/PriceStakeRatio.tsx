import { useQuery } from '@tanstack/react-query'
import { LineChart, Line, XAxis, YAxis, Tooltip, Legend, ResponsiveContainer } from 'recharts'
import ExampleWrapper from '../ExampleWrapper'
import { fetchFromProxy } from '../../../services/examplesApi'

export default function PriceStakeRatio() {
  const { data: statsData, isLoading: loadingStats, error } = useQuery({
    queryKey: ['examples', 'stats-history'],
    queryFn: () => fetchFromProxy('/api/stats/history/v1', { limit: 200 }),
    staleTime: 5 * 60 * 1000,
  })

  const { data: priceData, isLoading: loadingPrice } = useQuery({
    queryKey: ['examples', 'pool-total-price'],
    queryFn: () => fetchFromProxy('/api/dtao/pool/total_price/v1', { limit: 200 }),
    staleTime: 5 * 60 * 1000,
  })

  const isLoading = loadingStats || loadingPrice

  // Build stats by date: staked percentage
  const statsByDate: Record<string, number> = {}
  for (const s of (statsData?.data || [])) {
    const date = (s.timestamp || s.date || '').split('T')[0]
    const staked = parseFloat(s.total_stake || s.staked_percentage || '0')
    const total = parseFloat(s.total_issuance || s.circulating_supply || '1')
    const pct = total > 0 ? (staked / total) * 100 : staked
    if (date) statsByDate[date] = pct
  }

  // Build price by date
  const priceByDate: Record<string, number> = {}
  for (const p of (priceData?.data || [])) {
    const date = (p.timestamp || p.date || '').split('T')[0]
    const price = parseFloat(p.total_price || p.price || '0')
    if (date) priceByDate[date] = price
  }

  // Merge
  const allDates = new Set([...Object.keys(statsByDate), ...Object.keys(priceByDate)])
  const chartData = Array.from(allDates)
    .sort()
    .map((date) => ({
      date,
      stakePct: statsByDate[date] ?? null,
      totalPrice: priceByDate[date] ?? null,
    }))
    .filter((d) => d.stakePct !== null || d.totalPrice !== null)

  return (
    <ExampleWrapper
      title="Price:Stake Ratio"
      description="Relationship between percentage of TAO staked and total subnet prices over time."
      sourceNotebook="twitter SN price:stake ratio.ipynb"
      isLoading={isLoading}
      error={error as Error}
    >
      {chartData.length === 0 ? (
        <p className="text-[#5a7a94] text-sm">No stats/price data available.</p>
      ) : (
        <ResponsiveContainer width="100%" height={400}>
          <LineChart data={chartData}>
            <XAxis dataKey="date" tick={{ fontSize: 10, fill: '#9ca3af' }} />
            <YAxis yAxisId="stake" tick={{ fontSize: 10, fill: '#06b6d4' }} label={{ value: 'Stake %', angle: -90, position: 'insideLeft', style: { fill: '#06b6d4', fontSize: 10 } }} />
            <YAxis yAxisId="price" orientation="right" tick={{ fontSize: 10, fill: '#f59e0b' }} label={{ value: 'Total Price', angle: 90, position: 'insideRight', style: { fill: '#f59e0b', fontSize: 10 } }} />
            <Tooltip
              contentStyle={{ backgroundColor: '#1f2937', border: '1px solid #374151', borderRadius: 8 }}
              labelStyle={{ color: '#9ca3af' }}
            />
            <Legend />
            <Line yAxisId="stake" type="monotone" dataKey="stakePct" stroke="#06b6d4" strokeWidth={2} dot={false} connectNulls name="Staked %" />
            <Line yAxisId="price" type="monotone" dataKey="totalPrice" stroke="#f59e0b" strokeWidth={2} dot={false} connectNulls name="Total Price (τ)" />
          </LineChart>
        </ResponsiveContainer>
      )}
    </ExampleWrapper>
  )
}
