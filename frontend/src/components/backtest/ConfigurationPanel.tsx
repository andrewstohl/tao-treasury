import { useState } from 'react'
import { Info, AlertTriangle, Lock, Unlock } from 'lucide-react'

// Minimum date is Nov 5, 2025 (AMM change)
const MIN_DATE = '2025-11-05'

export interface BacktestConfig {
  // Date range
  startDate: string
  endDate: string

  // Hard failures
  minAgeDays: number
  minReserveTao: number
  maxOutflow7dPct: number
  maxDrawdownPct: number

  // Scoring weights
  faiWeight: number
  reserveWeight: number
  emissionWeight: number
  stabilityWeight: number

  // Strategy
  strategy: 'equal_weight' | 'fai_weighted'
  rebalanceDays: number
  topPercentile: number
  maxPositionPct: number

  // FAI config
  quintileMultipliers: Record<string, number>
  useLifecycle: boolean
}

const DEFAULT_CONFIG: BacktestConfig = {
  startDate: '2025-11-05',
  endDate: new Date().toISOString().split('T')[0],
  minAgeDays: 60,
  minReserveTao: 500,
  maxOutflow7dPct: 50,
  maxDrawdownPct: 50,
  faiWeight: 0.35,
  reserveWeight: 0.25,
  emissionWeight: 0.25,
  stabilityWeight: 0.15,
  strategy: 'equal_weight',
  rebalanceDays: 7,
  topPercentile: 50,
  maxPositionPct: 10,
  quintileMultipliers: { q1: 0.2, q2: 0.5, q3: 1.0, q4: 1.5, q5: 2.5 },
  useLifecycle: true,
}

interface ConfigurationPanelProps {
  config: BacktestConfig
  onChange: (config: BacktestConfig) => void
  onRun: () => void
  isRunning: boolean
}

