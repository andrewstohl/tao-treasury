import { useState } from 'react'
import { useQuery } from '@tanstack/react-query'
import { LineChart, Line, XAxis, YAxis, Tooltip, Legend, ResponsiveContainer } from 'recharts'
import ExampleWrapper from '../ExampleWrapper'
import { fetchFromProxy } from '../../../services/examplesApi'

const RAO = 1e9
const COLORS = [
  '#06b6d4', '#8b5cf6', '#f59e0b', '#10b981', '#ef4444',
  '#ec4899', '#6366f1', '#14b8a6', '#f97316', '#84cc16',
]

export default function StakeBalanceHistory() {
  const [days, setDays] = useState(30)

  const { data: stakeData, isLoading: loadingStakes, error } = useQuery({
    queryKey: ['examples', 'stake-balance-latest'],
    queryFn: () => fetchFromProxy('/api/dtao/stake_balance/latest/v1', { limit: 200 }),
    staleTime: 5 * 60 * 1000,
  })

  const positions = (stakeData?.data || [])
    .filter((d: any) => parseFloat(d.balance || '0') > 0)
    .slice(0, 8)

  const { data: historyResults, isLoading: loadingHistory } = useQuery({
    queryKey: ['examples', 'stake-history', days, positions.map((p: any) => `${p.hotkey?.ss58}-${p.netuid}`).join(',')],
    queryFn: async () => {
      const results: Record<string, any[]> = {}
      for (const pos of positions) {
        const resp = await fetchFromProxy('/api/dtao/stake_balance/history/v1', {
          coldkey: pos.coldkey?.ss58 || pos.coldkey,
          hotkey: pos.hotkey?.ss58 || pos.hotkey,
          netuid: pos.netuid,
          limit: days,
        })
        const name = pos.hotkey_name ? `SN${pos.netuid} (${pos.hotkey_name})` : `SN${pos.netuid}`
        results[name] = (resp.data || []).map((d: any) => ({
          date: d.timestamp?.split('T')[0] || d.date,
          tao: parseFloat(d.balance_as_tao || '0') / RAO,
        })).sort((a: any, b: any) => a.date?.localeCompare(b.date))
      }
      return results
    },
    enabled: positions.length > 0,
    staleTime: 5 * 60 * 1000,
  })

  const isLoading = loadingStakes || loadingHistory
  const series = Object.keys(historyResults || {})

  const allDates = new Set<string>()
  for (const key of series) {
    for (const pt of (historyResults?.[key] || [])) {
      if (pt.date) allDates.add(pt.date)
    }
  }
  const sortedDates = Array.from(allDates).sort()

  const chartData = sortedDates.map((date) => {
    const row: any = { date }
    for (const key of series) {
      const match = (historyResults?.[key] || []).find((p: any) => p.date === date)
      row[key] = match?.tao ?? null
    }
    return row
  })

  return (
    <ExampleWrapper
      title="Stake Balance History"
      description="Historical stake balance (TAO equivalent) per validator/subnet over time."
      sourceNotebook="coldkey stake balances.ipynb"
      isLoading={isLoading}
      error={error as Error}
    >
      <div className="flex gap-2 mb-4">
        {[7, 14, 30, 60, 90].map((d) => (
          <button
            key={d}
            onClick={() => setDays(d)}
            className={`px-3 py-1 rounded text-xs ${
              days === d ? 'bg-tao-600 text-white' : 'bg-[#1a2d42] text-[#6f87a0] hover:bg-[#243a52]'
            }`}
          >
            {d}d
          </button>
        ))}
      </div>
      {chartData.length === 0 ? (
        <p className="text-[#5a7a94] text-sm">No history data available.</p>
      ) : (
        <ResponsiveContainer width="100%" height={400}>
          <LineChart data={chartData}>
            <XAxis dataKey="date" tick={{ fontSize: 10, fill: '#9ca3af' }} />
            <YAxis tick={{ fontSize: 10, fill: '#9ca3af' }} tickFormatter={(v) => `${v.toFixed(1)}`} />
            <Tooltip
              contentStyle={{ backgroundColor: '#1f2937', border: '1px solid #374151', borderRadius: 8 }}
              labelStyle={{ color: '#9ca3af' }}
              formatter={(value: number) => [`${value.toFixed(4)} τ`]}
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
