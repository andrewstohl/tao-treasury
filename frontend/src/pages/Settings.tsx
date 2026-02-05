import { useState, useEffect, useCallback, useRef } from 'react'
import { useQuery, useMutation, useQueryClient } from '@tanstack/react-query'
import { Save, RotateCcw, AlertTriangle, CheckCircle, Info, Play, TrendingUp, TrendingDown, Download, Loader2 } from 'lucide-react'
import { api } from '../services/api'
import type { ViabilityConfig, BacktestResult, BackfillStatus, PortfolioSimResult } from '../types'

type NumericField = {
  key: string
  label: string
  description: string
  min: number
  max: number
  step: number
  format: 'decimal' | 'percent' | 'integer' | 'tao'
}

const HARD_FAILURE_FIELDS: NumericField[] = [
  { key: 'min_tao_reserve', label: 'Min TAO Reserve', description: 'Minimum pool TAO reserve to pass', min: 0, max: 10000, step: 50, format: 'tao' },
  { key: 'min_emission_share', label: 'Min Emission Share', description: 'Minimum emission share (as decimal)', min: 0, max: 0.1, step: 0.0005, format: 'percent' },
  { key: 'min_age_days', label: 'Min Age (days)', description: 'Minimum subnet age in days', min: 0, max: 365, step: 1, format: 'integer' },
  { key: 'min_holders', label: 'Min Holders', description: 'Minimum token holder count', min: 0, max: 500, step: 5, format: 'integer' },
  { key: 'max_drawdown_30d', label: 'Max 30d Drawdown', description: 'Maximum 30-day drawdown allowed', min: 0, max: 1, step: 0.05, format: 'percent' },
  { key: 'max_negative_flow_ratio', label: 'Max Outflow Ratio', description: '7d outflow as fraction of reserve', min: 0, max: 1, step: 0.05, format: 'percent' },
]

const WEIGHT_FIELDS: NumericField[] = [
  { key: 'weight_tao_reserve', label: 'TAO Reserve', description: 'Pool TAO liquidity depth', min: 0, max: 1, step: 0.05, format: 'decimal' },
  { key: 'weight_net_flow_7d', label: 'Net Flow 7d', description: '7-day net TAO flow', min: 0, max: 1, step: 0.05, format: 'decimal' },
  { key: 'weight_emission_share', label: 'Emission Share', description: 'Share of network emissions', min: 0, max: 1, step: 0.05, format: 'decimal' },
  { key: 'weight_price_trend_7d', label: 'Price Trend 7d', description: '7-day price change', min: 0, max: 1, step: 0.05, format: 'decimal' },
  { key: 'weight_subnet_age', label: 'Subnet Age', description: 'Days since registration', min: 0, max: 1, step: 0.05, format: 'decimal' },
  { key: 'weight_max_drawdown_30d', label: 'Max Drawdown 30d', description: 'Lower drawdown = better', min: 0, max: 1, step: 0.05, format: 'decimal' },
]

const TIER_FIELDS: NumericField[] = [
  { key: 'tier_1_min', label: 'Tier 1 (Prime)', description: 'Min score for Prime tier', min: 0, max: 100, step: 1, format: 'integer' },
  { key: 'tier_2_min', label: 'Tier 2 (Eligible)', description: 'Min score for Eligible tier', min: 0, max: 100, step: 1, format: 'integer' },
  { key: 'tier_3_min', label: 'Tier 3 (Watchlist)', description: 'Min score for Watchlist tier', min: 0, max: 100, step: 1, format: 'integer' },
  { key: 'age_cap_days', label: 'Age Cap (days)', description: 'Cap age metric at this value', min: 30, max: 730, step: 30, format: 'integer' },
]

function getFieldValue(config: ViabilityConfig, key: string): number {
  // eslint-disable-next-line @typescript-eslint/no-explicit-any
  const val = (config as any)[key]
  if (typeof val === 'number') return val
  if (typeof val === 'string') return parseFloat(val)
  return 0
}

function formatDisplay(value: number, format: NumericField['format']): string {
  switch (format) {
    case 'percent': return `${(value * 100).toFixed(1)}%`
    case 'tao': return `${value.toLocaleString()} TAO`
    case 'integer': return String(Math.round(value))
    case 'decimal': return value.toFixed(2)
  }
}

