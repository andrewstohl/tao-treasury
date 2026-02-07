import { useState, useEffect, useCallback } from 'react'
import { Link } from 'react-router-dom'
import { useQuery, useMutation, useQueryClient } from '@tanstack/react-query'
import { Save, RotateCcw, AlertTriangle, CheckCircle, Info, FlaskConical, ArrowRight, RefreshCw, Calendar } from 'lucide-react'
import { api } from '../services/api'
import type { ViabilityConfig } from '../types'
import {
  RebalanceConfig,
  loadRebalanceConfig,
  saveRebalanceConfig,
  resetRebalanceConfig,
  getDaysUntilRebalance,
} from '../services/settingsStore'

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

  // Rebalance config (localStorage)
  const [rebalanceConfig, setRebalanceConfig] = useState<RebalanceConfig>(() => loadRebalanceConfig())
  const [rebalanceSaveStatus, setRebalanceSaveStatus] = useState<'idle' | 'saved'>('idle')
  const daysUntilRebalance = getDaysUntilRebalance()

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

  const updateRebalanceConfig = useCallback((updates: Partial<RebalanceConfig>) => {
    setRebalanceConfig(prev => ({ ...prev, ...updates }))
    setRebalanceSaveStatus('idle')
  }, [])

  const handleSaveRebalanceConfig = useCallback(() => {
    saveRebalanceConfig(rebalanceConfig)
    setRebalanceSaveStatus('saved')
    setTimeout(() => setRebalanceSaveStatus('idle'), 3000)
  }, [rebalanceConfig])

  const handleResetRebalanceConfig = useCallback(() => {
    const defaults = resetRebalanceConfig()
    setRebalanceConfig(defaults)
    setRebalanceSaveStatus('saved')
    setTimeout(() => setRebalanceSaveStatus('idle'), 3000)
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
        <div className="text-[#6f87a0]">Loading configuration...</div>
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
          <p className="text-sm text-[#6f87a0] mt-1">
            Viability scoring configuration
            {config.source === 'database' && (
              <span className="ml-2 text-xs px-2 py-0.5 rounded bg-blue-900/40 text-blue-300">
                Customized
              </span>
            )}
            {config.source === 'defaults' && (
              <span className="ml-2 text-xs px-2 py-0.5 rounded bg-[#1a2d42] text-[#6f87a0]">
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
            className="flex items-center gap-2 px-3 py-2 bg-[#1a2d42] hover:bg-[#243a52] rounded text-sm text-[#8faabe] disabled:opacity-50 disabled:cursor-not-allowed"
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
      <div className="bg-[#121f2d] rounded-lg border border-[#1e3a5f] p-4">
        <label className="flex items-center gap-3 cursor-pointer">
          <input
            type="checkbox"
            checked={draft['enabled'] === 1}
            onChange={(e) => updateField('enabled', e.target.checked ? 1 : 0)}
            className="w-4 h-4 rounded border-[#2a4a66] bg-[#1a2d42] text-tao-500 focus:ring-tao-500"
          />
          <div>
            <span className="text-sm font-medium text-[#a8c4d9]">Enable Viability Scoring</span>
            <p className="text-xs text-[#5a7a94]">When disabled, viability scores will not be computed during strategy analysis</p>
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
            <span className="text-[#6f87a0]">Weight Total:</span>
            <span className={`tabular-nums font-medium ${weightsValid ? 'text-green-400' : 'text-red-400'}`}>
              {weightSum.toFixed(2)}
            </span>
            {!weightsValid && (
              <span className="flex items-center gap-1 text-xs text-red-400">
                <AlertTriangle className="w-3 h-3" /> Must equal 1.00
              </span>
            )}
          </div>
          {/* Visual weight bar */}
          <div className="mt-2 flex h-3 rounded-full overflow-hidden bg-[#1a2d42]">
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
      <div className="flex items-start gap-3 p-4 bg-[#121f2d]/50 rounded-lg border border-[#1e3a5f] text-sm text-[#6f87a0]">
        <Info className="w-4 h-4 mt-0.5 flex-shrink-0" />
        <div>
          <p>Changes take effect on the next strategy analysis run. To re-score immediately after saving, trigger a strategy analysis from the sidebar refresh button or the Strategy page.</p>
          {config.updated_at && (
            <p className="mt-1 text-xs text-[#5a7a94]">
              Last updated: {new Date(config.updated_at).toLocaleString()}
            </p>
          )}
        </div>
      </div>

      {/* Rebalance Settings */}
      <Section
        title="Rebalance Settings"
        description="Configure automatic portfolio rebalancing schedule and thresholds."
        icon={<RefreshCw className="w-5 h-5 text-amber-400" />}
        headerRight={
          <div className="flex items-center gap-3">
            {rebalanceSaveStatus === 'saved' && (
              <span className="flex items-center gap-1 text-sm text-green-400">
                <CheckCircle className="w-4 h-4" /> Saved
              </span>
            )}
            <button
              onClick={handleResetRebalanceConfig}
              className="flex items-center gap-2 px-3 py-1.5 bg-[#1a2d42] hover:bg-[#243a52] rounded text-xs text-[#8faabe]"
            >
              <RotateCcw size={12} />
              Reset
            </button>
            <button
              onClick={handleSaveRebalanceConfig}
              className="flex items-center gap-2 px-3 py-1.5 bg-tao-600 hover:bg-tao-500 rounded text-xs font-medium text-white"
            >
              <Save size={12} />
              Save
            </button>
          </div>
        }
      >
        {/* Schedule Status */}
        <div className="flex items-center gap-4 p-3 bg-[#0a1520]/50 rounded-lg border border-[#1e3a5f]/50">
          <Calendar className="w-5 h-5 text-[#6f87a0]" />
          <div>
            <span className="text-sm text-[#a8c4d9]">
              {daysUntilRebalance === null ? (
                'No rebalance scheduled'
              ) : daysUntilRebalance <= 0 ? (
                <span className="text-amber-400">Rebalance due now</span>
              ) : (
                <>Next rebalance in <span className="text-tao-400 font-medium">{daysUntilRebalance} days</span></>
              )}
            </span>
            {rebalanceConfig.lastRebalanceDate && (
              <span className="text-xs text-[#5a7a94] ml-3">
                Last: {rebalanceConfig.lastRebalanceDate}
              </span>
            )}
          </div>
        </div>

        {/* Schedule */}
        <div className="space-y-2">
          <label className="text-sm text-[#8faabe]">Rebalance Schedule</label>
          <div className="flex gap-3">
            {[3, 7, 14].map(days => (
              <button
                key={days}
                onClick={() => updateRebalanceConfig({ rebalanceIntervalDays: days })}
                className={`px-4 py-2 rounded text-sm ${
                  rebalanceConfig.rebalanceIntervalDays === days
                    ? 'bg-tao-600 text-white'
                    : 'bg-[#1a2d42] text-[#8faabe] hover:bg-[#243a52]'
                }`}
              >
                Every {days} days {days === 3 && '(Recommended)'}
              </button>
            ))}
          </div>
        </div>

        {/* Thresholds */}
        <div className="grid grid-cols-1 md:grid-cols-2 gap-4">
          <div className="space-y-1.5">
            <div className="flex justify-between items-baseline">
              <label className="text-sm text-[#8faabe]">Position Threshold</label>
              <span className="text-sm tabular-nums text-[#a8c4d9]">{rebalanceConfig.positionThresholdPct}%</span>
            </div>
            <input
              type="range"
              min={1}
              max={10}
              step={1}
              value={rebalanceConfig.positionThresholdPct}
              onChange={(e) => updateRebalanceConfig({ positionThresholdPct: Number(e.target.value) })}
              className="w-full h-1.5 bg-[#1a2d42] rounded-lg appearance-none cursor-pointer accent-tao-500"
            />
            <p className="text-xs text-[#5a7a94]">Skip trades where position delta is below this %</p>
          </div>
          <div className="space-y-1.5">
            <div className="flex justify-between items-baseline">
              <label className="text-sm text-[#8faabe]">Portfolio Threshold</label>
              <span className="text-sm tabular-nums text-[#a8c4d9]">{rebalanceConfig.portfolioThresholdPct}%</span>
            </div>
            <input
              type="range"
              min={2}
              max={15}
              step={1}
              value={rebalanceConfig.portfolioThresholdPct}
              onChange={(e) => updateRebalanceConfig({ portfolioThresholdPct: Number(e.target.value) })}
              className="w-full h-1.5 bg-[#1a2d42] rounded-lg appearance-none cursor-pointer accent-tao-500"
            />
            <p className="text-xs text-[#5a7a94]">Skip rebalance if total portfolio drift is below this %</p>
          </div>
        </div>

        {/* Allocation Strategy */}
        <div className="space-y-2">
          <label className="text-sm text-[#8faabe]">Allocation Strategy</label>
          <div className="flex gap-3">
            <button
              onClick={() => updateRebalanceConfig({ strategy: 'equal_weight' })}
              className={`px-4 py-2 rounded text-sm ${
                rebalanceConfig.strategy === 'equal_weight'
                  ? 'bg-tao-600 text-white'
                  : 'bg-[#1a2d42] text-[#8faabe] hover:bg-[#243a52]'
              }`}
            >
              Equal Weight (Recommended)
            </button>
            <button
              onClick={() => updateRebalanceConfig({ strategy: 'fai_weighted' })}
              className={`px-4 py-2 rounded text-sm ${
                rebalanceConfig.strategy === 'fai_weighted'
                  ? 'bg-tao-600 text-white'
                  : 'bg-[#1a2d42] text-[#8faabe] hover:bg-[#243a52]'
              }`}
            >
              FAI-Weighted
            </button>
          </div>
        </div>

        {/* Selection Parameters */}
        <div className="grid grid-cols-1 md:grid-cols-2 gap-4">
          <div className="space-y-1.5">
            <div className="flex justify-between items-baseline">
              <label className="text-sm text-[#8faabe]">Top Percentile</label>
              <span className="text-sm tabular-nums text-[#a8c4d9]">{rebalanceConfig.topPercentile}%</span>
            </div>
            <input
              type="range"
              min={20}
              max={80}
              step={5}
              value={rebalanceConfig.topPercentile}
              onChange={(e) => updateRebalanceConfig({ topPercentile: Number(e.target.value) })}
              className="w-full h-1.5 bg-[#1a2d42] rounded-lg appearance-none cursor-pointer accent-tao-500"
            />
            <p className="text-xs text-[#5a7a94]">Select top N% of viable subnets by score</p>
          </div>
          <div className="space-y-1.5">
            <div className="flex justify-between items-baseline">
              <label className="text-sm text-[#8faabe]">Max Position Size</label>
              <span className="text-sm tabular-nums text-[#a8c4d9]">{rebalanceConfig.maxPositionPct}%</span>
            </div>
            <input
              type="range"
              min={5}
              max={25}
              step={2.5}
              value={rebalanceConfig.maxPositionPct}
              onChange={(e) => updateRebalanceConfig({ maxPositionPct: Number(e.target.value) })}
              className="w-full h-1.5 bg-[#1a2d42] rounded-lg appearance-none cursor-pointer accent-tao-500"
            />
            <p className="text-xs text-[#5a7a94]">Maximum weight allowed per position</p>
          </div>
        </div>

        {/* Viability Config Toggle */}
        <div className="p-4 bg-[#0a1520]/50 rounded-lg border border-[#1e3a5f]/50">
          <label className="flex items-center gap-3 cursor-pointer">
            <input
              type="checkbox"
              checked={rebalanceConfig.useBackendViabilityConfig}
              onChange={(e) => updateRebalanceConfig({ useBackendViabilityConfig: e.target.checked })}
              className="w-4 h-4 rounded border-[#2a4a66] bg-[#1a2d42] text-tao-500 focus:ring-tao-500"
            />
            <div>
              <span className="text-sm font-medium text-[#a8c4d9]">Use viability settings from above</span>
              <p className="text-xs text-[#5a7a94]">
                Inherits hard failure thresholds and scoring weights from the Viability Scoring configuration
              </p>
            </div>
          </label>
        </div>

        {/* Custom Viability Overrides (shown when not using backend config) */}
        {!rebalanceConfig.useBackendViabilityConfig && (
          <div className="space-y-4 p-4 bg-[#0a1520]/30 rounded-lg border border-amber-600/30">
            <p className="text-xs text-amber-400 flex items-center gap-2">
              <AlertTriangle className="w-4 h-4" />
              Custom viability settings for rebalancing (overrides main config)
            </p>
            <div className="grid grid-cols-2 md:grid-cols-4 gap-4">
              <div className="space-y-1">
                <label className="text-xs text-[#6f87a0]">Min Age (days)</label>
                <input
                  type="number"
                  value={rebalanceConfig.minAgeDays}
                  onChange={(e) => updateRebalanceConfig({ minAgeDays: Number(e.target.value) })}
                  className="w-full px-2 py-1 bg-[#1a2d42] border border-[#2a4a66] rounded text-sm text-[#a8c4d9]"
                />
              </div>
              <div className="space-y-1">
                <label className="text-xs text-[#6f87a0]">Min Reserve (TAO)</label>
                <input
                  type="number"
                  value={rebalanceConfig.minReserveTao}
                  onChange={(e) => updateRebalanceConfig({ minReserveTao: Number(e.target.value) })}
                  className="w-full px-2 py-1 bg-[#1a2d42] border border-[#2a4a66] rounded text-sm text-[#a8c4d9]"
                />
              </div>
              <div className="space-y-1">
                <label className="text-xs text-[#6f87a0]">Max Outflow 7d (%)</label>
                <input
                  type="number"
                  value={rebalanceConfig.maxOutflow7dPct}
                  onChange={(e) => updateRebalanceConfig({ maxOutflow7dPct: Number(e.target.value) })}
                  className="w-full px-2 py-1 bg-[#1a2d42] border border-[#2a4a66] rounded text-sm text-[#a8c4d9]"
                />
              </div>
              <div className="space-y-1">
                <label className="text-xs text-[#6f87a0]">Max Drawdown (%)</label>
                <input
                  type="number"
                  value={rebalanceConfig.maxDrawdownPct}
                  onChange={(e) => updateRebalanceConfig({ maxDrawdownPct: Number(e.target.value) })}
                  className="w-full px-2 py-1 bg-[#1a2d42] border border-[#2a4a66] rounded text-sm text-[#a8c4d9]"
                />
              </div>
            </div>
            <div className="grid grid-cols-2 md:grid-cols-4 gap-4">
              <div className="space-y-1">
                <label className="text-xs text-[#6f87a0]">FAI Weight</label>
                <input
                  type="number"
                  step="0.05"
                  min="0"
                  max="1"
                  value={rebalanceConfig.faiWeight}
                  onChange={(e) => updateRebalanceConfig({ faiWeight: Number(e.target.value) })}
                  className="w-full px-2 py-1 bg-[#1a2d42] border border-[#2a4a66] rounded text-sm text-[#a8c4d9]"
                />
              </div>
              <div className="space-y-1">
                <label className="text-xs text-[#6f87a0]">Reserve Weight</label>
                <input
                  type="number"
                  step="0.05"
                  min="0"
                  max="1"
                  value={rebalanceConfig.reserveWeight}
                  onChange={(e) => updateRebalanceConfig({ reserveWeight: Number(e.target.value) })}
                  className="w-full px-2 py-1 bg-[#1a2d42] border border-[#2a4a66] rounded text-sm text-[#a8c4d9]"
                />
              </div>
              <div className="space-y-1">
                <label className="text-xs text-[#6f87a0]">Emission Weight</label>
                <input
                  type="number"
                  step="0.05"
                  min="0"
                  max="1"
                  value={rebalanceConfig.emissionWeight}
                  onChange={(e) => updateRebalanceConfig({ emissionWeight: Number(e.target.value) })}
                  className="w-full px-2 py-1 bg-[#1a2d42] border border-[#2a4a66] rounded text-sm text-[#a8c4d9]"
                />
              </div>
              <div className="space-y-1">
                <label className="text-xs text-[#6f87a0]">Stability Weight</label>
                <input
                  type="number"
                  step="0.05"
                  min="0"
                  max="1"
                  value={rebalanceConfig.stabilityWeight}
                  onChange={(e) => updateRebalanceConfig({ stabilityWeight: Number(e.target.value) })}
                  className="w-full px-2 py-1 bg-[#1a2d42] border border-[#2a4a66] rounded text-sm text-[#a8c4d9]"
                />
              </div>
            </div>
          </div>
        )}
      </Section>

      {/* Link to Backtest Page */}
      <Link
        to="/backtest"
        className="flex items-center justify-between p-5 bg-[#121f2d] rounded-lg border border-[#1e3a5f] hover:border-tao-500/50 transition-colors group"
      >
        <div className="flex items-center gap-4">
          <div className="p-3 bg-tao-600/20 rounded-lg">
            <FlaskConical className="w-6 h-6 text-tao-400" />
          </div>
          <div>
            <h2 className="text-lg font-semibold text-white group-hover:text-tao-400 transition-colors">
              Strategy Backtesting
            </h2>
            <p className="text-sm text-[#5a7a94] mt-0.5">
              Test viability and allocation strategies against historical data
            </p>
          </div>
        </div>
        <ArrowRight className="w-5 h-5 text-[#5a7a94] group-hover:text-tao-400 transition-colors" />
      </Link>

      {/* Link to Rebalance Page */}
      <Link
        to="/recommendations"
        className="flex items-center justify-between p-5 bg-[#121f2d] rounded-lg border border-[#1e3a5f] hover:border-amber-500/50 transition-colors group"
      >
        <div className="flex items-center gap-4">
          <div className="p-3 bg-amber-600/20 rounded-lg">
            <RefreshCw className="w-6 h-6 text-amber-400" />
          </div>
          <div>
            <h2 className="text-lg font-semibold text-white group-hover:text-amber-400 transition-colors">
              Rebalance Advisor
            </h2>
            <p className="text-sm text-[#5a7a94] mt-0.5">
              Compare current portfolio to optimal target and get trade recommendations
            </p>
          </div>
        </div>
        <ArrowRight className="w-5 h-5 text-[#5a7a94] group-hover:text-amber-400 transition-colors" />
      </Link>
    </div>
  )
}


function Section({
  title,
  description,
  children,
  icon,
  headerRight,
}: {
  title: string
  description: string
  children: React.ReactNode
  icon?: React.ReactNode
  headerRight?: React.ReactNode
}) {
  return (
    <div className="bg-[#121f2d] rounded-lg border border-[#1e3a5f] p-5 space-y-4">
      <div className="flex items-start justify-between">
        <div className="flex items-start gap-3">
          {icon && <div className="mt-0.5">{icon}</div>}
          <div>
            <h2 className="text-lg font-semibold text-white">{title}</h2>
            <p className="text-xs text-[#5a7a94] mt-0.5">{description}</p>
          </div>
        </div>
        {headerRight && <div>{headerRight}</div>}
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
        <label className="text-sm text-[#8faabe]">{field.label}</label>
        <span className="text-sm tabular-nums text-[#a8c4d9]">{displayValue}</span>
      </div>
      <input
        type="range"
        min={field.min}
        max={field.max}
        step={field.step}
        value={value}
        onChange={(e) => onChange(parseFloat(e.target.value))}
        className="w-full h-1.5 bg-[#1a2d42] rounded-lg appearance-none cursor-pointer accent-tao-500"
      />
      <p className="text-xs text-[#243a52]">{field.description}</p>
    </div>
  )
}
