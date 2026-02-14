import { useState, useMemo } from 'react'
import { useQuery } from '@tanstack/react-query'
import {
  Table,
  FileDown,
  ChevronDown,
  ChevronRight,
  Calendar,
  Filter,
  Search,
  BookOpen,
} from 'lucide-react'
import { format, parseISO } from 'date-fns'
import { supabaseQueries, type StrategyLedger } from '../services/supabase'

// Format percentage (values already in percentage form, e.g., 0.43 means 0.43%)
function formatPct(value: number): string {
  return `${value.toFixed(2)}%`
}

// Format number with commas
function formatNumber(value: number, decimals: number = 2): string {
  return value.toLocaleString(undefined, { minimumFractionDigits: decimals, maximumFractionDigits: decimals })
}

// Strategy display names
const STRATEGY_DISPLAY_NAMES: Record<string, string> = {
  bedrock: 'Bedrock',
  yield_hunter: 'Sharpe Hunter',
  contrarian: 'Vol-Targeted',
}

// Parse notes JSON to get positions
function parsePositions(notes: string | null): PositionEntry[] {
  if (!notes) return []
  try {
    const parsed = JSON.parse(notes)
    if (parsed.positions && Array.isArray(parsed.positions)) {
      return parsed.positions as PositionEntry[]
    }
    return []
  } catch {
    return []
  }
}

// Export to CSV
function exportToCSV(data: StrategyLedger[], filename: string) {
  const headers = [
    'Strategy ID',
    'Date',
    'NAV',
    'Daily Return %',
    'Max Drawdown %',
    'SN88 MAR',
    'SN88 LSR',
    'SN88 Odds',
    'SN88 Daily',
    'SN88 Score',
    'Win Rate',
    'Turnover',
    'Notes',
  ]

  const rows = data.map((row) => [
    row.strategy_id,
    row.date,
    row.nav,
    row.daily_return_pct,
    row.max_drawdown_pct,
    row.sn88_mar,
    row.sn88_lsr,
    row.sn88_odds,
    row.sn88_daily,
    row.sn88_score,
    row.win_rate,
    row.turnover,
    row.notes || '',
  ])

  const csvContent = [headers.join(','), ...rows.map((row) => row.join(','))].join('\n')

  const blob = new Blob([csvContent], { type: 'text/csv;charset=utf-8;' })
  const link = document.createElement('a')
  const url = URL.createObjectURL(blob)
  link.setAttribute('href', url)
  link.setAttribute('download', filename)
  link.style.visibility = 'hidden'
  document.body.appendChild(link)
  link.click()
  document.body.removeChild(link)
}

interface PositionEntry {
  netuid: number
  weight: number
  value_tao: number
}