export default function Settings() {
  const queryClient = useQueryClient()
  const [draft, setDraft] = useState<Record<string, number> | null>(null)
  const [saveStatus, setSaveStatus] = useState<'idle' | 'saved' | 'error'>('idle')

  const { data: config, isLoading } = useQuery<ViabilityConfig>({
    queryKey: ['viability-config'],
    queryFn: api.getViabilityConfig,
  })

  // Initialize draft from loaded config
  useEffect(() => {
    if (config && !draft) {
      const initial: Record<string, number> = {}
      for (const f of [...HARD_FAILURE_FIELDS, ...WEIGHT_FIELDS, ...TIER_FIELDS]) {
        initial[f.key] = getFieldValue(config, f.key)
      }
      initial['enabled'] = config.enabled ? 1 : 0
      setDraft(initial)
    }
  }, [config, draft])

  const saveMutation = useMutation({
    mutationFn: api.updateViabilityConfig,
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ['viability-config'] })
      setSaveStatus('saved')
      setTimeout(() => setSaveStatus('idle'), 3000)
    },
    onError: () => {
      setSaveStatus('error')
      setTimeout(() => setSaveStatus('idle'), 5000)
    },
  })

  const resetMutation = useMutation({
    mutationFn: api.resetViabilityConfig,
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ['viability-config'] })
      setDraft(null) // will re-initialize from fresh query
      setSaveStatus('saved')
      setTimeout(() => setSaveStatus('idle'), 3000)
    },
  })

  const updateField = useCallback((key: string, value: number) => {
    setDraft(prev => prev ? { ...prev, [key]: value } : prev)
    setSaveStatus('idle')
  }, [])

  const weightSum = draft
    ? WEIGHT_FIELDS.reduce((sum, f) => sum + (draft[f.key] || 0), 0)
    : 0
  const weightsValid = Math.abs(weightSum - 1.0) < 0.001

  const handleSave = () => {
    if (!draft) return
    const payload: Record<string, unknown> = {}
    for (const f of HARD_FAILURE_FIELDS) {
      payload[f.key] = f.format === 'integer' ? Math.round(draft[f.key]) : String(draft[f.key])
    }
    for (const f of WEIGHT_FIELDS) {
      payload[f.key] = String(draft[f.key])
    }
    for (const f of TIER_FIELDS) {
      payload[f.key] = Math.round(draft[f.key])
    }
    payload['enabled'] = draft['enabled'] === 1
    saveMutation.mutate(payload)
  }

  const hasChanges = config && draft ? (() => {
    for (const f of [...HARD_FAILURE_FIELDS, ...WEIGHT_FIELDS, ...TIER_FIELDS]) {
      const orig = getFieldValue(config, f.key)
      const curr = draft[f.key]
      if (Math.abs(orig - curr) > 0.0001) return true
    }
    const origEnabled = config.enabled ? 1 : 0
    if (origEnabled !== draft['enabled']) return true
    return false
  })() : false

  if (isLoading) {
    return (
      <div className="space-y-6">
        <h1 className="text-2xl font-bold">Settings</h1>
        <div className="text-gray-400">Loading configuration...</div>
      </div>
    )
  }

  if (!config || !draft) {
    return (
      <div className="space-y-6">
        <h1 className="text-2xl font-bold">Settings</h1>
        <div className="text-red-400">Failed to load configuration.</div>
      </div>
    )
  }

  return (
    <div className="space-y-6 max-w-4xl">
      {/* Header */}
      <div className="flex items-center justify-between">
        <div>
          <h1 className="text-2xl font-bold">Settings</h1>
          <p className="text-sm text-gray-400 mt-1">
            Viability scoring configuration
            {config.source === 'database' && (
              <span className="ml-2 text-xs px-2 py-0.5 rounded bg-blue-900/40 text-blue-300">
                Customized
              </span>
            )}
            {config.source === 'defaults' && (
              <span className="ml-2 text-xs px-2 py-0.5 rounded bg-gray-700 text-gray-400">
                Using defaults
              </span>
            )}
          </p>
        </div>
        <div className="flex items-center gap-3">
          {saveStatus === 'saved' && (
            <span className="flex items-center gap-1 text-sm text-green-400">
              <CheckCircle className="w-4 h-4" /> Saved
            </span>
          )}
          {saveStatus === 'error' && (
            <span className="flex items-center gap-1 text-sm text-red-400">
              <AlertTriangle className="w-4 h-4" /> Failed to save
            </span>
          )}
          <button
            onClick={() => resetMutation.mutate()}
            disabled={resetMutation.isPending || config.source === 'defaults'}
            className="flex items-center gap-2 px-3 py-2 bg-gray-700 hover:bg-gray-600 rounded text-sm text-gray-300 disabled:opacity-50 disabled:cursor-not-allowed"
          >
            <RotateCcw size={14} />
            Reset to Defaults
          </button>
          <button
            onClick={handleSave}
            disabled={saveMutation.isPending || !hasChanges || !weightsValid}
            className="flex items-center gap-2 px-4 py-2 bg-tao-600 hover:bg-tao-500 rounded text-sm font-medium text-white disabled:opacity-50 disabled:cursor-not-allowed"
          >
            <Save size={14} />
            {saveMutation.isPending ? 'Saving...' : 'Save & Apply'}
          </button>
        </div>
      </div>

      {/* Enable toggle */}
      <div className="bg-gray-800 rounded-lg border border-gray-700 p-4">
        <label className="flex items-center gap-3 cursor-pointer">
          <input
            type="checkbox"
            checked={draft['enabled'] === 1}
            onChange={(e) => updateField('enabled', e.target.checked ? 1 : 0)}
            className="w-4 h-4 rounded border-gray-600 bg-gray-700 text-tao-500 focus:ring-tao-500"
          />
          <div>
            <span className="text-sm font-medium text-gray-200">Enable Viability Scoring</span>
            <p className="text-xs text-gray-500">When disabled, viability scores will not be computed during strategy analysis</p>
          </div>
        </label>
      </div>

      {/* Hard Failure Thresholds */}
      <Section title="Hard Failure Thresholds" description="Subnets failing any of these checks are immediately excluded (Tier 4).">
        <div className="grid grid-cols-1 md:grid-cols-2 gap-4">
          {HARD_FAILURE_FIELDS.map(f => (
            <FieldControl
              key={f.key}
              field={f}
              value={draft[f.key]}
              onChange={(v) => updateField(f.key, v)}
            />
          ))}
        </div>
      </Section>

      {/* Metric Weights */}
      <Section
        title="Metric Weights"
        description="Relative importance of each scored metric. Must sum to 1.0."
      >
        <div className="mb-3">
          <div className="flex items-center gap-2 text-sm">
            <span className="text-gray-400">Weight Total:</span>
            <span className={`font-mono font-medium ${weightsValid ? 'text-green-400' : 'text-red-400'}`}>
              {weightSum.toFixed(2)}
            </span>
            {!weightsValid && (
              <span className="flex items-center gap-1 text-xs text-red-400">
                <AlertTriangle className="w-3 h-3" /> Must equal 1.00
              </span>
            )}
          </div>
          {/* Visual weight bar */}
          <div className="mt-2 flex h-3 rounded-full overflow-hidden bg-gray-700">
            {WEIGHT_FIELDS.map((f, i) => {
              const pct = (draft[f.key] / Math.max(weightSum, 0.01)) * 100
              const colors = ['bg-emerald-500', 'bg-blue-500', 'bg-purple-500', 'bg-amber-500', 'bg-cyan-500', 'bg-rose-500']
              return (
                <div
                  key={f.key}
                  className={`${colors[i]} transition-all`}
                  style={{ width: `${pct}%` }}
                  title={`${f.label}: ${(draft[f.key] * 100).toFixed(0)}%`}
                />
              )
            })}
          </div>
          <div className="mt-1 flex flex-wrap gap-x-4 gap-y-0.5">
            {WEIGHT_FIELDS.map((f, i) => {
              const colors = ['text-emerald-400', 'text-blue-400', 'text-purple-400', 'text-amber-400', 'text-cyan-400', 'text-rose-400']
              return (
                <span key={f.key} className={`text-xs ${colors[i]}`}>
                  {f.label}: {(draft[f.key] * 100).toFixed(0)}%
                </span>
              )
            })}
          </div>
        </div>
        <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-3 gap-4">
          {WEIGHT_FIELDS.map(f => (
            <FieldControl
              key={f.key}
              field={f}
              value={draft[f.key]}
              onChange={(v) => updateField(f.key, v)}
            />
          ))}
        </div>
      </Section>

      {/* Tier Boundaries */}
      <Section title="Tier Boundaries" description="Score thresholds that determine tier classification.">
        <div className="grid grid-cols-1 md:grid-cols-2 gap-4">
          {TIER_FIELDS.map(f => (
            <FieldControl
              key={f.key}
              field={f}
              value={draft[f.key]}
              onChange={(v) => updateField(f.key, v)}
            />
          ))}
        </div>
        {/* Tier preview bar */}
        <div className="mt-4 flex h-6 rounded-full overflow-hidden text-xs font-medium">
          <div className="bg-emerald-600/60 flex items-center justify-center" style={{ width: `${100 - draft['tier_1_min']}%` }}>
            {100 - draft['tier_1_min'] > 8 && `Prime (${draft['tier_1_min']}-100)`}
          </div>
          <div className="bg-green-600/60 flex items-center justify-center" style={{ width: `${draft['tier_1_min'] - draft['tier_2_min']}%` }}>
            {draft['tier_1_min'] - draft['tier_2_min'] > 8 && `Eligible (${draft['tier_2_min']}-${draft['tier_1_min'] - 1})`}
          </div>
          <div className="bg-yellow-600/60 flex items-center justify-center" style={{ width: `${draft['tier_2_min'] - draft['tier_3_min']}%` }}>
            {draft['tier_2_min'] - draft['tier_3_min'] > 8 && `Watch (${draft['tier_3_min']}-${draft['tier_2_min'] - 1})`}
          </div>
          <div className="bg-red-600/60 flex items-center justify-center" style={{ width: `${draft['tier_3_min']}%` }}>
            {draft['tier_3_min'] > 8 && `Excluded (0-${draft['tier_3_min'] - 1})`}
          </div>
        </div>
      </Section>

      {/* Info note */}
      <div className="flex items-start gap-3 p-4 bg-gray-800/50 rounded-lg border border-gray-700 text-sm text-gray-400">
        <Info className="w-4 h-4 mt-0.5 flex-shrink-0" />
        <div>
          <p>Changes take effect on the next strategy analysis run. To re-score immediately after saving, trigger a strategy analysis from the sidebar refresh button or the Strategy page.</p>
          {config.updated_at && (
            <p className="mt-1 text-xs text-gray-500">
              Last updated: {new Date(config.updated_at).toLocaleString()}
            </p>
          )}
        </div>
      </div>

      {/* Backtest Section */}
      <BacktestSection />

      {/* Portfolio Simulation */}
      <PortfolioSimSection />
    </div>
  )
}

