import { useState } from 'react'
import { useQuery } from '@tanstack/react-query'
import { AreaChart, Area, XAxis, YAxis, Tooltip, Legend, ResponsiveContainer } from 'recharts'
import ExampleWrapper from '../ExampleWrapper'
import { fetchFromProxy } from '../../../services/examplesApi'

const RAO = 1e9

export default function AccountBalanceHistory() {
  const [days, setDays] = useState(30)

  const endDate = new Date().toISOString().split('T')[0]
  const startDate = new Date(Date.now() - days * 86400000).toISOString().split('T')[0]

  const { data, isLoading, error } = useQuery({
    queryKey: ['examples', 'account-history', days],
    queryFn: () => fetchFromProxy('/api/account/history/v1', {
      date_start: startDate,
      date_end: endDate,
      limit: 500,
    }),
    staleTime: 5 * 60 * 1000,
  })

  // API fields: balance_total, balance_staked, balance_free — all in RAO
  const chartData = (data?.data || [])
    .map((d: any) => ({
      date: d.timestamp?.split('T')[0] || d.date,
      balance: parseFloat(d.balance_total || '0') / RAO,
      staked: parseFloat(d.balance_staked || '0') / RAO,
      free: parseFloat(d.balance_free || '0') / RAO,
    }))
    .sort((a: any, b: any) => a.date?.localeCompare(b.date))

  return (
    <ExampleWrapper
      title="Account Balance History"
      description="Daily account balance history showing total balance, staked, and free TAO."
      sourceNotebook="balances.py"
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
        <p className="text-[#5a7a94] text-sm">No balance history available.</p>
      ) : (
        <ResponsiveContainer width="100%" height={400}>
          <AreaChart data={chartData}>
            <XAxis dataKey="date" tick={{ fontSize: 10, fill: '#9ca3af' }} />
            <YAxis tick={{ fontSize: 10, fill: '#9ca3af' }} tickFormatter={(v) => `${v.toFixed(1)}`} />
            <Tooltip
              contentStyle={{ backgroundColor: '#1f2937', border: '1px solid #374151', borderRadius: 8 }}
              labelStyle={{ color: '#9ca3af' }}
              formatter={(value: number) => [`${value.toFixed(4)} τ`]}
            />
            <Legend />
            <Area
              type="monotone"
              dataKey="balance"
              stroke="#06b6d4"
              fill="#06b6d4"
              fillOpacity={0.15}
              strokeWidth={2}
              name="Total Balance"
            />
            <Area
              type="monotone"
              dataKey="staked"
              stroke="#8b5cf6"
              fill="#8b5cf6"
              fillOpacity={0.1}
              strokeWidth={1.5}
              name="Staked"
            />
            <Area
              type="monotone"
              dataKey="free"
              stroke="#10b981"
              fill="#10b981"
              fillOpacity={0.1}
              strokeWidth={1.5}
              name="Free"
            />
          </AreaChart>
        </ResponsiveContainer>
      )}
    </ExampleWrapper>
  )
}
