import { useState } from 'react'
import { useQuery } from '@tanstack/react-query'
import { BarChart, Bar, XAxis, YAxis, Tooltip, ResponsiveContainer } from 'recharts'
import ExampleWrapper from '../ExampleWrapper'
import { fetchFromProxy } from '../../../services/examplesApi'

export default function DailyAlphaBurns() {
  const [netuid, setNetuid] = useState(3)

  const { data, isLoading, error } = useQuery({
    queryKey: ['examples', 'burned-alpha', netuid],
    queryFn: () => fetchFromProxy('/api/dtao/burned_alpha/v1', {
      netuid,
      limit: 90,
    }),
    staleTime: 5 * 60 * 1000,
  })

  // Aggregate burns by date
  const burnsByDate: Record<string, number> = {}
  for (const item of (data?.data || [])) {
    const date = (item.timestamp || item.date || '').split('T')[0]
    const burned = parseFloat(item.burned_alpha || item.amount || '0')
    if (date) {
      burnsByDate[date] = (burnsByDate[date] || 0) + burned
    }
  }

  const chartData = Object.entries(burnsByDate)
    .map(([date, burned]) => ({ date, burned: parseFloat(burned.toFixed(4)) }))
    .sort((a, b) => a.date.localeCompare(b.date))

  const totalBurned = chartData.reduce((s, d) => s + d.burned, 0)

  return (
    <ExampleWrapper
      title="Daily Alpha Burns"
      description="Daily alpha burn amounts for a selected subnet."
      sourceNotebook="subnet burns per day.ipynb"
      isLoading={isLoading}
      error={error as Error}
    >
      <div className="flex items-center gap-3 mb-4">
        <label className="text-xs text-gray-400">Subnet:</label>
        <input
          type="number"
          value={netuid}
          onChange={(e) => setNetuid(parseInt(e.target.value) || 1)}
          className="w-20 px-2 py-1 bg-gray-700 border border-gray-600 rounded text-xs text-white"
          min={1}
        />
        <span className="text-xs text-gray-500 ml-2">
          Total Burned: <span className="text-white font-mono">{totalBurned.toFixed(4)} α</span>
        </span>
      </div>

      {chartData.length === 0 ? (
        <p className="text-gray-500 text-sm">No burn data available for SN{netuid}.</p>
      ) : (
        <ResponsiveContainer width="100%" height={400}>
          <BarChart data={chartData}>
            <XAxis dataKey="date" tick={{ fontSize: 10, fill: '#9ca3af' }} />
            <YAxis tick={{ fontSize: 10, fill: '#9ca3af' }} />
            <Tooltip
              contentStyle={{ backgroundColor: '#1f2937', border: '1px solid #374151', borderRadius: 8 }}
              labelStyle={{ color: '#9ca3af' }}
              formatter={(value: number) => [`${value.toFixed(4)} α`, 'Burned']}
            />
            <Bar dataKey="burned" fill="#ef4444" radius={[2, 2, 0, 0]} name="Alpha Burned" />
          </BarChart>
        </ResponsiveContainer>
      )}
    </ExampleWrapper>
  )
}