const TIER_LABELS: Record<string, string> = {
  tier_1: 'Tier 1 (Prime)',
  tier_2: 'Tier 2 (Eligible)',
  tier_3: 'Tier 3 (Watchlist)',
  tier_4: 'Tier 4 (Excluded)',
}
const TIER_COLORS: Record<string, string> = {
  tier_1: 'text-emerald-400',
  tier_2: 'text-green-400',
  tier_3: 'text-yellow-400',
  tier_4: 'text-red-400',
}
const TIER_BG: Record<string, string> = {
  tier_1: 'bg-emerald-900/30 border-emerald-700/50',
  tier_2: 'bg-green-900/30 border-green-700/50',
  tier_3: 'bg-yellow-900/30 border-yellow-700/50',
  tier_4: 'bg-red-900/30 border-red-700/50',
}

function fmtPct(v: number | null | undefined): string {
  if (v == null) return '--'
  return `${v >= 0 ? '+' : ''}${(v * 100).toFixed(2)}%`
}

function fmtWr(v: number | null | undefined): string {
  if (v == null) return '--'
  return `${(v * 100).toFixed(0)}%`
}

function ReturnCell({ value }: { value: number | null | undefined }) {
  if (value == null) return <span className="text-gray-600">--</span>
  const color = value >= 0 ? 'text-green-400' : 'text-red-400'
  return <span className={`font-mono ${color}`}>{fmtPct(value)}</span>
}

