import { useQuery } from '@tanstack/react-query'
import { BarChart, Bar, XAxis, YAxis, Tooltip, ResponsiveContainer, ReferenceLine } from 'recharts'
import ExampleWrapper from '../ExampleWrapper'
import { fetchFromProxy } from '../../../services/examplesApi'

export default function DailyRecycleHalvening() {
  const { data: statsData, isLoading: loadingStats, error } = useQuery({
    queryKey: ['examples', 'stats-latest'],
    queryFn: () => fetchFromProxy('/api/stats/latest/v1', {}),
    staleTime: 5 * 60 * 1000,
  })

  const { data: subnetHistory, isLoading: loadingSubnets } = useQuery({
    queryKey: ['examples', 'subnet-history-recycle'],
    queryFn: () => fetchFromProxy('/api/subnet/history/v1', { limit: 500 }),
    staleTime: 5 * 60 * 1000,
  })

  const isLoading = loadingStats || loadingSubnets

  // Aggregate daily recycled TAO from subnet history
  const recycleByDate: Record<string, number> = {}
  for (const item of (subnetHistory?.data || [])) {
    const date = (item.timestamp || item.date || '').split('T')[0]
    const recycled = parseFloat(item.recycled || item.burn || item.recycle_amount || '0')
    if (date && recycled > 0) {
      recycleByDate[date] = (recycleByDate[date] || 0) + recycled
    }
  }

  const chartData = Object.entries(recycleByDate)
    .map(([date, recycled]) => ({ date, recycled: parseFloat(recycled.toFixed(4)) }))
    .sort((a, b) => a.date.localeCompare(b.date))

  // Stats for halvening projection
  const stats = statsData?.data?.[0] || statsData?.data || {}
  const totalIssuance = parseFloat(stats.total_issuance || stats.circulating_supply || '0')
  const dailyEmission = parseFloat(stats.daily_emission || stats.emission || '0')
  const totalSupply = 21_000_000
  const remaining = totalSupply - totalIssuance
  const daysToHalving = dailyEmission > 0 ? remaining / dailyEmission : 0
  const halvingDate = daysToHalving > 0
    ? new Date(Date.now() + daysToHalving * 86400000).toISOString().split('T')[0]
    : 'N/A'

  const avgDailyRecycle = chartData.length > 0
    ? chartData.reduce((s, d) => s + d.recycled, 0) / chartData.length
    : 0

  return (
    <ExampleWrapper
      title="Daily Recycle / Halvening"
      description="Daily TAO recycled/burned across subnets with halvening date projection."
      sourceNotebook="dailyrecycle_halvening.ipynb"
      isLoading={isLoading}
      error={error as Error}
    >
      <div className="grid grid-cols-2 md:grid-cols-4 gap-4 mb-4 text-sm">
        <div>
          <span className="text-[#5a7a94]">Total Issuance</span>
          <p className="tabular-nums text-white">{totalIssuance > 0 ? totalIssuance.toLocaleString() : 'N/A'} τ</p>
        </div>
        <div>
          <span className="text-[#5a7a94]">Daily Emission</span>
          <p className="tabular-nums text-white">{dailyEmission > 0 ? dailyEmission.toFixed(2) : 'N/A'} τ</p>
        </div>
        <div>
          <span className="text-[#5a7a94]">Avg Daily Recycle</span>
          <p className="tabular-nums text-yellow-400">{avgDailyRecycle.toFixed(2)} τ</p>
        </div>
        <div>
          <span className="text-[#5a7a94]">Est. Halving Date</span>
          <p className="tabular-nums text-tao-400">{halvingDate}</p>
        </div>
      </div>

      {chartData.length === 0 ? (
        <p className="text-[#5a7a94] text-sm">No recycle data available. This endpoint may require subnet history data.</p>
      ) : (
        <ResponsiveContainer width="100%" height={400}>
          <BarChart data={chartData}>
            <XAxis dataKey="date" tick={{ fontSize: 10, fill: '#9ca3af' }} />
            <YAxis tick={{ fontSize: 10, fill: '#9ca3af' }} />
            <Tooltip
              contentStyle={{ backgroundColor: '#1f2937', border: '1px solid #374151', borderRadius: 8 }}
              labelStyle={{ color: '#9ca3af' }}
              formatter={(value: number) => [`${value.toFixed(4)} τ`, 'Recycled']}
            />
            {avgDailyRecycle > 0 && (
              <ReferenceLine
                y={avgDailyRecycle}
                stroke="#f59e0b"
                strokeDasharray="4 2"
                label={{ value: 'Avg', position: 'right', fill: '#f59e0b', fontSize: 10 }}
              />
            )}
            <Bar dataKey="recycled" fill="#8b5cf6" radius={[2, 2, 0, 0]} name="TAO Recycled" />
          </BarChart>
        </ResponsiveContainer>
      )}
    </ExampleWrapper>
  )
}
