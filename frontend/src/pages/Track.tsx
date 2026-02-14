import { useState, useMemo } from 'react'
import { useQuery } from '@tanstack/react-query'
import { ChevronDown, ChevronRight, Search, Columns, X, ArrowUpDown, ArrowUp, ArrowDown } from 'lucide-react'
import { supabase } from '../services/supabase'

interface PortfolioData { positions?: PositionData[]; total_value_tao?: number; total_value_usd?: number }
interface PositionData {
  netuid: number; subnet_name?: string; stake: number; value_tao?: number; value_usd?: number
  pct_of_portfolio?: number; daily_return_pct?: number; weekly_return_pct?: number
  yield_tao?: number; alpha_tao?: number; pnl_tao?: number; apy?: number; validator?: string; chart_data?: number[]
}
interface SubnetScore { netuid: number; viability_score: number; viability_label: string; regime: string }

const FALLBACK_POSITIONS: PositionData[] = [
  { netuid: 64, subnet_name: 'Chutes', stake: 303.67, pct_of_portfolio: 59.3, value_usd: 57451, daily_return_pct: -1.38, weekly_return_pct: 8.05, yield_tao: 1.94, alpha_tao: 11.73, pnl_tao: 13.68, apy: 47.31, validator: 'tao.bot' },
  { netuid: 44, subnet_name: 'Score', stake: 48.95, pct_of_portfolio: 9.6, value_usd: 9261, daily_return_pct: 3.54, weekly_return_pct: 25.19, yield_tao: 0.48, alpha_tao: 7.48, pnl_tao: 7.96, apy: 33.96, validator: 'tao.bot' },
  { netuid: 120, subnet_name: 'Affine', stake: 46.76, pct_of_portfolio: 9.1, value_usd: 8846, daily_return_pct: 1.18, weekly_return_pct: 15.70, yield_tao: 1.14, alpha_tao: 2.61, pnl_tao: 3.75, apy: 65.76, validator: 'tao.bot' },
  { netuid: 8, subnet_name: 'Vanta', stake: 35.57, pct_of_portfolio: 6.9, value_usd: 6729, daily_return_pct: 0.03, weekly_return_pct: 1.45, yield_tao: 0.43, alpha_tao: -0.88, pnl_tao: -0.44, apy: 50.81, validator: 'tao.bot' },
  { netuid: 81, subnet_name: 'Grail', stake: 35.09, pct_of_portfolio: 8.9, value_usd: 6637, daily_return_pct: 4.57, weekly_return_pct: -1.82, yield_tao: 0.08, alpha_tao: 10.00, pnl_tao: 10.09, apy: 64.25, validator: 'tao.bot' },
  { netuid: 3, subnet_name: 'Templar', stake: 22.07, pct_of_portfolio: 4.3, value_usd: 4176, daily_return_pct: -0.06, weekly_return_pct: -3.46, yield_tao: 0.51, alpha_tao: -0.45, pnl_tao: 0.06, apy: 51.37, validator: 'tao.bot' },
  { netuid: 39, subnet_name: 'SN39', stake: 10.7, pct_of_portfolio: 2.1, value_usd: 2026 },
  { netuid: 2, subnet_name: 'DSperse', stake: 8.2, pct_of_portfolio: 1.6, value_usd: 1554 },
]

const Sparkline = ({ data, color }: { data: number[]; color: string }) => {
  if (!data?.length) return <div className="w-20 h-8 bg-gray-700 rounded" />
  const max = Math.max(...data), min = Math.min(...data), range = max - min || 1
  const points = data.map((v, i) => `${(i / (data.length - 1)) * 80},${32 - ((v - min) / range) * 28}`).join(' ')
  return <svg width="80" height="32"><polyline points={points} fill="none" stroke={color} strokeWidth="1.5" /></svg>
}