function BacktestSection() {
  const [backtestData, setBacktestData] = useState<BacktestResult | null>(null)
  const [isRunning, setIsRunning] = useState(false)
  const [error, setError] = useState<string | null>(null)
  const [intervalDays, setIntervalDays] = useState(3)

  // Backfill state
  const [backfillStatus, setBackfillStatus] = useState<BackfillStatus | null>(null)
  const [isBackfilling, setIsBackfilling] = useState(false)
  const pollRef = useRef<ReturnType<typeof setInterval> | null>(null)

  const runBacktest = async () => {
    setIsRunning(true)
    setError(null)
    try {
      const data = await api.runBacktest(intervalDays)
      setBacktestData(data)
    } catch (e: unknown) {
      setError(e instanceof Error ? e.message : 'Backtest failed')
    } finally {
      setIsRunning(false)
    }
  }

  const triggerBackfill = async () => {
    try {
      await api.triggerBackfill(365)
      setIsBackfilling(true)
      // Start polling for status
      pollRef.current = setInterval(async () => {
        try {
          const status = await api.getBackfillStatus()
          setBackfillStatus(status)
          if (!status.running) {
            setIsBackfilling(false)
            if (pollRef.current) clearInterval(pollRef.current)
            pollRef.current = null
          }
        } catch {
          // ignore polling errors
        }
      }, 3000)
    } catch (e: unknown) {
      setError(e instanceof Error ? e.message : 'Backfill trigger failed')
    }
  }

  // Check backfill status on mount
  useEffect(() => {
    const checkStatus = async () => {
      try {
        const status = await api.getBackfillStatus()
        setBackfillStatus(status)
        if (status.running) {
          setIsBackfilling(true)
          pollRef.current = setInterval(async () => {
            try {
              const s = await api.getBackfillStatus()
              setBackfillStatus(s)
              if (!s.running) {
                setIsBackfilling(false)
                if (pollRef.current) clearInterval(pollRef.current)
                pollRef.current = null
              }
            } catch { /* ignore */ }
          }, 3000)
        }
      } catch { /* ignore */ }
    }
    checkStatus()
    return () => {
      if (pollRef.current) clearInterval(pollRef.current)
    }
  }, [])

  const hardFailRate = backtestData?.tier_separation?.hard_failure_rate
  const totalObs = backtestData ? Object.values(backtestData.summary).reduce((sum, s) => sum + s.count, 0) : 0
  const passObs = backtestData ? totalObs - (backtestData.summary.tier_4?.count || 0) : 0

  return (
    <Section title="Backtest Validation" description="Replay viability scoring against historical data to validate tier quality.">
      {/* Historical Data Backfill */}
      <div className="bg-gray-900/40 rounded-lg p-4 border border-gray-700/50 space-y-3">
        <div className="flex items-center justify-between">
          <div>
            <h4 className="text-sm font-medium text-gray-200">Historical Data</h4>
            <p className="text-xs text-gray-500 mt-0.5">
              Fetch daily pool snapshots from TaoStats for deeper backtesting (up to 12 months).
            </p>
          </div>
          <button
            onClick={triggerBackfill}
            disabled={isBackfilling}
            className="flex items-center gap-2 px-3 py-1.5 bg-gray-700 hover:bg-gray-600 rounded text-sm text-gray-300 disabled:opacity-50 whitespace-nowrap"
          >
            {isBackfilling ? <Loader2 size={14} className="animate-spin" /> : <Download size={14} />}
            {isBackfilling ? 'Backfilling...' : 'Fetch History'}
          </button>
        </div>
        {backfillStatus && (
          <div className="text-xs text-gray-400 space-y-1">
            {backfillStatus.running ? (
              <div className="space-y-1.5">
                <div className="flex items-center gap-2">
                  <Loader2 size={12} className="animate-spin text-tao-400" />
                  <span>Processing subnet {backfillStatus.current_netuid} ({backfillStatus.completed_subnets}/{backfillStatus.total_subnets})</span>
                </div>
                <div className="w-full bg-gray-700 rounded-full h-1.5">
                  <div
                    className="bg-tao-500 h-1.5 rounded-full transition-all"
                    style={{ width: `${backfillStatus.total_subnets > 0 ? (backfillStatus.completed_subnets / backfillStatus.total_subnets) * 100 : 0}%` }}
                  />
                </div>
                <span className="text-gray-500">{backfillStatus.total_records_created.toLocaleString()} records created</span>
              </div>
            ) : backfillStatus.finished_at ? (
              <div className="flex items-center gap-2">
                <CheckCircle size={12} className="text-green-400" />
                <span>
                  Last backfill: {backfillStatus.total_records_created.toLocaleString()} records created
                  {backfillStatus.errors.length > 0 && `, ${backfillStatus.errors.length} errors`}
                </span>
              </div>
            ) : null}
          </div>
        )}
      </div>

      {/* Run controls */}
      <div className="flex items-center justify-between">
        <div className="flex items-center gap-3">
          <p className="text-sm text-gray-400">
            Scores subnets at each historical date, then measures forward price performance per tier.
          </p>
        </div>
        <div className="flex items-center gap-2">
          <select
            value={intervalDays}
            onChange={(e) => setIntervalDays(Number(e.target.value))}
            className="bg-gray-700 border border-gray-600 rounded px-2 py-1.5 text-sm text-gray-300"
          >
            <option value={1}>Every day</option>
            <option value={3}>Every 3 days</option>
            <option value={7}>Weekly</option>
          </select>
          <button
            onClick={runBacktest}
            disabled={isRunning}
            className="flex items-center gap-2 px-4 py-2 bg-tao-600 hover:bg-tao-500 rounded text-sm font-medium text-white disabled:opacity-50 whitespace-nowrap"
          >
            <Play size={14} />
            {isRunning ? 'Running...' : 'Run Backtest'}
          </button>
        </div>
      </div>

      {error && (
        <div className="text-sm text-red-400 bg-red-900/20 rounded p-3 flex items-center gap-2">
          <AlertTriangle className="w-4 h-4" /> {error}
        </div>
      )}

      {backtestData && (
        <div className="space-y-4 mt-2">
          {/* Data range + summary stats */}
          <div className="flex items-center justify-between text-xs text-gray-500">
            <span>
              Data: {backtestData.data_range.start} to {backtestData.data_range.end}
              {' '}&middot;{' '}{backtestData.scoring_dates.length} scoring dates
              {' '}&middot;{' '}{totalObs.toLocaleString()} observations
            </span>
            {hardFailRate != null && (
              <span className="text-gray-400">
                Pass rate: <span className="font-mono">{((1 - hardFailRate) * 100).toFixed(1)}%</span>
                {' '}({passObs.toLocaleString()} scored)
              </span>
            )}
          </div>

          {/* Tier performance table */}
          <div className="overflow-x-auto">
            <table className="w-full text-sm">
              <thead>
                <tr className="border-b border-gray-700">
                  <th className="text-left py-2 text-gray-400 font-medium">Tier</th>
                  <th className="text-right py-2 text-gray-400 font-medium">Count</th>
                  <th className="text-right py-2 text-gray-400 font-medium">Median 1d</th>
                  <th className="text-right py-2 text-gray-400 font-medium">Median 3d</th>
                  <th className="text-right py-2 text-gray-400 font-medium">Median 7d</th>
                  <th className="text-right py-2 text-gray-400 font-medium">Win 1d</th>
                  <th className="text-right py-2 text-gray-400 font-medium">Win 3d</th>
                  <th className="text-right py-2 text-gray-400 font-medium">Win 7d</th>
                </tr>
              </thead>
              <tbody>
                {['tier_1', 'tier_2', 'tier_3', 'tier_4'].map(tier => {
                  const s = backtestData.summary[tier]
                  if (!s) return null
                  return (
                    <tr key={tier} className={`border-b border-gray-800 ${TIER_BG[tier]}`}>
                      <td className={`py-2 font-medium ${TIER_COLORS[tier]}`}>{TIER_LABELS[tier]}</td>
                      <td className="text-right py-2 font-mono text-gray-300">{s.count.toLocaleString()}</td>
                      <td className="text-right py-2"><ReturnCell value={s.median_return_1d} /></td>
                      <td className="text-right py-2"><ReturnCell value={s.median_return_3d} /></td>
                      <td className="text-right py-2"><ReturnCell value={s.median_return_7d} /></td>
                      <td className="text-right py-2 font-mono text-gray-300">{fmtWr(s.win_rate_1d)}</td>
                      <td className="text-right py-2 font-mono text-gray-300">{fmtWr(s.win_rate_3d)}</td>
                      <td className="text-right py-2 font-mono text-gray-300">{fmtWr(s.win_rate_7d)}</td>
                    </tr>
                  )
                })}
              </tbody>
            </table>
          </div>

          {/* Tier separation cards — median return and win rate */}
          <div>
            <h4 className="text-xs font-semibold text-gray-400 uppercase tracking-wider mb-2">T1 vs T4 Separation</h4>
            <div className="grid grid-cols-3 gap-3">
              {[1, 3, 7].map(h => {
                const medKey = `tier1_vs_tier4_median_${h}d`
                const wrKey = `tier1_vs_tier4_winrate_${h}d`
                const medVal = backtestData.tier_separation[medKey]
                const wrVal = backtestData.tier_separation[wrKey]
                const medPositive = medVal != null && medVal > 0
                const wrPositive = wrVal != null && wrVal > 0
                return (
                  <div key={h} className="bg-gray-900/60 rounded-lg p-3 border border-gray-700">
                    <div className="text-xs text-gray-500 mb-2 text-center">{h}-day horizon</div>
                    <div className="grid grid-cols-2 gap-2">
                      <div className="text-center">
                        <div className="text-[10px] text-gray-600 uppercase">Median</div>
                        <div className={`text-sm font-mono font-semibold ${medVal == null ? 'text-gray-600' : medPositive ? 'text-green-400' : 'text-red-400'}`}>
                          {medVal == null ? '--' : fmtPct(medVal)}
                        </div>
                        <div className="mt-0.5">
                          {medPositive ? (
                            <TrendingUp className="w-3 h-3 text-green-500 inline" />
                          ) : medVal != null ? (
                            <TrendingDown className="w-3 h-3 text-red-500 inline" />
                          ) : null}
                        </div>
                      </div>
                      <div className="text-center">
                        <div className="text-[10px] text-gray-600 uppercase">Win Rate</div>
                        <div className={`text-sm font-mono font-semibold ${wrVal == null ? 'text-gray-600' : wrPositive ? 'text-green-400' : 'text-red-400'}`}>
                          {wrVal == null ? '--' : `${wrVal >= 0 ? '+' : ''}${(wrVal * 100).toFixed(1)}pp`}
                        </div>
                        <div className="mt-0.5">
                          {wrPositive ? (
                            <TrendingUp className="w-3 h-3 text-green-500 inline" />
                          ) : wrVal != null ? (
                            <TrendingDown className="w-3 h-3 text-red-500 inline" />
                          ) : null}
                        </div>
                      </div>
                    </div>
                  </div>
                )
              })}
            </div>
          </div>

          {/* Daily tier distribution */}
          {backtestData.daily_results.length > 0 && (
            <div>
              <h4 className="text-xs font-semibold text-gray-400 uppercase tracking-wider mb-2">Daily Tier Distribution</h4>
              <div className="space-y-1 max-h-[300px] overflow-y-auto">
                {backtestData.daily_results.map(day => {
                  const total = Object.values(day.tier_counts).reduce((a, b) => a + b, 0) || 1
                  return (
                    <div key={day.date} className="flex items-center gap-2 text-xs">
                      <span className="text-gray-500 w-20 font-mono">{day.date}</span>
                      <div className="flex-1 flex h-4 rounded overflow-hidden bg-gray-800">
                        <div className="bg-emerald-600/60" style={{ width: `${(day.tier_counts.tier_1 || 0) / total * 100}%` }} title={`T1: ${day.tier_counts.tier_1 || 0}`} />
                        <div className="bg-green-600/60" style={{ width: `${(day.tier_counts.tier_2 || 0) / total * 100}%` }} title={`T2: ${day.tier_counts.tier_2 || 0}`} />
                        <div className="bg-yellow-600/50" style={{ width: `${(day.tier_counts.tier_3 || 0) / total * 100}%` }} title={`T3: ${day.tier_counts.tier_3 || 0}`} />
                        <div className="bg-red-600/40" style={{ width: `${(day.tier_counts.tier_4 || 0) / total * 100}%` }} title={`T4: ${day.tier_counts.tier_4 || 0}`} />
                      </div>
                      <span className="text-gray-600 w-28 text-right">
                        {day.tier_counts.tier_1 || 0}/{day.tier_counts.tier_2 || 0}/{day.tier_counts.tier_3 || 0}/{day.tier_counts.tier_4 || 0}
                      </span>
                    </div>
                  )
                })}
              </div>
              <div className="flex gap-4 mt-1 text-xs text-gray-600">
                <span><span className="inline-block w-2 h-2 rounded bg-emerald-600 mr-1" />T1</span>
                <span><span className="inline-block w-2 h-2 rounded bg-green-600 mr-1" />T2</span>
                <span><span className="inline-block w-2 h-2 rounded bg-yellow-600 mr-1" />T3</span>
                <span><span className="inline-block w-2 h-2 rounded bg-red-600 mr-1" />T4</span>
              </div>
            </div>
          )}

          {/* Interpretation note */}
          <div className="flex items-start gap-2 text-xs text-gray-500 mt-2">
            <Info className="w-3 h-3 mt-0.5 flex-shrink-0" />
            <span>
              Positive T1-vs-T4 separation = the model adds value. Median returns resist outlier distortion.
              Win rate delta shows the probability edge of picking Tier 1 over Tier 4 subnets.
              Adjust weights and thresholds above, then re-run to see the effect.
            </span>
          </div>
        </div>
      )}
    </Section>
  )
}