export default function ConfigurationPanel({ config, onChange, onRun, isRunning }: ConfigurationPanelProps) {
  const [lockedWeights, setLockedWeights] = useState<Record<string, boolean>>({})

  const weightSum = config.faiWeight + config.reserveWeight + config.emissionWeight + config.stabilityWeight
  const weightsValid = Math.abs(weightSum - 1.0) < 0.01

  const updateConfig = (partial: Partial<BacktestConfig>) => {
    onChange({ ...config, ...partial })
  }

  const updateWeight = (key: keyof BacktestConfig, value: number) => {
    // When updating a weight, adjust others proportionally if they're not locked
    const currentValue = config[key] as number
    const delta = value - currentValue

    const weightKeys = ['faiWeight', 'reserveWeight', 'emissionWeight', 'stabilityWeight'] as const
    const unlockedKeys = weightKeys.filter(k => k !== key && !lockedWeights[k])

    if (unlockedKeys.length > 0 && delta !== 0) {
      const totalUnlocked = unlockedKeys.reduce((sum, k) => sum + (config[k] as number), 0)
      const newConfig = { ...config, [key]: value }

      if (totalUnlocked > 0) {
        unlockedKeys.forEach(k => {
          const currentWeight = config[k] as number
          const adjustment = (currentWeight / totalUnlocked) * -delta
          newConfig[k] = Math.max(0, Math.min(1, currentWeight + adjustment))
        })
      }

      onChange(newConfig)
    } else {
      updateConfig({ [key]: value } as Partial<BacktestConfig>)
    }
  }

  const applyPreset = (preset: 'research' | 'conservative' | 'aggressive') => {
    switch (preset) {
      case 'research':
        onChange({
          ...DEFAULT_CONFIG,
          strategy: 'equal_weight',
          rebalanceDays: 7,
        })
        break
      case 'conservative':
        onChange({
          ...DEFAULT_CONFIG,
          minAgeDays: 90,
          minReserveTao: 1000,
          strategy: 'equal_weight',
          rebalanceDays: 7,
          topPercentile: 30,
        })
        break
      case 'aggressive':
        onChange({
          ...DEFAULT_CONFIG,
          minAgeDays: 30,
          minReserveTao: 200,
          strategy: 'fai_weighted',
          rebalanceDays: 1,
          topPercentile: 70,
        })
        break
    }
  }

  return (
    <div className="bg-[#121f2d] rounded-lg border border-[#1e3a5f] p-5 space-y-5">
      <div className="flex items-center justify-between">
        <div>
          <h2 className="text-lg font-semibold text-white">Backtest Configuration</h2>
          <p className="text-xs text-[#5a7a94] mt-0.5">Configure parameters for historical strategy testing</p>
        </div>
        <div className="flex gap-2">
          <button
            onClick={() => applyPreset('research')}
            className="px-2 py-1 text-xs bg-[#1a2d42] hover:bg-[#243a52] rounded text-[#8faabe]"
          >
            Research Optimal
          </button>
          <button
            onClick={() => applyPreset('conservative')}
            className="px-2 py-1 text-xs bg-[#1a2d42] hover:bg-[#243a52] rounded text-[#8faabe]"
          >
            Conservative
          </button>
          <button
            onClick={() => applyPreset('aggressive')}
            className="px-2 py-1 text-xs bg-[#1a2d42] hover:bg-[#243a52] rounded text-[#8faabe]"
          >
            Aggressive
          </button>
        </div>
      </div>

      {/* Date Range */}
      <Section title="Date Range">
        <div className="grid grid-cols-2 gap-4">
          <div>
            <label className="text-xs text-[#6f87a0] block mb-1">Start Date</label>
            <input
              type="date"
              value={config.startDate}
              min={MIN_DATE}
              max={config.endDate}
              onChange={(e) => updateConfig({ startDate: e.target.value })}
              className="w-full bg-[#1a2d42] border border-[#2a4a66] rounded px-3 py-2 text-sm text-[#a8c4d9]"
            />
            <p className="text-[10px] text-[#5a7a94] mt-1">Min: Nov 5, 2025 (AMM change)</p>
          </div>
          <div>
            <label className="text-xs text-[#6f87a0] block mb-1">End Date</label>
            <input
              type="date"
              value={config.endDate}
              min={config.startDate}
              max={new Date().toISOString().split('T')[0]}
              onChange={(e) => updateConfig({ endDate: e.target.value })}
              className="w-full bg-[#1a2d42] border border-[#2a4a66] rounded px-3 py-2 text-sm text-[#a8c4d9]"
            />
          </div>
        </div>
        <div className="flex gap-2 mt-2">
          <QuickDateButton label="Last 30D" onClick={() => {
            const end = new Date()
            const start = new Date(end)
            start.setDate(start.getDate() - 30)
            const startStr = start.toISOString().split('T')[0]
            updateConfig({
              startDate: startStr < MIN_DATE ? MIN_DATE : startStr,
              endDate: end.toISOString().split('T')[0]
            })
          }} />
          <QuickDateButton label="Last 90D" onClick={() => {
            const end = new Date()
            const start = new Date(end)
            start.setDate(start.getDate() - 90)
            const startStr = start.toISOString().split('T')[0]
            updateConfig({
              startDate: startStr < MIN_DATE ? MIN_DATE : startStr,
              endDate: end.toISOString().split('T')[0]
            })
          }} />
          <QuickDateButton label="All Data" onClick={() => {
            updateConfig({
              startDate: MIN_DATE,
              endDate: new Date().toISOString().split('T')[0]
            })
          }} />
        </div>
      </Section>

      {/* Hard Failures */}
      <Section title="Viability Hard Failures" description="Subnets failing any threshold are excluded">
        <div className="grid grid-cols-2 gap-4">
          <SliderField
            label="Min Age (days)"
            value={config.minAgeDays}
            min={0}
            max={180}
            step={15}
            onChange={(v) => updateConfig({ minAgeDays: v })}
            format={(v) => `${v}d`}
          />
          <SliderField
            label="Min TAO Reserve"
            value={config.minReserveTao}
            min={0}
            max={5000}
            step={100}
            onChange={(v) => updateConfig({ minReserveTao: v })}
            format={(v) => `${v} TAO`}
          />
          <SliderField
            label="Max 7D Outflow"
            value={config.maxOutflow7dPct}
            min={10}
            max={100}
            step={5}
            onChange={(v) => updateConfig({ maxOutflow7dPct: v })}
            format={(v) => `-${v}%`}
          />
          <SliderField
            label="Max Drawdown"
            value={config.maxDrawdownPct}
            min={10}
            max={100}
            step={5}
            onChange={(v) => updateConfig({ maxDrawdownPct: v })}
            format={(v) => `${v}%`}
          />
        </div>
      </Section>

      {/* Viability Weights */}
      <Section
        title="Viability Scoring Weights"
        description="Must sum to 100%"
        headerRight={
          <span className={`text-sm tabular-nums ${weightsValid ? 'text-green-400' : 'text-red-400'}`}>
            Total: {(weightSum * 100).toFixed(0)}%
          </span>
        }
      >
        {!weightsValid && (
          <div className="flex items-center gap-2 text-xs text-red-400 mb-2">
            <AlertTriangle className="w-3 h-3" /> Weights must sum to 100%
          </div>
        )}

        {/* Weight bar visualization */}
        <div className="flex h-3 rounded-full overflow-hidden bg-[#1a2d42] mb-3">
          <div className="bg-emerald-500 transition-all" style={{ width: `${config.faiWeight * 100}%` }} title={`FAI: ${(config.faiWeight * 100).toFixed(0)}%`} />
          <div className="bg-blue-500 transition-all" style={{ width: `${config.reserveWeight * 100}%` }} title={`Reserve: ${(config.reserveWeight * 100).toFixed(0)}%`} />
          <div className="bg-purple-500 transition-all" style={{ width: `${config.emissionWeight * 100}%` }} title={`Emission: ${(config.emissionWeight * 100).toFixed(0)}%`} />
          <div className="bg-amber-500 transition-all" style={{ width: `${config.stabilityWeight * 100}%` }} title={`Stability: ${(config.stabilityWeight * 100).toFixed(0)}%`} />
        </div>

        <div className="grid grid-cols-2 gap-4">
          <WeightField
            label="FAI (Flow Momentum)"
            value={config.faiWeight}
            onChange={(v) => updateWeight('faiWeight', v)}
            color="text-emerald-400"
            locked={lockedWeights.faiWeight}
            onLockToggle={() => setLockedWeights(p => ({ ...p, faiWeight: !p.faiWeight }))}
          />
          <WeightField
            label="TAO Reserve"
            value={config.reserveWeight}
            onChange={(v) => updateWeight('reserveWeight', v)}
            color="text-blue-400"
            locked={lockedWeights.reserveWeight}
            onLockToggle={() => setLockedWeights(p => ({ ...p, reserveWeight: !p.reserveWeight }))}
          />
          <WeightField
            label="Emission Share"
            value={config.emissionWeight}
            onChange={(v) => updateWeight('emissionWeight', v)}
            color="text-purple-400"
            locked={lockedWeights.emissionWeight}
            onLockToggle={() => setLockedWeights(p => ({ ...p, emissionWeight: !p.emissionWeight }))}
          />
          <WeightField
            label="Stability"
            value={config.stabilityWeight}
            onChange={(v) => updateWeight('stabilityWeight', v)}
            color="text-amber-400"
            locked={lockedWeights.stabilityWeight}
            onLockToggle={() => setLockedWeights(p => ({ ...p, stabilityWeight: !p.stabilityWeight }))}
          />
        </div>
      </Section>

      {/* Strategy Selection */}
      <Section title="Strategy">
        <div className="space-y-4">
          <div className="flex gap-4">
            <label className="flex items-center gap-2 cursor-pointer">
              <input
                type="radio"
                checked={config.strategy === 'equal_weight'}
                onChange={() => updateConfig({ strategy: 'equal_weight' })}
                className="w-4 h-4 text-tao-500"
              />
              <span className="text-sm text-[#a8c4d9]">Equal Weight</span>
              <span className="text-[10px] text-green-400">(Recommended)</span>
            </label>
            <label className="flex items-center gap-2 cursor-pointer">
              <input
                type="radio"
                checked={config.strategy === 'fai_weighted'}
                onChange={() => updateConfig({ strategy: 'fai_weighted' })}
                className="w-4 h-4 text-tao-500"
              />
              <span className="text-sm text-[#a8c4d9]">FAI-Weighted</span>
            </label>
          </div>

          <div className="grid grid-cols-3 gap-4">
            <div>
              <label className="text-xs text-[#6f87a0] block mb-1">Rebalance Frequency</label>
              <select
                value={config.rebalanceDays}
                onChange={(e) => updateConfig({ rebalanceDays: Number(e.target.value) })}
                className="w-full bg-[#1a2d42] border border-[#2a4a66] rounded px-3 py-2 text-sm text-[#a8c4d9]"
              >
                <option value={1}>Daily</option>
                <option value={3}>Every 3 Days</option>
                <option value={7}>Weekly</option>
              </select>
            </div>
            <SliderField
              label="Top Subnets %"
              value={config.topPercentile}
              min={10}
              max={100}
              step={10}
              onChange={(v) => updateConfig({ topPercentile: v })}
              format={(v) => `${v}%`}
            />
            <SliderField
              label="Max Position"
              value={config.maxPositionPct}
              min={5}
              max={25}
              step={5}
              onChange={(v) => updateConfig({ maxPositionPct: v })}
              format={(v) => `${v}%`}
            />
          </div>
        </div>
      </Section>

      {/* FAI Settings (when FAI strategy selected) */}
      {config.strategy === 'fai_weighted' && (
        <Section title="FAI Settings">
          <div className="space-y-4">
            <div>
              <label className="text-xs text-[#6f87a0] block mb-2">Quintile Multipliers</label>
              <div className="grid grid-cols-5 gap-2">
                {['q1', 'q2', 'q3', 'q4', 'q5'].map((q, i) => (
                  <div key={q}>
                    <label className="text-[10px] text-[#5a7a94] block mb-1">Q{i + 1}</label>
                    <input
                      type="number"
                      value={config.quintileMultipliers[q]}
                      onChange={(e) => updateConfig({
                        quintileMultipliers: { ...config.quintileMultipliers, [q]: Number(e.target.value) }
                      })}
                      step={0.1}
                      min={0}
                      max={5}
                      className="w-full bg-[#1a2d42] border border-[#2a4a66] rounded px-2 py-1 text-sm text-center text-[#a8c4d9] tabular-nums"
                    />
                  </div>
                ))}
              </div>
            </div>

            <label className="flex items-center gap-2 cursor-pointer">
              <input
                type="checkbox"
                checked={config.useLifecycle}
                onChange={(e) => updateConfig({ useLifecycle: e.target.checked })}
                className="w-4 h-4 rounded border-[#2a4a66] bg-[#1a2d42] text-tao-500"
              />
              <span className="text-sm text-[#a8c4d9]">Use Days-in-Signal Lifecycle</span>
            </label>
          </div>
        </Section>
      )}

      {/* Run Button */}
      <div className="flex items-center justify-between pt-2 border-t border-[#1e3a5f]">
        <div className="flex items-start gap-2 text-xs text-[#5a7a94]">
          <Info className="w-3 h-3 mt-0.5 flex-shrink-0" />
          <span>Uses actual subnet registration dates for age calculation</span>
        </div>
        <button
          onClick={onRun}
          disabled={isRunning || !weightsValid}
          className="flex items-center gap-2 px-6 py-2.5 bg-tao-600 hover:bg-tao-500 rounded text-sm font-medium text-white disabled:opacity-50 disabled:cursor-not-allowed"
        >
          {isRunning ? (
            <>
              <span className="animate-spin">&#9696;</span>
              Running Backtest...
            </>
          ) : (
            'Run Backtest'
          )}
        </button>
      </div>
    </div>
  )
}