const fmt = (v?: number, d = 2) => v == null ? '--' : v.toLocaleString(undefined, { minimumFractionDigits: d, maximumFractionDigits: d })
const fmtUsd = (v?: number) => v == null ? '--' : '$' + fmt(v)
const fmtPct = (v?: number) => v == null ? '--' : `${v >= 0 ? '+' : ''}${v.toFixed(2)}%`
const subnetColor = (n: number) => ['#ef4444','#f97316','#f59e0b','#84cc16','#10b981','#06b6d4','#3b82f6','#6366f1','#8b5cf6','#d946ef','#f43f5e','#14b8a6','#22c55e','#eab308','#a855f7'][n % 15]

const Badge = ({ score, label }: { score: number; label: string }) => {
  const cls = label === 'Eligible' ? 'bg-green-500/20 text-green-400 border-green-500/50' :
    label === 'Watchlist' ? 'bg-yellow-500/20 text-yellow-400 border-yellow-500/50' :
    'bg-red-500/20 text-red-400 border-red-500/50'
  return <span className={`px-2 py-1 rounded text-xs font-medium border ${cls}`}>{label} ({score})</span>
}

const SortIcon = ({ col, active, dir }: { col: string; active: string | null; dir: string }) => {
  if (active !== col) return <ArrowUpDown className="w-3 h-3 text-gray-500 ml-1" />
  return dir === 'asc' ? <ArrowUp className="w-3 h-3 text-emerald-400 ml-1" /> : <ArrowDown className="w-3 h-3 text-emerald-400 ml-1" />
}