const TIER_OPTIONS = [
  { key: 'tier_1', label: 'T1 (Prime)', color: 'text-emerald-400', bg: 'bg-emerald-600', border: 'border-emerald-500' },
  { key: 'tier_2', label: 'T2 (Eligible)', color: 'text-green-400', bg: 'bg-green-600', border: 'border-green-500' },
  { key: 'tier_3', label: 'T3 (Watchlist)', color: 'text-yellow-400', bg: 'bg-yellow-600', border: 'border-yellow-500' },
] as const

function PortfolioSimSection() {
  const [simData, setSimData] = useState<PortfolioSimResult | null>(null)
  const [isRunning, setIsRunning] = useState(false)
  const [error, setError] = useState<string | null>(null)
  const [intervalDays, setIntervalDays] = useState(3)
  const [expandedPeriod, setExpandedPeriod] = useState<string | null>(null)

  // Multi-tier state: which tiers are selected and their weight %
  const [selectedTiers, setSelectedTiers] = useState<Record<string, boolean>>({
    tier_1: true,
    tier_2: false,
    tier_3: false,
  })
  const [tierPcts, setTierPcts] = useState<Record<string, number>>({
    tier_1: 100,
    tier_2: 0,
    tier_3: 0,
  })

  const activeTiers = Object.entries(selectedTiers).filter(([, v]) => v).map(([k]) => k)
  const totalPct = activeTiers.reduce((sum, t) => sum + (tierPcts[t] || 0), 0)
  const weightsValid = activeTiers.length > 0 && Math.abs(totalPct - 100) < 0.5

  const toggleTier = (tier: string) => {
    const next = { ...selectedTiers, [tier]: !selectedTiers[tier] }
    setSelectedTiers(next)
    // Auto-distribute weights evenly when toggling
    const active = Object.entries(next).filter(([, v]) => v).map(([k]) => k)
    if (active.length > 0) {
      const even = Math.round(100 / active.length)
      const pcts: Record<string, number> = {}
      active.forEach((t, i) => {
        pcts[t] = i === active.length - 1 ? 100 - even * (active.length - 1) : even
      })
      // Keep unselected at 0
      for (const t of Object.keys(next)) {
        if (!next[t]) pcts[t] = 0
      }
      setTierPcts(prev => ({ ...prev, ...pcts }))
    }
  }

  const runSim = async () => {
    setIsRunning(true)
    setError(null)
    try {
      // Build tier_weights from selections
      const weights: Record<string, number> = {}
      for (const t of activeTiers) {
        weights[t] = (tierPcts[t] || 0) / 100
      }
      const data = await api.simulatePortfolio(intervalDays, 'tier_1', undefined, 100, weights)
      setSimData(data)
    } catch (e: unknown) {
      setError(e instanceof Error ? e.message : 'Simulation failed')
    } finally {
      setIsRunning(false)
    }
  }

  // Format the tier allocation label for display
  const allocationLabel = activeTiers.length === 0
    ? 'No tiers selected'
    : activeTiers.map(t => {
        const opt = TIER_OPTIONS.find(o => o.key === t)
        return `${opt?.label ?? t} ${tierPcts[t]}%`
      }).join(' + ')

  return (
    <Section title="Portfolio Simulation" description="Simulate a multi-tier weighted portfolio, rebalancing at each interval.">
      {/* Tier selection + weight controls */}
      <div className="bg-gray-900/40 rounded-lg p-4 border border-gray-700/50 space-y-3">
        <div className="flex items-center justify-between">
          <div>
            <h4 className="text-sm font-medium text-gray-200">Tier Allocation</h4>
            <p className="text-xs text-gray-500 mt-0.5">
              Select tiers to include and set weight for each. Weights must total 100%.
            </p>
          </div>
          {!weightsValid && activeTiers.length > 0 && (
            <span className="flex items-center gap-1 text-xs text-red-400">
              <AlertTriangle className="w-3 h-3" /> Total: {totalPct}% (must be 100%)
            </span>
          )}
        </div>

        <div className="grid grid-cols-3 gap-3">
          {TIER_OPTIONS.map(opt => {
            const selected = selectedTiers[opt.key]
            return (
              <div
                key={opt.key}
                className={`rounded-lg border p-3 transition-all ${
                  selected
                    ? `${opt.border} bg-gray-800/80`
                    : 'border-gray-700 bg-gray-800/30 opacity-60'
                }`}
              >
                <label className="flex items-center gap-2 cursor-pointer">
                  <input
                    type="checkbox"
                    checked={selected}
                    onChange={() => toggleTier(opt.key)}
                    className="w-4 h-4 rounded border-gray-600 bg-gray-700 text-tao-500 focus:ring-tao-500"
                  />
                  <span className={`text-sm font-medium ${opt.color}`}>{opt.label}</span>
                </label>
                {selected && (
                  <div className="mt-2 flex items-center gap-2">
                    <input
                      type="range"
                      min={5}
                      max={100}
                      step={5}
                      value={tierPcts[opt.key] || 0}
                      onChange={(e) => setTierPcts(prev => ({ ...prev, [opt.key]: Number(e.target.value) }))}
                      className="flex-1 h-1.5 bg-gray-700 rounded-lg appearance-none cursor-pointer accent-tao-500"
                    />
                    <input
                      type="number"
                      min={5}
                      max={100}
                      step={5}
                      value={tierPcts[opt.key] || 0}
                      onChange={(e) => setTierPcts(prev => ({ ...prev, [opt.key]: Number(e.target.value) }))}
                      className="w-14 bg-gray-700 border border-gray-600 rounded px-1.5 py-0.5 text-sm text-center text-gray-300 font-mono"
                    />
                    <span className="text-xs text-gray-500">%</span>
                  </div>
                )}
              </div>
            )
          })}
        </div>

        {/* Visual weight bar */}
        {activeTiers.length > 0 && (
          <div className="flex h-2.5 rounded-full overflow-hidden bg-gray-700">
            {TIER_OPTIONS.filter(o => selectedTiers[o.key]).map(opt => (
              <div
                key={opt.key}
                className={`${opt.bg} transition-all`}
                style={{ width: `${totalPct > 0 ? (tierPcts[opt.key] / totalPct) * 100 : 0}%` }}
                title={`${opt.label}: ${tierPcts[opt.key]}%`}
              />
            ))}
          </div>
        )}
      </div>

      {/* Run controls */}
      <div className="flex items-center justify-between">
        <p className="text-sm text-gray-400">
          {allocationLabel}
        </p>
        <div className="flex items-center gap-2">
          <select
            value={intervalDays}
            onChange={(e) => setIntervalDays(Number(e.target.value))}
            className="bg-gray-700 border border-gray-600 rounded px-2 py-1.5 text-sm text-gray-300"
          >
            <option value={1}>Daily rebal</option>
            <option value={3}>3-day rebal</option>
            <option value={7}>Weekly rebal</option>
          </select>
          <button
            onClick={runSim}
            disabled={isRunning || !weightsValid}
            className="flex items-center gap-2 px-4 py-2 bg-tao-600 hover:bg-tao-500 rounded text-sm font-medium text-white disabled:opacity-50 whitespace-nowrap"
          >
            <Play size={14} />
            {isRunning ? 'Running...' : 'Simulate'}
          </button>
        </div>
      </div>

      {error && (
        <div className="text-sm text-red-400 bg-red-900/20 rounded p-3 flex items-center gap-2">
          <AlertTriangle className="w-4 h-4" /> {error}
        </div>
      )}

      {simData && (
        <div className="space-y-4 mt-2">
          {/* Summary cards */}
          <div className="grid grid-cols-4 gap-3">
            <StatCard
              label="Total Return"
              value={`${simData.total_return >= 0 ? '+' : ''}${(simData.total_return * 100).toFixed(1)}%`}
              sub={`${simData.initial_capital} → ${simData.final_value.toFixed(1)} TAO`}
              color={simData.total_return >= 0 ? 'text-green-400' : 'text-red-400'}
            />
            <StatCard
              label="Win Rate"
              value={`${(simData.summary.win_rate * 100).toFixed(0)}%`}
              sub={`${simData.num_periods} periods`}
              color={simData.summary.win_rate > 0.5 ? 'text-green-400' : 'text-yellow-400'}
            />
            <StatCard
              label="Max Drawdown"
              value={`-${(simData.summary.max_drawdown_pct * 100).toFixed(1)}%`}
              sub={`${simData.periods_in_root} periods in root`}
              color="text-red-400"
            />
            <StatCard
              label="Avg Holdings"
              value={`${simData.summary.avg_holdings_per_period}`}
              sub={`per ${intervalDays}d period`}
              color="text-gray-300"
            />
          </div>

          {/* Equity curve */}
          <div>
            <h4 className="text-xs font-semibold text-gray-400 uppercase tracking-wider mb-2">
              Equity Curve ({simData.start_date} to {simData.end_date})
            </h4>
            <EquityCurveChart data={simData.equity_curve} initial={simData.initial_capital} />
          </div>

          {/* Period details table */}
          <div>
            <h4 className="text-xs font-semibold text-gray-400 uppercase tracking-wider mb-2">
              Period Details (click to expand)
            </h4>
            <div className="max-h-[400px] overflow-y-auto space-y-0.5">
              {simData.periods.map(period => (
                <div key={period.date}>
                  <button
                    onClick={() => setExpandedPeriod(expandedPeriod === period.date ? null : period.date)}
                    className="w-full flex items-center gap-2 text-xs py-1.5 px-2 rounded hover:bg-gray-700/50 text-left"
                  >
                    <span className="font-mono text-gray-500 w-20">{period.date}</span>
                    <span className={`font-mono w-16 text-right ${period.period_return >= 0 ? 'text-green-400' : 'text-red-400'}`}>
                      {period.in_root ? '--' : fmtPct(period.period_return)}
                    </span>
                    <span className="font-mono text-gray-400 w-20 text-right">{period.portfolio_value.toFixed(1)} TAO</span>
                    <span className="text-gray-600 flex-1 text-right">
                      {period.in_root ? 'Root (no picks)' : `${period.holdings.length} holdings`}
                    </span>
                  </button>
                  {expandedPeriod === period.date && period.holdings.length > 0 && (
                    <div className="ml-6 mb-2 bg-gray-900/40 rounded p-2 text-xs space-y-1">
                      {period.holdings.map(h => (
                        <div key={h.netuid} className="flex items-center gap-3">
                          <span className="text-gray-400 w-12">SN{h.netuid}</span>
                          <span className="text-gray-300 flex-1 truncate">{h.name}</span>
                          {h.tier && (
                            <span className={`text-[10px] px-1.5 py-0.5 rounded ${
                              h.tier === 'tier_1' ? 'bg-emerald-900/40 text-emerald-400' :
                              h.tier === 'tier_2' ? 'bg-green-900/40 text-green-400' :
                              'bg-yellow-900/40 text-yellow-400'
                            }`}>
                              {h.tier === 'tier_1' ? 'T1' : h.tier === 'tier_2' ? 'T2' : 'T3'}
                            </span>
                          )}
                          <span className="text-gray-500 font-mono">{h.score ?? '--'}</span>
                          <span className="text-gray-500 font-mono">{(h.weight * 100).toFixed(0)}%</span>
                          <span className={`font-mono w-16 text-right ${h.return_pct >= 0 ? 'text-green-400' : 'text-red-400'}`}>
                            {fmtPct(h.return_pct)}
                          </span>
                        </div>
                      ))}
                    </div>
                  )}
                </div>
              ))}
            </div>
          </div>

          <div className="flex items-start gap-2 text-xs text-gray-500 mt-2">
            <Info className="w-3 h-3 mt-0.5 flex-shrink-0" />
            <span>
              Multi-tier simulation: each tier gets its designated weight share. Within each tier,
              subnets are equal-weighted. If a tier has no qualifying subnets for a period, that
              allocation is parked in root (0% return). Adjust tier selection, weights, and rebalance
              frequency above and re-run.
            </span>
          </div>
        </div>
      )}
    </Section>
  )
}

