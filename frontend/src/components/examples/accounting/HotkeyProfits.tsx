import { useQuery } from '@tanstack/react-query'
import { LineChart, Line, XAxis, YAxis, Tooltip, Legend, ResponsiveContainer } from 'recharts'
import ExampleWrapper from '../ExampleWrapper'
import { fetchFromProxy } from '../../../services/examplesApi'

export default function HotkeyProfits() {
  const endDate = new Date(Date.now() + 86400000).toISOString().split('T')[0]
  const startDate = new Date(Date.now() - 90 * 86400000).toISOString().split('T')[0]

  const { data: acctData, isLoading: loadingAcct, error } = useQuery({
    queryKey: ['examples', 'accounting-records'],
    queryFn: () => fetchFromProxy('/api/accounting/tax/v1', {
      token: 'TAO',
      date_start: startDate,
      date_end: endDate,
      limit: 500,
    }),
    staleTime: 5 * 60 * 1000,
  })

  const records = acctData?.data || []

  // Aggregate daily income vs expenses
  const dailyMap: Record<string, { income: number; expense: number }> = {}

  for (const rec of records) {
    const date = (rec.timestamp || rec.date || '').split('T')[0]
    if (!date) continue
    if (!dailyMap[date]) dailyMap[date] = { income: 0, expense: 0 }

    const credit = parseFloat(rec.credit_amount || '0')
    const debit = parseFloat(rec.debit_amount || '0')
    const txType = rec.transaction_type || ''

    if (txType === 'daily_income' || txType === 'transfer_in') {
      dailyMap[date].income += credit
    } else if (txType === 'token_swap' && credit > 0) {
      dailyMap[date].income += credit
    } else if (txType === 'token_swap' && debit > 0) {
      dailyMap[date].expense += debit
    } else if (debit > 0) {
      dailyMap[date].expense += debit
    }
  }

  const chartData = Object.entries(dailyMap)
    .map(([date, vals]) => ({
      date,
      income: parseFloat(vals.income.toFixed(4)),
      expense: parseFloat(vals.expense.toFixed(4)),
      net: parseFloat((vals.income - vals.expense).toFixed(4)),
    }))
    .sort((a, b) => a.date.localeCompare(b.date))

  const totalIncome = chartData.reduce((s, d) => s + d.income, 0)
  const totalExpense = chartData.reduce((s, d) => s + d.expense, 0)
  const netProfit = totalIncome - totalExpense

  return (
    <ExampleWrapper
      title="Hotkey Profits"
      description="Daily income vs expenses from accounting records. Shows net profit over time."
      sourceNotebook="hotkey profits v2.ipynb"
      isLoading={loadingAcct}
      error={error as Error}
    >
      <div className="grid grid-cols-3 gap-4 mb-4 text-sm">
        <div>
          <span className="text-gray-500">Total Income</span>
          <p className="tabular-nums text-green-400">{totalIncome.toFixed(4)} τ</p>
        </div>
        <div>
          <span className="text-gray-500">Total Expense</span>
          <p className="tabular-nums text-red-400">{totalExpense.toFixed(4)} τ</p>
        </div>
        <div>
          <span className="text-gray-500">Net Profit</span>
          <p className={`tabular-nums ${netProfit >= 0 ? 'text-green-400' : 'text-red-400'}`}>
            {netProfit >= 0 ? '+' : ''}{netProfit.toFixed(4)} τ
          </p>
        </div>
      </div>

      {chartData.length === 0 ? (
        <p className="text-gray-500 text-sm">No accounting data available.</p>
      ) : (
        <ResponsiveContainer width="100%" height={350}>
          <LineChart data={chartData}>
            <XAxis dataKey="date" tick={{ fontSize: 10, fill: '#9ca3af' }} />
            <YAxis tick={{ fontSize: 10, fill: '#9ca3af' }} />
            <Tooltip
              contentStyle={{ backgroundColor: '#1f2937', border: '1px solid #374151', borderRadius: 8 }}
              labelStyle={{ color: '#9ca3af' }}
              formatter={(value: number) => [`${value.toFixed(4)} τ`]}
            />
            <Legend />
            <Line type="monotone" dataKey="income" stroke="#10b981" strokeWidth={2} dot={false} name="Income" />
            <Line type="monotone" dataKey="expense" stroke="#ef4444" strokeWidth={2} dot={false} name="Expense" />
            <Line type="monotone" dataKey="net" stroke="#06b6d4" strokeWidth={2} dot={false} name="Net" strokeDasharray="4 2" />
          </LineChart>
        </ResponsiveContainer>
      )}
    </ExampleWrapper>
  )
}