function Section({
  title,
  description,
  headerRight,
  children
}: {
  title: string
  description?: string
  headerRight?: React.ReactNode
  children: React.ReactNode
}) {
  return (
    <div className="space-y-3">
      <div className="flex items-center justify-between">
        <div>
          <h3 className="text-sm font-medium text-[#a8c4d9]">{title}</h3>
          {description && <p className="text-[10px] text-[#5a7a94] mt-0.5">{description}</p>}
        </div>
        {headerRight}
      </div>
      {children}
    </div>
  )
}

function SliderField({
  label,
  value,
  min,
  max,
  step,
  onChange,
  format,
}: {
  label: string
  value: number
  min: number
  max: number
  step: number
  onChange: (v: number) => void
  format: (v: number) => string
}) {
  return (
    <div className="space-y-1">
      <div className="flex justify-between items-baseline">
        <label className="text-xs text-[#6f87a0]">{label}</label>
        <span className="text-xs tabular-nums text-[#a8c4d9]">{format(value)}</span>
      </div>
      <input
        type="range"
        min={min}
        max={max}
        step={step}
        value={value}
        onChange={(e) => onChange(Number(e.target.value))}
        className="w-full h-1.5 bg-[#1a2d42] rounded-lg appearance-none cursor-pointer accent-tao-500"
      />
    </div>
  )
}