export default function Ledger() {
  const [selectedStrategy, setSelectedStrategy] = useState<string>('all')
  const [startDate, setStartDate] = useState<string>('')
  const [endDate, setEndDate] = useState<string>('')
  const [expandedRows, setExpandedRows] = useState<Set<string>>(new Set())
  const [searchQuery, setSearchQuery] = useState('')

  // Fetch all strategy IDs
  const { data: strategyIds, isLoading: isLoadingIds } = useQuery({
    queryKey: ['supabase-strategy-ids'],
    queryFn: supabaseQueries.getStrategyIds,
  })

  // Fetch ledger data
  const { data: ledgerData, isLoading: isLoadingLedger } = useQuery({
    queryKey: ['supabase-ledger', selectedStrategy, startDate, endDate],
    queryFn: () =>
      supabaseQueries.getStrategyHistory(
        selectedStrategy === 'all' ? undefined : selectedStrategy,
        startDate || undefined,
        endDate || undefined
      ),
    refetchInterval: 60000,
  })

  // Toggle row expansion
  const toggleRow = (key: string) => {
    setExpandedRows((prev) => {
      const newSet = new Set(prev)
      if (newSet.has(key)) {
        newSet.delete(key)
      } else {
        newSet.add(key)
      }
      return newSet
    })
  }

  // Filter data by search
  const filteredData = useMemo(() => {
    if (!ledgerData) return []
    if (!searchQuery) return ledgerData

    const query = searchQuery.toLowerCase()
    return ledgerData.filter(
      (row) =>
        row.strategy_id.toLowerCase().includes(query) ||
        row.date.includes(query) ||
        (row.notes || '').toLowerCase().includes(query)
    )
  }, [ledgerData, searchQuery])

  // Group by strategy for display
  const groupedData = useMemo(() => {
    const groups = new Map<string, StrategyLedger[]>()
    filteredData.forEach((row) => {
      if (!groups.has(row.strategy_id)) {
        groups.set(row.strategy_id, [])
      }
      groups.get(row.strategy_id)!.push(row)
    })
    return groups
  }, [filteredData])

  const isLoading = isLoadingIds || isLoadingLedger

  return (
    <div className="space-y-6">
      {/* Header */}
      <div className="flex items-center justify-between">
        <div>
          <h1 className="text-2xl font-bold text-[#2a3ded] flex items-center gap-2">
            <BookOpen className="w-6 h-6" />
            Daily Ledger Audit
          </h1>
          <p className="text-sm text-[#8a8f98] mt-1">
            Full transaction history and position breakdowns
          </p>
        </div>

        {/* Export Button */}
        <button
          onClick={() =>
            exportToCSV(
              filteredData,
              `ledger_export_${format(new Date(), 'yyyy-MM-dd')}.csv`
            )
          }
          disabled={filteredData.length === 0}
          className="flex items-center gap-2 px-4 py-2 bg-[#2a3ded] hover:bg-[#3a4dff] disabled:opacity-50 disabled:cursor-not-allowed rounded-lg text-sm font-medium text-white transition-colors"
        >
          <FileDown className="w-4 h-4" />
          Export CSV
        </button>
      </div>

      {/* Filters */}
      <div className="bg-[#16181d] rounded-lg border border-[#2a2f38] p-4">
        <div className="grid grid-cols-1 md:grid-cols-4 gap-4">
          {/* Strategy Selector */}
          <div>
            <label className="block text-xs text-[#6b7280] mb-2">
              <Filter className="w-3 h-3 inline mr-1" />
              Strategy
            </label>
            <select
              value={selectedStrategy}
              onChange={(e) => setSelectedStrategy(e.target.value)}
              className="w-full bg-[#0d0f12] border border-[#2a2f38] rounded-lg px-3 py-2 text-sm text-[#8faabe] focus:outline-none focus:border-[#2a3ded]"
            >
              <option value="all">All Strategies</option>
              {strategyIds?.map((id) => (
                <option key={id} value={id}>
                  {STRATEGY_DISPLAY_NAMES[id] || id}
                </option>
              ))}
            </select>
          </div>

          {/* Start Date */}
          <div>
            <label className="block text-xs text-[#6b7280] mb-2">
              <Calendar className="w-3 h-3 inline mr-1" />
              Start Date
            </label>
            <input
              type="date"
              value={startDate}
              onChange={(e) => setStartDate(e.target.value)}
              className="w-full bg-[#0d0f12] border border-[#2a2f38] rounded-lg px-3 py-2 text-sm text-[#8faabe] focus:outline-none focus:border-[#2a3ded]"
            />
          </div>

          {/* End Date */}
          <div>
            <label className="block text-xs text-[#6b7280] mb-2">
              <Calendar className="w-3 h-3 inline mr-1" />
              End Date
            </label>
            <input
              type="date"
              value={endDate}
              onChange={(e) => setEndDate(e.target.value)}
              className="w-full bg-[#0d0f12] border border-[#2a2f38] rounded-lg px-3 py-2 text-sm text-[#8faabe] focus:outline-none focus:border-[#2a3ded]"
            />
          </div>

          {/* Search */}
          <div>
            <label className="block text-xs text-[#6b7280] mb-2">
              <Search className="w-3 h-3 inline mr-1" />
              Search
            </label>
            <div className="relative">
              <input
                type="text"
                placeholder="Search..."
                value={searchQuery}
                onChange={(e) => setSearchQuery(e.target.value)}
                className="w-full bg-[#0d0f12] border border-[#2a2f38] rounded-lg pl-9 pr-3 py-2 text-sm text-[#8faabe] placeholder-gray-500 focus:outline-none focus:border-[#2a3ded]"
              />
              <Search className="absolute left-3 top-2.5 w-4 h-4 text-[#6b7280]" />
            </div>
          </div>
        </div>
      </div>

      {/* Ledger Table */}
      <div className="bg-[#16181d] rounded-lg border border-[#2a2f38] overflow-hidden">
        <div className="px-5 py-4 border-b border-[#2a2f38] flex items-center justify-between">
          <div className="flex items-center gap-2">
            <Table className="w-5 h-5 text-[#2a3ded]" />
            <h3 className="font-semibold text-white">Ledger Entries</h3>
          </div>
          <span className="text-xs text-[#6b7280]">
            {filteredData.length.toLocaleString()} records
          </span>
        </div>

        {isLoading ? (
          <div className="p-8">
            <div className="space-y-2">
              {[1, 2, 3, 4, 5].map((i) => (
                <div key={i} className="h-12 bg-[#1e2128] rounded animate-pulse" />
              ))}
            </div>
          </div>
        ) : (
          <div className="overflow-x-auto">
            <table className="w-full">
              <thead>
                <tr className="bg-[#0d0f12]">
                  <th className="px-4 py-3 text-left text-xs font-semibold text-[#6b7280] uppercase tracking-wider w-8" />
                  <th className="px-4 py-3 text-left text-xs font-semibold text-[#6b7280] uppercase tracking-wider">
                    Strategy
                  </th>
                  <th className="px-4 py-3 text-left text-xs font-semibold text-[#6b7280] uppercase tracking-wider">
                    Date
                  </th>
                  <th className="px-4 py-3 text-right text-xs font-semibold text-[#6b7280] uppercase tracking-wider">
                    NAV
                  </th>
                  <th className="px-4 py-3 text-right text-xs font-semibold text-[#6b7280] uppercase tracking-wider">
                    Daily Return
                  </th>
                  <th className="px-4 py-3 text-right text-xs font-semibold text-[#6b7280] uppercase tracking-wider">
                    Max DD
                  </th>
                  <th className="px-4 py-3 text-right text-xs font-semibold text-[#6b7280] uppercase tracking-wider">
                    MAR
                  </th>
                  <th className="px-4 py-3 text-right text-xs font-semibold text-[#6b7280] uppercase tracking-wider">
                    LSR
                  </th>
                  <th className="px-4 py-3 text-right text-xs font-semibold text-[#6b7280] uppercase tracking-wider">
                    Odds
                  </th>
                  <th className="px-4 py-3 text-right text-xs font-semibold text-[#6b7280] uppercase tracking-wider">
                    SN88
                  </th>
                </tr>
              </thead>
              <tbody className="divide-y divide-[#2a2f38]">
                {filteredData.map((row) => {
                  const rowKey = `${row.strategy_id}-${row.date}`
                  const isExpanded = expandedRows.has(rowKey)
                  const positions = parsePositions(row.notes)

                  return (
                    <>
                      <tr
                        key={rowKey}
                        className="hover:bg-[#1e2128]/50 cursor-pointer"
                        onClick={() => toggleRow(rowKey)}
                      >
                        <td className="px-4 py-3">
                          {positions.length > 0 ? (
                            isExpanded ? (
                              <ChevronDown className="w-4 h-4 text-[#6b7280]" />
                            ) : (
                              <ChevronRight className="w-4 h-4 text-[#6b7280]" />
                            )
                          ) : (
                            <div className="w-4 h-4" />
                          )}
                        </td>
                        <td className="px-4 py-3">
                          <span className="text-sm font-medium text-white">
                            {STRATEGY_DISPLAY_NAMES[row.strategy_id] || row.strategy_id}
                          </span>
                        </td>
                        <td className="px-4 py-3">
                          <span className="text-sm text-[#9ca3af]">
                            {format(parseISO(row.date), 'MMM d, yyyy')}
                          </span>
                        </td>
                        <td className="px-4 py-3 text-right">
                          <span className="text-sm text-white tabular-nums">
                            {formatNumber(row.nav)} τ
                          </span>
                        </td>
                        <td className="px-4 py-3 text-right">
                          <span
                            className={`text-sm tabular-nums ${
                              (row.daily_return_pct || 0) >= 0 ? 'text-green-400' : 'text-red-400'
                            }`}
                          >
                            {(row.daily_return_pct || 0) >= 0 ? '+' : ''}
                            {formatPct(row.daily_return_pct || 0)}
                          </span>
                        </td>
                        <td className="px-4 py-3 text-right">
                          <span className="text-sm text-red-400 tabular-nums">
                            {formatPct(row.max_drawdown_pct || 0)}
                          </span>
                        </td>
                        <td className="px-4 py-3 text-right">
                          <span className="text-sm text-white tabular-nums">
                            {row.sn88_mar?.toFixed(2) || '—'}
                          </span>
                        </td>
                        <td className="px-4 py-3 text-right">
                          <span className="text-sm text-white tabular-nums">
                            {row.sn88_lsr?.toFixed(2) || '—'}
                          </span>
                        </td>
                        <td className="px-4 py-3 text-right">
                          <span className="text-sm text-white tabular-nums">
                            {row.sn88_odds ? formatPct(row.sn88_odds) : '—'}
                          </span>
                        </td>
                        <td className="px-4 py-3 text-right">
                          <span
                            className={`text-sm font-bold tabular-nums ${
                              (row.sn88_score || 0) >= 70
                                ? 'text-green-400'
                                : (row.sn88_score || 0) >= 50
                                ? 'text-yellow-400'
                                : 'text-red-400'
                            }`}
                          >
                            {(row.sn88_score || 0).toFixed(1)}
                          </span>
                        </td>
                      </tr>

                      {/* Expanded Position Details */}
                      {isExpanded && positions.length > 0 && (
                        <tr key={`${rowKey}-expanded`}>
                          <td colSpan={10} className="px-4 py-4 bg-[#0d0f12]">
                            <div className="pl-8">
                              <div className="text-xs text-[#6b7280] mb-2 uppercase tracking-wider">
                                Position Breakdown ({positions.length} positions)
                              </div>
                              <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-3 gap-3">
                                {positions.map((pos, idx) => (
                                  <div
                                    key={idx}
                                    className="flex items-center justify-between p-3 bg-[#16181d] rounded border border-[#2a2f38]"
                                  >
                                    <div>
                                      <div className="text-sm font-medium text-white">
                                        SN{pos.netuid}
                                      </div>
                                      <div className="text-xs text-[#6b7280]">
                                        NetUID {pos.netuid}
                                      </div>
                                    </div>
                                    <div className="text-right">
                                      <div className="text-sm text-white tabular-nums">
                                        {formatNumber(pos.weight * 100, 1)}%
                                      </div>
                                      <div className="text-xs text-[#6b7280] tabular-nums">
                                        {formatNumber(pos.value_tao)} τ
                                      </div>
                                    </div>
                                  </div>
                                ))}
                              </div>
                            </div>
                          </td>
                        </tr>
                      )}
                    </>
                  )
                })}
              </tbody>
            </table>

            {filteredData.length === 0 && !isLoading && (
              <div className="text-center py-12 text-[#6b7280]">
                <Table className="w-8 h-8 mx-auto mb-3 opacity-50" />
                <p className="text-sm">No ledger entries found</p>
                <p className="text-xs mt-1">
                  {searchQuery
                    ? 'Try adjusting your search or filters'
                    : 'Data will appear once strategies start reporting'}
                </p>
              </div>
            )}
          </div>
        )}
      </div>

      {/* Summary Stats */}
      {filteredData.length > 0 && (
        <div className="grid grid-cols-1 md:grid-cols-4 gap-4">
          <div className="bg-[#16181d] rounded-lg border border-[#2a2f38] p-4">
            <div className="text-xs text-[#6b7280] mb-1">Total Records</div>
            <div className="text-xl font-bold text-white">
              {filteredData.length.toLocaleString()}
            </div>
          </div>

          <div className="bg-[#16181d] rounded-lg border border-[#2a2f38] p-4">
            <div className="text-xs text-[#6b7280] mb-1">Unique Strategies</div>
            <div className="text-xl font-bold text-white">
              {groupedData.size}
            </div>
          </div>

          <div className="bg-[#16181d] rounded-lg border border-[#2a2f38] p-4">
            <div className="text-xs text-[#6b7280] mb-1">Date Range</div>
            <div className="text-sm font-bold text-white">
              {filteredData.length > 0 && (
                <>
                  {format(parseISO(filteredData[filteredData.length - 1].date), 'MMM d')} -{' '}
                  {format(parseISO(filteredData[0].date), 'MMM d, yyyy')}
                </>
              )}
            </div>
          </div>

          <div className="bg-[#16181d] rounded-lg border border-[#2a2f38] p-4">
            <div className="text-xs text-[#6b7280] mb-1">Avg SN88 Score</div>
            <div className="text-xl font-bold text-white">
              {filteredData.length > 0
                ? (
                    filteredData.reduce((sum, row) => sum + (row.sn88_score || 0), 0) /
                    filteredData.length
                  ).toFixed(1)
                : '—'}
            </div>
          </div>
        </div>
      )}
    </div>
  )
}