function StatCard({ label, value, sub, color }: { label: string; value: string; sub: string; color: string }) {
  return (
    <div className="bg-gray-900/60 rounded-lg p-3 border border-gray-700">
      <div className="text-xs text-gray-500">{label}</div>
      <div className={`text-xl font-mono font-bold mt-1 ${color}`}>{value}</div>
      <div className="text-[10px] text-gray-600 mt-0.5">{sub}</div>
    </div>
  )
}

function EquityCurveChart({ data, initial }: { data: { date: string; value: number; in_root: boolean; num_holdings: number }[]; initial: number }) {
  if (data.length < 2) return null

  const maxVal = Math.max(...data.map(d => d.value))
  const minVal = Math.min(...data.map(d => d.value))
  const range = maxVal - minVal || 1

  const width = 800
  const height = 200
  const padL = 50
  const padR = 10
  const padT = 10
  const padB = 25
  const chartW = width - padL - padR
  const chartH = height - padT - padB

  const points = data.map((d, i) => {
    const x = padL + (i / (data.length - 1)) * chartW
    const y = padT + chartH - ((d.value - minVal) / range) * chartH
    return { x, y, ...d }
  })

  const linePath = points.map((p, i) => `${i === 0 ? 'M' : 'L'}${p.x},${p.y}`).join(' ')

  // Fill area under curve
  const areaPath = linePath + ` L${points[points.length - 1].x},${padT + chartH} L${points[0].x},${padT + chartH} Z`

  // Reference line at initial capital
  const refY = padT + chartH - ((initial - minVal) / range) * chartH

  // Y axis labels
  const yLabels = [minVal, initial, maxVal].map(v => ({
    val: v,
    y: padT + chartH - ((v - minVal) / range) * chartH,
    label: v.toFixed(0),
  }))

  // X axis labels (show ~5 dates)
  const step = Math.max(1, Math.floor(data.length / 5))
  const xLabels = data.filter((_, i) => i % step === 0 || i === data.length - 1).map((d) => ({
    x: padL + (data.indexOf(d) / (data.length - 1)) * chartW,
    label: d.date.slice(5), // MM-DD
  }))

  const finalReturn = data.length > 0 ? ((data[data.length - 1].value - initial) / initial) : 0
  const curveColor = finalReturn >= 0 ? '#4ade80' : '#f87171'
  const fillColor = finalReturn >= 0 ? 'rgba(74,222,128,0.1)' : 'rgba(248,113,113,0.1)'

  return (
    <svg viewBox={`0 0 ${width} ${height}`} className="w-full" style={{ maxHeight: 240 }}>
      {/* Grid lines */}
      {yLabels.map((yl, i) => (
        <g key={i}>
          <line x1={padL} y1={yl.y} x2={width - padR} y2={yl.y} stroke="#374151" strokeWidth={0.5} strokeDasharray={yl.val === initial ? '4,2' : '0'} />
          <text x={padL - 4} y={yl.y + 3} textAnchor="end" fill="#6b7280" fontSize={10}>{yl.label}</text>
        </g>
      ))}

      {/* X axis labels */}
      {xLabels.map((xl, i) => (
        <text key={i} x={xl.x} y={height - 4} textAnchor="middle" fill="#6b7280" fontSize={9}>{xl.label}</text>
      ))}

      {/* Reference line */}
      <line x1={padL} y1={refY} x2={width - padR} y2={refY} stroke="#6b7280" strokeWidth={1} strokeDasharray="4,2" />
      <text x={padL - 4} y={refY - 5} textAnchor="end" fill="#9ca3af" fontSize={9}>start</text>

      {/* Area fill */}
      <path d={areaPath} fill={fillColor} />

      {/* Line */}
      <path d={linePath} fill="none" stroke={curveColor} strokeWidth={2} />

      {/* Root periods (gray dots) */}
      {points.filter(p => p.in_root).map((p, i) => (
        <circle key={i} cx={p.x} cy={p.y} r={3} fill="#6b7280" />
      ))}

      {/* Final value label */}
      {points.length > 0 && (
        <text
          x={points[points.length - 1].x}
          y={points[points.length - 1].y - 8}
          textAnchor="end"
          fill={curveColor}
          fontSize={11}
          fontWeight="bold"
        >
          {data[data.length - 1].value.toFixed(1)}
        </text>
      )}
    </svg>
  )
}

function Section({ title, description, children }: { title: string; description: string; children: React.ReactNode }) {
  return (
    <div className="bg-gray-800 rounded-lg border border-gray-700 p-5 space-y-4">
      <div>
        <h2 className="text-lg font-semibold text-gray-100">{title}</h2>
        <p className="text-xs text-gray-500 mt-0.5">{description}</p>
      </div>
      {children}
    </div>
  )
}

function FieldControl({ field, value, onChange }: { field: NumericField; value: number; onChange: (v: number) => void }) {
  const displayValue = formatDisplay(value, field.format)

  return (
    <div className="space-y-1.5">
      <div className="flex justify-between items-baseline">
        <label className="text-sm text-gray-300">{field.label}</label>
        <span className="text-sm font-mono text-gray-200">{displayValue}</span>
      </div>
      <input
        type="range"
        min={field.min}
        max={field.max}
        step={field.step}
        value={value}
        onChange={(e) => onChange(parseFloat(e.target.value))}
        className="w-full h-1.5 bg-gray-700 rounded-lg appearance-none cursor-pointer accent-tao-500"
      />
      <p className="text-xs text-gray-600">{field.description}</p>
    </div>
  )
}
