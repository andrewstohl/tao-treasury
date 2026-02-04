import { useQuery } from '@tanstack/react-query'
import { LineChart, Line, XAxis, YAxis, Tooltip, Legend, ResponsiveContainer } from 'recharts'
import ExampleWrapper from '../ExampleWrapper'
import { fetchFromProxy } from '../../../services/examplesApi'

const RAO = 1e9
const COLORS = [
  '#06b6d4', '#8b5cf6', '#f59e0b', '#10b981', '#ef4444',
  '#ec4899', '#6366f1', '#14b8a6', '#f97316', '#84cc16',
]

export default function AlphaGrowthOverTime() {
  const { data: stakeData, isLoading: loadingStakes, error: stakeError } = useQuery({
    queryKey: ['examples', 'stake-balance-latest'],
    queryFn: () => fetchFromProxy('/api/dtao/stake_balance/latest/v1', { limit: 200 }),
    staleTime: 5 * 60 * 1000,
  })

  // Get unique hotkey+netuid combos from latest balances (balance is alpha in RAO)
  const positions = (stakeData?.data || [])
    .filter((d: any) => parseFloat(d.balance || '0') > 0)
    .slice(0, 10)

  const { data: historyResults, isLoading: loadingHistory } = useQuery({
    queryKey: ['examples', 'alpha-growth-history', positions.map((p: any) => `${p.hotkey?.ss58}-${p.netuid}`).join(',')],
    queryFn: async () => {
      const results: Record<string, any[]> = {}
      for (const pos of positions) {
        const resp = await fetchFromProxy('/api/dtao/stake_balance/history/v1', {
          coldkey: pos.coldkey?.ss58 || pos.coldkey,
          hotkey: pos.hotkey?.ss58 || pos.hotkey,
          netuid: pos.netuid,
          limit: 90,
        })
        const name = pos.hotkey_name ? `SN${pos.netuid} (${pos.hotkey_name})` : `SN${pos.netuid}`
        results[name] = (resp.data || []).map((d: any) => ({
          date: d.timestamp?.split('T')[0] || d.date,
          alpha: parseFloat(d.balance || '0') / RAO,
        })).sort((a: any, b: any) => a.date?.localeCompare(b.date))
      }
      return results
    },
    enabled: positions.length > 0,
    staleTime: 5 * 60 * 1000,
  })

  const isLoading = loadingStakes || loadingHistory

  // Merge all series into a unified timeline
  const allDates = new Set<string>()
  const series = Object.keys(historyResults || {})
  for (const key of series) {
    for (const pt of (historyResults?.[key] || [])) {
      if (pt.date) allDates.add(pt.date)
    }
  }
  const sortedDates = Array.from(allDates).sort()

  const chartData = sortedDates.map((date) => {
    const row: any = { date }
    for (const key of series) {
      const pts = historyResults?.[key] || []
      const match = pts.find((p: any) => p.date === date)
      row[key] = match?.alpha ?? null
    }
    return row
  })

  return (
    <ExampleWrapper
      title="Alpha Growth Over Time"
      description="Tracks how alpha stake grows over time across validators and subnets."
      sourceNotebook="alpha growth over time.ipynb"
      isLoading={isLoading}
      error={stakeError as Error}
    >
      {chartData.length === 0 ? (
        <p className="text-gray-500 text-sm">No history data available.</p>
      ) : (
        <ResponsiveContainer width="100%" height={400}>
          <LineChart data={chartData}>
            <XAxis dataKey="date" tick={{ fontSize: 10, fill: '#9ca3af' }} />
            <YAxis tick={{ fontSize: 10, fill: '#9ca3af' }} tickFormatter={(v) => v.toLocaleString()} />
            <Tooltip
              contentStyle={{ backgroundColor: '#1f2937', border: '1px solid #374151', borderRadius: 8 }}
              labelStyle={{ color: '#9ca3af' }}
              formatter={(value: number) => [`${value.toFixed(2)} α`]}
            />
            <Legend />
            {series.map((key, i) => (
              <Line
                key={key}
                type="monotone"
                dataKey={key}
                stroke={COLORS[i % COLORS.length]}
                strokeWidth={2}
                dot={false}
                connectNulls
              />
            ))}
          </LineChart>
        </ResponsiveContainer>
      )}
    </ExampleWrapper>
  )
}