function WeightField({
  label,
  value,
  onChange,
  color,
  locked,
  onLockToggle,
}: {
  label: string
  value: number
  onChange: (v: number) => void
  color: string
  locked: boolean
  onLockToggle: () => void
}) {
  return (
    <div className="space-y-1">
      <div className="flex justify-between items-center">
        <label className={`text-xs ${color}`}>{label}</label>
        <div className="flex items-center gap-2">
          <span className="text-xs tabular-nums text-[#a8c4d9]">{(value * 100).toFixed(0)}%</span>
          <button onClick={onLockToggle} className="text-[#5a7a94] hover:text-[#a8c4d9]">
            {locked ? <Lock className="w-3 h-3" /> : <Unlock className="w-3 h-3" />}
          </button>
        </div>
      </div>
      <input
        type="range"
        min={0}
        max={1}
        step={0.05}
        value={value}
        onChange={(e) => onChange(Number(e.target.value))}
        disabled={locked}
        className="w-full h-1.5 bg-[#1a2d42] rounded-lg appearance-none cursor-pointer accent-tao-500 disabled:opacity-50"
      />
    </div>
  )
}

function QuickDateButton({ label, onClick }: { label: string; onClick: () => void }) {
  return (
    <button
      onClick={onClick}
      className="px-2 py-1 text-xs bg-[#1a2d42] hover:bg-[#243a52] rounded text-[#6f87a0] hover:text-[#a8c4d9]"
    >
      {label}
    </button>
  )
}

export { DEFAULT_CONFIG }
