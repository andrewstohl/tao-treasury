import { useState } from 'react'
import { useQuery } from '@tanstack/react-query'
import { BarChart, Bar, XAxis, YAxis, Tooltip, ResponsiveContainer } from 'recharts'
import ExampleWrapper from '../ExampleWrapper'
import { fetchFromProxy } from '../../../services/examplesApi'

const RAO = 1e9

export default function StakeEarnings() {
  const [days, setDays] = useState(30)

  const endDate = new Date().toISOString().split('T')[0]
  const startDate = new Date(Date.now() - days * 86400000).toISOString().split('T')[0]

  const { data: histData, isLoading: loadingHist, error } = useQuery({
    queryKey: ['examples', 'account-history-earnings', days],
    queryFn: () => fetchFromProxy('/api/account/history/v1', {
      date_start: startDate,
      date_end: endDate,
      limit: 500,
    }),
    staleTime: 5 * 60 * 1000,
  })

  const isLoading = loadingHist

  // Compute daily earnings from day-over-day staked balance changes
  // API fields: balance_staked (RAO), timestamp
  const balances = (histData?.data || [])
    .map((d: any) => ({
      date: d.timestamp?.split('T')[0] || d.date,
      staked: parseFloat(d.balance_staked || '0') / RAO,
    }))
    .sort((a: any, b: any) => a.date?.localeCompare(b.date))

  // Day-over-day staked change = yield + delegation net
  // Without separate delegation filtering, this shows total balance change per day
  const earningsData = balances.slice(1).map((day: any, i: number) => {
    const prev = balances[i]
    const change = day.staked - prev.staked
    return {
      date: day.date,
      change: parseFloat(change.toFixed(6)),
    }
  })

  const totalChange = earningsData.reduce((sum: number, d: any) => sum + d.change, 0)

  return (
    <ExampleWrapper
      title="Stake Earnings"
      description="Daily staked balance changes. Positive = yield + new stakes. Negative = unstakes or price movement."
      sourceNotebook="delegation_stake_earnings.py"
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

      <div className="mb-4 text-sm">
        <span className="text-[#6f87a0]">Net Change ({days}d): </span>
        <span className={`tabular-nums font-semibold ${totalChange >= 0 ? 'text-green-400' : 'text-red-400'}`}>
          {totalChange >= 0 ? '+' : ''}{totalChange.toFixed(4)} τ
        </span>
      </div>

      {earningsData.length === 0 ? (
        <p className="text-[#5a7a94] text-sm">No earnings data available.</p>
      ) : (
        <>
          <ResponsiveContainer width="100%" height={300}>
            <BarChart data={earningsData}>
              <XAxis dataKey="date" tick={{ fontSize: 10, fill: '#9ca3af' }} />
              <YAxis tick={{ fontSize: 10, fill: '#9ca3af' }} />
              <Tooltip
                contentStyle={{ backgroundColor: '#1f2937', border: '1px solid #374151', borderRadius: 8 }}
                labelStyle={{ color: '#9ca3af' }}
                formatter={(value: number) => [`${value.toFixed(4)} τ`]}
              />
              <Bar
                dataKey="change"
                fill="#06b6d4"
                radius={[2, 2, 0, 0]}
              />
            </BarChart>
          </ResponsiveContainer>

          <div className="mt-4 overflow-x-auto">
            <table className="w-full text-xs">
              <thead>
                <tr className="border-b border-[#1e3a5f]">
                  <th className="text-left py-1 px-2 text-[#5a7a94]">Date</th>
                  <th className="text-right py-1 px-2 text-[#5a7a94]">Staked Balance (τ)</th>
                  <th className="text-right py-1 px-2 text-[#5a7a94]">Daily Change</th>
                </tr>
              </thead>
              <tbody>
                {earningsData.slice(-10).reverse().map((d: any) => {
                  const balIdx = balances.findIndex((b: any) => b.date === d.date)
                  const bal = balIdx >= 0 ? balances[balIdx].staked : 0
                  return (
                    <tr key={d.date} className="border-b border-[#132436]">
                      <td className="py-1 px-2 text-[#6f87a0] tabular-nums">{d.date}</td>
                      <td className="py-1 px-2 text-right tabular-nums text-[#8faabe]">{bal.toFixed(4)}</td>
                      <td className={`py-1 px-2 text-right tabular-nums ${d.change >= 0 ? 'text-green-400' : 'text-red-400'}`}>
                        {d.change >= 0 ? '+' : ''}{d.change.toFixed(4)}
                      </td>
                    </tr>
                  )
                })}
              </tbody>
            </table>
          </div>
        </>
      )}
    </ExampleWrapper>
  )
}
