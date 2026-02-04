import { useState } from 'react'
import { useQuery } from '@tanstack/react-query'
import { LineChart, Line, XAxis, YAxis, Tooltip, Legend, ResponsiveContainer } from 'recharts'
import ExampleWrapper from '../ExampleWrapper'
import { fetchFromProxy } from '../../../services/examplesApi'

const COLORS = [
  '#06b6d4', '#8b5cf6', '#f59e0b', '#10b981', '#ef4444',
]

export default function SubnetEmissions() {
  const [netuids, setNetuids] = useState('3,8,19')

  const netuidList = netuids.split(',').map((s) => parseInt(s.trim())).filter((n) => !isNaN(n)).slice(0, 5)

  const { data: results, isLoading, error } = useQuery({
    queryKey: ['examples', 'subnet-emissions', netuids],
    queryFn: async () => {
      const allData: Record<string, any[]> = {}
      for (const nid of netuidList) {
        const resp = await fetchFromProxy('/api/dtao/subnet_emission/v1', {
          netuid: nid,
          limit: 200,
        })
        allData[`SN${nid}`] = (resp.data || []).map((d: any) => ({
          date: (d.timestamp || d.date || '').split('T')[0],
          emission: parseFloat(d.emission || d.tao_in_percentage || d.tao_in || '0'),
        }))
      }
      return allData
    },
    enabled: netuidList.length > 0,
    staleTime: 5 * 60 * 1000,
  })

  const series = Object.keys(results || {})
  const allDates = new Set<string>()
  for (const key of series) {
    for (const pt of (results?.[key] || [])) {
      if (pt.date) allDates.add(pt.date)
    }
  }
  const sortedDates = Array.from(allDates).sort()

  const chartData = sortedDates.map((date) => {
    const row: any = { date }
    for (const key of series) {
      const match = (results?.[key] || []).find((p: any) => p.date === date)
      row[key] = match?.emission ?? null
    }
    return row
  })

  return (
    <ExampleWrapper
      title="Subnet Emissions"
      description="Emission rates over time for selected subnets."
      sourceNotebook="subnet_emissions_chart.ipynb"
      isLoading={isLoading}
      error={error as Error}
    >
      <div className="flex items-center gap-3 mb-4">
        <label className="text-xs text-gray-400">Subnets (comma-separated):</label>
        <input
          value={netuids}
          onChange={(e) => setNetuids(e.target.value)}
          className="w-48 px-2 py-1 bg-gray-700 border border-gray-600 rounded text-xs text-white"
          placeholder="3,8,19"
        />
      </div>

      {chartData.length === 0 ? (
        <p className="text-gray-500 text-sm">No emission data available.</p>
      ) : (
        <ResponsiveContainer width="100%" height={400}>
          <LineChart data={chartData}>
            <XAxis dataKey="date" tick={{ fontSize: 10, fill: '#9ca3af' }} />
            <YAxis tick={{ fontSize: 10, fill: '#9ca3af' }} />
            <Tooltip
              contentStyle={{ backgroundColor: '#1f2937', border: '1px solid #374151', borderRadius: 8 }}
              labelStyle={{ color: '#9ca3af' }}
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