export default function Track() {
  const [mode, setMode] = useState<'tao'|'usd'>('tao')
  const [wallet, setWallet] = useState('5EnHLg...n2grd')
  const [walletInput, setWalletInput] = useState('')
  const [tab, setTab] = useState<'active'|'inactive'|'all'>('active')
  const [search, setSearch] = useState('')
  const [expanded, setExpanded] = useState<Set<number>>(new Set())
  const [sortCol, setSortCol] = useState<string|null>(null)
  const [sortDir, setSortDir] = useState<'asc'|'desc'>('desc')

  const { data: portfolio, isLoading } = useQuery({
    queryKey: ['portfolio-current'],
    queryFn: async () => {
      try {
        const { data, error } = await supabase.from('raw_api_data').select('data').eq('source', 'portfolio_current').order('fetched_at', { ascending: false }).limit(1).single()
        if (error) throw error
        return data?.data as PortfolioData
      } catch { return { positions: FALLBACK_POSITIONS } }
    },
  })

  const { data: scores } = useQuery({
    queryKey: ['subnet-scores'],
    queryFn: async () => {
      try {
        const { data, error } = await supabase.from('subnet_scores').select('*').order('scored_at', { ascending: false })
        if (error) throw error
        const m = new Map<number, SubnetScore>()
        data?.forEach(s => { if (!m.has(s.netuid)) m.set(s.netuid, s as SubnetScore) })
        return m
      } catch { return new Map<number, SubnetScore>() }
    },
  })

  const positions = useMemo(() => {
    return (portfolio?.positions || FALLBACK_POSITIONS).map(p => {
      const sc = scores?.get(p.netuid)
      return { ...p, viability_score: sc?.viability_score ?? 0, viability_label: sc?.viability_label ?? 'Excluded', regime: sc?.regime ?? 'Risk Off', validator: p.validator ?? 'tao.bot', chart_data: p.chart_data ?? Array.from({length:7},(_,i) => 100 + (p.weekly_return_pct||0)/7*i + (Math.random()-0.5)*5) }
    })
  }, [portfolio, scores])

  const filtered = useMemo(() => {
    let list = tab === 'active' ? positions.filter(p => p.stake > 0) : tab === 'inactive' ? positions.filter(p => p.stake === 0) : positions
    if (search) { const q = search.toLowerCase(); list = list.filter(p => (p.subnet_name||'').toLowerCase().includes(q) || `sn${p.netuid}`.includes(q)) }
    if (sortCol) {
      list = [...list].sort((a: any, b: any) => {
        const av = a[sortCol] ?? a.stake ?? 0, bv = b[sortCol] ?? b.stake ?? 0
        return sortDir === 'asc' ? (av > bv ? 1 : -1) : (av < bv ? 1 : -1)
      })
    }
    return list
  }, [positions, tab, search, sortCol, sortDir])

  const sort = (c: string) => { if (sortCol === c) setSortDir(d => d === 'asc' ? 'desc' : 'asc'); else { setSortCol(c); setSortDir('desc') } }
  const toggle = (n: number) => { const s = new Set(expanded); s.has(n) ? s.delete(n) : s.add(n); setExpanded(s) }
  const activeN = positions.filter(p => p.stake > 0).length, inactiveN = positions.filter(p => p.stake === 0).length

  const kpi = {
    value: { tao: 512.21, usd: 97176.53, realized: -21.95, unrealized: 32.06, total: 10.11 },
    yield: { tao: 10.12, usd: 1919.36, realized: 5.31, unrealized: 4.81 },
    alpha: { tao: -0.01, usd: -1.26, realized: -27.26, unrealized: 27.25 },
    apy: { value: 49.0, daily: 0.69, proj7d: 4.81, proj30d: 20.62 },
    fx: { value: -7763.95, pct: -3.2, at: 1431.84, tu: -9195.79 },
  }

  if (isLoading) return <div className="flex items-center justify-center h-64"><div className="animate-spin rounded-full h-8 w-8 border-b-2 border-emerald-400" /></div>

  const KpiCard = ({ title, main, sub, rows }: { title: string; main: string; sub: string; rows: [string, string, string][] }) => (
    <div className="bg-gray-800 border border-gray-700 rounded-lg p-4">
      <div className="text-sm text-gray-400 mb-1">{title}</div>
      <div className="text-2xl font-bold text-white">{main}</div>
      <div className="text-xs text-gray-500 mt-1">{sub}</div>
      <div className="mt-3 pt-3 border-t border-gray-700 text-xs text-gray-400 space-y-1">
        {rows.map(([l, v, c], i) => <div key={i} className="flex justify-between"><span>{l}</span><span className={c}>{v}</span></div>)}
      </div>
    </div>
  )

  const TH = ({ col, label }: { col: string; label: string }) => (
    <th className="px-3 py-3 font-medium cursor-pointer hover:text-gray-200 whitespace-nowrap" onClick={() => sort(col)}>
      <div className="flex items-center">{label}<SortIcon col={col} active={sortCol} dir={sortDir} /></div>
    </th>
  )

  return (
    <div className="space-y-6 p-4 bg-gray-900 min-h-screen text-gray-100">
      <div className="space-y-4">
        <h1 className="text-2xl font-bold text-emerald-500">Track</h1>
        <div className="flex gap-2 max-w-xl">
          <input type="text" placeholder="Add wallet address (SS58 format)" value={walletInput} onChange={e => setWalletInput(e.target.value)}
            className="flex-1 px-4 py-2 bg-gray-800 border border-gray-700 rounded-lg text-sm text-gray-200 placeholder-gray-500 focus:outline-none focus:border-blue-500" />
          <button onClick={() => { if (walletInput.trim()) { setWallet(walletInput.trim()); setWalletInput('') } }}
            className="px-4 py-2 bg-blue-600 hover:bg-blue-700 text-white text-sm font-medium rounded-lg">Add</button>
        </div>
        {wallet && <span className="inline-flex items-center gap-1 px-3 py-1 bg-gray-800 border border-gray-700 rounded-full text-sm text-gray-300">
          {wallet}<button onClick={() => setWallet('')} className="ml-1 hover:text-red-400"><X className="w-3 h-3" /></button>
        </span>}
      </div>

      {/* KPI Cards */}
      <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-5 gap-4">
        <KpiCard title="Current Value" main={mode==='tao'?`${fmt(kpi.value.tao)} τ`:fmtUsd(kpi.value.usd)} sub={mode==='tao'?fmtUsd(kpi.value.usd):`${fmt(kpi.value.tao)} τ`}
          rows={[['Realized:',`${kpi.value.realized}τ`,kpi.value.realized>=0?'text-green-400':'text-red-400'],['Unrealized:',`+${kpi.value.unrealized}τ`,'text-green-400'],['Total:',`+${kpi.value.total}τ`,'text-green-400']]} />
        <KpiCard title="Yield" main={mode==='tao'?`${fmt(kpi.yield.tao)} τ`:fmtUsd(kpi.yield.usd)} sub={mode==='tao'?fmtUsd(kpi.yield.usd):`${fmt(kpi.yield.tao)} τ`}
          rows={[['Realized:',`+${fmt(kpi.yield.realized)}τ`,'text-green-400'],['Unrealized:',`+${fmt(kpi.yield.unrealized)}τ`,'text-green-400']]} />
        <KpiCard title="Alpha" main={mode==='tao'?`${fmt(kpi.alpha.tao)} τ`:fmtUsd(kpi.alpha.usd)} sub={mode==='tao'?fmtUsd(kpi.alpha.usd):`${fmt(kpi.alpha.tao)} τ`}
          rows={[['Realized:',`${fmt(kpi.alpha.realized)}τ`,'text-red-400'],['Unrealized:',`+${fmt(kpi.alpha.unrealized)}τ`,'text-green-400']]} />
        <KpiCard title="APY" main={`${kpi.apy.value.toFixed(1)}%`} sub={`${kpi.apy.daily.toFixed(2)}/day`}
          rows={[['7d Proj:',`${fmt(kpi.apy.proj7d)}τ`,'text-emerald-400'],['30d Proj:',`${fmt(kpi.apy.proj30d)}τ`,'text-emerald-400']]} />
        <KpiCard title="FX Exposure" main={fmtUsd(kpi.fx.value)} sub={`${kpi.fx.pct.toFixed(1)}%`}
          rows={[['α/τ Effect:',fmtUsd(kpi.fx.at),'text-green-400'],['τ/$ Effect:',fmtUsd(kpi.fx.tu),'text-red-400']]} />
      </div>

      {/* Toggle */}
      <div className="flex justify-center">
        <div className="inline-flex bg-gray-800 border border-gray-700 rounded-lg p-1">
          {(['tao','usd'] as const).map(m => <button key={m} onClick={() => setMode(m)}
            className={`px-4 py-2 text-sm font-medium rounded-md ${mode===m?'bg-gray-700 text-white':'text-gray-400 hover:text-white'}`}>
            {m==='tao'?'τ':'$'}</button>)}
        </div>
      </div>

      {/* Tabs + Filters */}
      <div className="flex flex-col sm:flex-row sm:items-center sm:justify-between gap-4">
        <div className="flex border-b border-gray-700">
          {([['active',activeN],['inactive',inactiveN],['all',positions.length]] as const).map(([t,n]) =>
            <button key={t} onClick={() => setTab(t as any)} className={`px-4 py-3 text-sm font-medium border-b-2 ${tab===t?'border-emerald-500 text-emerald-400':'border-transparent text-gray-400 hover:text-gray-200'}`}>
              {t==='active'?'Active':t==='inactive'?'Inactive':'All'} Positions ({n})</button>)}
        </div>
        <div className="flex items-center gap-2">
          <div className="relative">
            <Search className="absolute left-3 top-1/2 -translate-y-1/2 w-4 h-4 text-gray-500" />
            <input type="text" placeholder="Search subnets..." value={search} onChange={e => setSearch(e.target.value)}
              className="pl-9 pr-4 py-2 bg-gray-800 border border-gray-700 rounded-lg text-sm text-gray-200 placeholder-gray-500 focus:outline-none focus:border-emerald-500" />
          </div>
          <select className="px-3 py-2 bg-gray-800 border border-gray-700 rounded-lg text-sm text-gray-300">
            <option>Wallet: All</option>
          </select>
          <button className="flex items-center gap-2 px-3 py-2 bg-gray-800 border border-gray-700 rounded-lg text-sm text-gray-300 hover:bg-gray-700">
            <Columns className="w-4 h-4" />Columns</button>
        </div>
      </div>

      {/* Table */}
      <div className="bg-gray-800 border border-gray-700 rounded-lg overflow-x-auto">
        <table className="w-full min-w-[1400px]">
          <thead><tr className="border-b border-gray-700 text-left text-xs text-gray-400 uppercase">
            <th className="px-3 py-3 w-8" />
            <TH col="subnet_name" label="SUBNET" />
            <th className="px-3 py-3 font-medium">7D CHART</th>
            <TH col="daily_return_pct" label="24H / 7D" />
            <TH col="value_usd" label="VALUE" />
            <TH col="pct_of_portfolio" label="% OF STAKE" />
            <TH col="stake" label="TAO" />
            <TH col="yield_tao" label="YIELD" />
            <TH col="alpha_tao" label="ALPHA" />
            <TH col="pnl_tao" label="P&L" />
            <TH col="apy" label="APY" />
            <th className="px-3 py-3 font-medium">VIABILITY</th>
            <th className="px-3 py-3 font-medium">REGIME</th>
            <th className="px-3 py-3 font-medium">VALIDATOR</th>
          </tr></thead>
          <tbody>
            {filtered.map(p => (
              <tr key={p.netuid} className="border-b border-gray-700/50 hover:bg-gray-700/30 text-sm" onClick={() => toggle(p.netuid)}>
                <td className="px-3 py-3">{expanded.has(p.netuid) ? <ChevronDown className="w-4 h-4 text-gray-500" /> : <ChevronRight className="w-4 h-4 text-gray-500" />}</td>
                <td className="px-3 py-3">
                  <div className="flex items-center gap-2">
                    <div className="w-7 h-7 rounded-full flex items-center justify-center text-xs font-bold text-white" style={{ backgroundColor: subnetColor(p.netuid) }}>
                      {(p.subnet_name||'?')[0]}
                    </div>
                    <div><div className="font-medium text-white">{p.subnet_name}</div><div className="text-xs text-gray-500">SN{p.netuid}</div></div>
                  </div>
                </td>
                <td className="px-3 py-3"><Sparkline data={p.chart_data||[]} color={(p.weekly_return_pct||0)>=0?'#10b981':'#ef4444'} /></td>
                <td className="px-3 py-3">
                  <div className={`text-xs ${(p.daily_return_pct||0)>=0?'text-green-400':'text-red-400'}`}>{fmtPct(p.daily_return_pct)}</div>
                  <div className={`text-xs ${(p.weekly_return_pct||0)>=0?'text-green-400':'text-red-400'}`}>{fmtPct(p.weekly_return_pct)}</div>
                </td>
                <td className="px-3 py-3 text-white">{fmtUsd(p.value_usd)}</td>
                <td className="px-3 py-3 text-white">{p.pct_of_portfolio?.toFixed(1)}%</td>
                <td className="px-3 py-3 text-white">{fmt(p.stake)} τ</td>
                <td className="px-3 py-3 text-white">{fmt(p.yield_tao)} τ</td>
                <td className="px-3 py-3 text-white">{fmt(p.alpha_tao)} τ</td>
                <td className={`px-3 py-3 font-medium ${(p.pnl_tao||0)>=0?'text-green-400':'text-red-400'}`}>{fmt(p.pnl_tao)} τ</td>
                <td className="px-3 py-3 text-white">{(p.apy||0).toFixed(2)}%</td>
                <td className="px-3 py-3"><Badge score={p.viability_score} label={p.viability_label} /></td>
                <td className={`px-3 py-3 ${p.regime==='Risk On'?'text-green-400':'text-red-400'}`}>{p.regime}</td>
                <td className="px-3 py-3 text-gray-300">{p.validator}</td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>
      <div className="text-xs text-gray-500 text-right">{filtered.length} positions</div>
    </div>
  )
}
