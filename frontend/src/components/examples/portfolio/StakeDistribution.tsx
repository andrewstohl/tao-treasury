import { useQuery } from '@tanstack/react-query'
import { PieChart, Pie, Cell, Tooltip, Legend, ResponsiveContainer } from 'recharts'
import ExampleWrapper from '../ExampleWrapper'
import { fetchFromProxy } from '../../../services/examplesApi'

const RAO = 1e9
const COLORS = [
  '#06b6d4', '#8b5cf6', '#f59e0b', '#10b981', '#ef4444',
  '#ec4899', '#6366f1', '#14b8a6', '#f97316', '#84cc16',
  '#a855f7', '#22d3ee', '#fb923c', '#4ade80', '#f43f5e',
]

export default function StakeDistribution() {
  const { data, isLoading, error } = useQuery({
    queryKey: ['examples', 'stake-distribution'],
    queryFn: () => fetchFromProxy('/api/dtao/stake_balance/latest/v1', { limit: 200 }),
    staleTime: 5 * 60 * 1000,
  })

  // Aggregate stake by subnet — balance_as_tao is TAO equivalent in RAO
  const bySubnet: Record<string, number> = {}
  for (const item of (data?.data || [])) {
    const netuid = item.netuid
    const taoValue = parseFloat(item.balance_as_tao || '0') / RAO
    if (taoValue > 0) {
      const key = `SN${netuid}`
      bySubnet[key] = (bySubnet[key] || 0) + taoValue
    }
  }

  const chartData = Object.entries(bySubnet)
    .map(([name, value]) => ({
      name,
      value: parseFloat(value.toFixed(4)),
    }))
    .sort((a, b) => b.value - a.value)

  const total = chartData.reduce((sum, d) => sum + d.value, 0)

  return (
    <ExampleWrapper
      title="Stake Distribution"
      description="Pie chart showing TAO stake value distribution across subnets."
      sourceNotebook="alpha pie charts.ipynb"
      isLoading={isLoading}
      error={error as Error}
    >
      {chartData.length === 0 ? (
        <p className="text-gray-500 text-sm">No stake data available.</p>
      ) : (
        <div className="flex flex-col lg:flex-row items-center gap-6">
          <ResponsiveContainer width="100%" height={400}>
            <PieChart>
              <Pie
                data={chartData}
                cx="50%"
                cy="50%"
                outerRadius={150}
                dataKey="value"
                label={({ name, percent }) => `${name} ${(percent * 100).toFixed(1)}%`}
                labelLine={{ stroke: '#6b7280' }}
              >
                {chartData.map((_, i) => (
                  <Cell key={i} fill={COLORS[i % COLORS.length]} />
                ))}
              </Pie>
              <Tooltip
                contentStyle={{ backgroundColor: '#1f2937', border: '1px solid #374151', borderRadius: 8 }}
                formatter={(value: number) => [`${value.toFixed(4)} τ`, 'Value']}
              />
              <Legend />
            </PieChart>
          </ResponsiveContainer>
          <div className="text-sm text-gray-400 space-y-1">
            <p>Total Staked: <span className="text-white font-mono">{total.toFixed(4)} τ</span></p>
            <p>Subnets: <span className="text-white font-mono">{chartData.length}</span></p>
          </div>
        </div>
      )}
    </ExampleWrapper>
  )
}
