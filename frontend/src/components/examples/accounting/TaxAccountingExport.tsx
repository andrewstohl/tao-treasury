import { useQuery } from '@tanstack/react-query'
import ExampleWrapper from '../ExampleWrapper'
import { fetchFromProxy } from '../../../services/examplesApi'

export default function TaxAccountingExport() {
  const endDate = new Date(Date.now() + 86400000).toISOString().split('T')[0]
  const startDate = new Date(Date.now() - 364 * 86400000).toISOString().split('T')[0]

  const { data, isLoading, error } = useQuery({
    queryKey: ['examples', 'tax-accounting'],
    queryFn: () => fetchFromProxy('/api/accounting/tax/v1', {
      token: 'TAO',
      date_start: startDate,
      date_end: endDate,
      limit: 500,
    }),
    staleTime: 5 * 60 * 1000,
  })

  const records = data?.data || []

  const downloadCsv = () => {
    if (records.length === 0) return
    const headers = Object.keys(records[0])
    const rows = records.map((r: any) => headers.map((h) => JSON.stringify(r[h] ?? '')).join(','))
    const csv = [headers.join(','), ...rows].join('\n')
    const blob = new Blob([csv], { type: 'text/csv' })
    const url = URL.createObjectURL(blob)
    const a = document.createElement('a')
    a.href = url
    a.download = 'tao_accounting_export.csv'
    a.click()
    URL.revokeObjectURL(url)
  }

  return (
    <ExampleWrapper
      title="Tax Accounting Export"
      description="Complete accounting/tax records for your wallet with CSV export."
      sourceNotebook="accounting-v2.ipynb"
      isLoading={isLoading}
      error={error as Error}
    >
      <div className="flex items-center justify-between mb-4">
        <span className="text-sm text-[#6f87a0]">{records.length} records found</span>
        <button
          onClick={downloadCsv}
          disabled={records.length === 0}
          className="px-3 py-1.5 bg-tao-600 hover:bg-tao-500 text-white text-xs rounded disabled:opacity-50"
        >
          Download CSV
        </button>
      </div>

      {records.length === 0 ? (
        <p className="text-[#5a7a94] text-sm">No accounting records found.</p>
      ) : (
        <div className="overflow-x-auto max-h-[500px] overflow-y-auto">
          <table className="w-full text-xs">
            <thead className="sticky top-0 bg-[#121f2d]">
              <tr className="border-b border-[#1e3a5f]">
                <th className="text-left py-1.5 px-2 text-[#5a7a94]">Date</th>
                <th className="text-left py-1.5 px-2 text-[#5a7a94]">Type</th>
                <th className="text-left py-1.5 px-2 text-[#5a7a94]">Info</th>
                <th className="text-right py-1.5 px-2 text-[#5a7a94]">Debit</th>
                <th className="text-right py-1.5 px-2 text-[#5a7a94]">Credit</th>
                <th className="text-right py-1.5 px-2 text-[#5a7a94]">Fee</th>
              </tr>
            </thead>
            <tbody>
              {records.map((rec: any, i: number) => (
                <tr key={i} className="border-b border-[#132436] hover:bg-[#1a2d42]/30">
                  <td className="py-1 px-2 text-[#6f87a0] tabular-nums whitespace-nowrap">
                    {(rec.timestamp || rec.date || '').split('T')[0]}
                  </td>
                  <td className="py-1 px-2 text-[#8faabe]">{rec.transaction_type || '-'}</td>
                  <td className="py-1 px-2 text-[#5a7a94] max-w-[200px] truncate">
                    {rec.additional_data || '-'}
                  </td>
                  <td className="py-1 px-2 text-right tabular-nums text-red-400">
                    {rec.debit_amount ? parseFloat(rec.debit_amount).toFixed(4) : ''}
                  </td>
                  <td className="py-1 px-2 text-right tabular-nums text-green-400">
                    {rec.credit_amount ? parseFloat(rec.credit_amount).toFixed(4) : ''}
                  </td>
                  <td className="py-1 px-2 text-right tabular-nums text-[#5a7a94]">
                    {rec.fee_amount ? parseFloat(rec.fee_amount).toFixed(6) : ''}
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      )}
    </ExampleWrapper>
  )
}
