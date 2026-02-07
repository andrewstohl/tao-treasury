import { useState, useMemo } from 'react'
import { Play, Square, Zap, Target, TrendingUp, AlertTriangle, ArrowUp, ArrowDown } from 'lucide-react'
import { api } from '../../services/api'

type SortColumn = 'sharpe' | 'return' | 'maxDrawdown' | 'winRate'
type SortDirection = 'asc' | 'desc'

interface OptimizationConfig {
  // Parameters to optimize
  optimizeWeights: boolean
  optimizeThresholds: boolean
  optimizePercentile: boolean

  // Weight ranges [min, max, step]
  faiWeightRange: [number, number, number]
  reserveWeightRange: [number, number, number]
  emissionWeightRange: [number, number, number]
  stabilityWeightRange: [number, number, number]

  // Threshold ranges
  minAgeRange: [number, number, number]
  minReserveRange: [number, number, number]

  // Percentile range
  topPercentileRange: [number, number, number]

  // Optimization target
  optimizeFor: 'sharpe' | 'return' | 'drawdown' | 'win_rate'
}

interface OptimizationResult {
  config: Record<string, number>
  sharpe: number
  totalReturn: number
  maxDrawdown: number
  winRate: number
  avgHoldings: number
}

interface OptimizationPanelProps {
  onApplyConfig: (config: Record<string, number>) => void
  isBacktestRunning: boolean
}

const DEFAULT_OPTIMIZATION_CONFIG: OptimizationConfig = {
  optimizeWeights: true,
  optimizeThresholds: false,
  optimizePercentile: false,
  faiWeightRange: [0.2, 0.5, 0.05],
  reserveWeightRange: [0.15, 0.35, 0.05],
  emissionWeightRange: [0.15, 0.35, 0.05],
  stabilityWeightRange: [0.1, 0.25, 0.05],
  minAgeRange: [30, 90, 15],
  minReserveRange: [200, 1000, 200],
  topPercentileRange: [30, 70, 10],
  optimizeFor: 'sharpe',
}

export default function OptimizationPanel({ onApplyConfig, isBacktestRunning }: OptimizationPanelProps) {
  const [config, setConfig] = useState<OptimizationConfig>(DEFAULT_OPTIMIZATION_CONFIG)
  const [isRunning, setIsRunning] = useState(false)
  const [progress, setProgress] = useState(0)
  const [results, setResults] = useState<OptimizationResult[]>([])
  const [error, setError] = useState<string | null>(null)
  const [sortColumn, setSortColumn] = useState<SortColumn>('sharpe')
  const [sortDirection, setSortDirection] = useState<SortDirection>('desc')

  const sortedResults = useMemo(() => {
    return [...results].sort((a, b) => {
      let aVal: number, bVal: number
      switch (sortColumn) {
        case 'sharpe':
          aVal = a.sharpe
          bVal = b.sharpe
          break
        case 'return':
          aVal = a.totalReturn
          bVal = b.totalReturn
          break
        case 'maxDrawdown':
          aVal = a.maxDrawdown
          bVal = b.maxDrawdown
          break
        case 'winRate':
          aVal = a.winRate
          bVal = b.winRate
          break
        default:
          return 0
      }
      return sortDirection === 'desc' ? bVal - aVal : aVal - bVal
    })
  }, [results, sortColumn, sortDirection])

  const handleSort = (column: SortColumn) => {
    if (sortColumn === column) {
      setSortDirection(prev => prev === 'desc' ? 'asc' : 'desc')
    } else {
      setSortColumn(column)
      // Default to descending for most metrics, ascending for drawdown
      setSortDirection(column === 'maxDrawdown' ? 'asc' : 'desc')
    }
  }

  const SortIcon = ({ column }: { column: SortColumn }) => {
    if (sortColumn !== column) {
      return <span className="opacity-30 ml-1">↕</span>
    }
    return sortDirection === 'desc'
      ? <ArrowDown className="w-3 h-3 ml-1 inline" />
      : <ArrowUp className="w-3 h-3 ml-1 inline" />
  }

  const calculateCombinations = () => {
    let count = 1

    if (config.optimizeWeights) {
      const faiSteps = Math.floor((config.faiWeightRange[1] - config.faiWeightRange[0]) / config.faiWeightRange[2]) + 1
      const reserveSteps = Math.floor((config.reserveWeightRange[1] - config.reserveWeightRange[0]) / config.reserveWeightRange[2]) + 1
      const emissionSteps = Math.floor((config.emissionWeightRange[1] - config.emissionWeightRange[0]) / config.emissionWeightRange[2]) + 1
      // Stability is derived to sum to 100%, so we estimate valid combinations
      count *= faiSteps * reserveSteps * emissionSteps * 0.3 // ~30% are valid (sum to 100%)
    }

    if (config.optimizeThresholds) {
      const ageSteps = Math.floor((config.minAgeRange[1] - config.minAgeRange[0]) / config.minAgeRange[2]) + 1
      const reserveSteps = Math.floor((config.minReserveRange[1] - config.minReserveRange[0]) / config.minReserveRange[2]) + 1
      count *= ageSteps * reserveSteps
    }

    if (config.optimizePercentile) {
      const pctSteps = Math.floor((config.topPercentileRange[1] - config.topPercentileRange[0]) / config.topPercentileRange[2]) + 1
      count *= pctSteps
    }

    return Math.max(1, Math.floor(count))
  }

  const runOptimization = async () => {
    setIsRunning(true)
    setError(null)
    setProgress(0)
    setResults([])

    const combinations = calculateCombinations()

    try {
      // Generate all valid parameter combinations
      const allResults: OptimizationResult[] = []
      let tested = 0

      // Weight optimization
      const faiValues = config.optimizeWeights
        ? generateRange(config.faiWeightRange[0], config.faiWeightRange[1], config.faiWeightRange[2])
        : [0.35]
      const reserveValues = config.optimizeWeights
        ? generateRange(config.reserveWeightRange[0], config.reserveWeightRange[1], config.reserveWeightRange[2])
        : [0.25]
      const emissionValues = config.optimizeWeights
        ? generateRange(config.emissionWeightRange[0], config.emissionWeightRange[1], config.emissionWeightRange[2])
        : [0.25]

      // Threshold optimization
      const ageValues = config.optimizeThresholds
        ? generateRange(config.minAgeRange[0], config.minAgeRange[1], config.minAgeRange[2])
        : [60]
      const reserveThreshValues = config.optimizeThresholds
        ? generateRange(config.minReserveRange[0], config.minReserveRange[1], config.minReserveRange[2])
        : [500]

      // Percentile optimization
      const percentileValues = config.optimizePercentile
        ? generateRange(config.topPercentileRange[0], config.topPercentileRange[1], config.topPercentileRange[2])
        : [50]

      // Run through all combinations
      for (const fai of faiValues) {
        for (const reserve of reserveValues) {
          for (const emission of emissionValues) {
            const stability = 1.0 - fai - reserve - emission

            // Skip invalid weight combinations
            if (stability < 0.05 || stability > 0.3) continue

            for (const age of ageValues) {
              for (const reserveThresh of reserveThreshValues) {
                for (const percentile of percentileValues) {
                  tested++
                  setProgress(Math.floor((tested / combinations) * 100))

                  // Call the API for this configuration
                  try {
                    const data = await api.simulatePortfolioV2({
                      intervalDays: 7,
                      initialCapital: 100,
                      minAgeDays: age,
                      minReserveTao: reserveThresh,
                      faiWeight: fai,
                      reserveWeight: reserve,
                      emissionWeight: emission,
                      stabilityWeight: stability,
                      strategy: 'equal_weight',
                      topPercentile: percentile,
                    })

                    allResults.push({
                      config: {
                        faiWeight: fai,
                        reserveWeight: reserve,
                        emissionWeight: emission,
                        stabilityWeight: stability,
                        minAgeDays: age,
                        minReserveTao: reserveThresh,
                        topPercentile: percentile,
                      },
                      sharpe: data.summary.win_rate > 0
                        ? data.total_return / Math.max(data.summary.max_drawdown_pct, 0.01)
                        : 0,
                      totalReturn: data.total_return,
                      maxDrawdown: data.summary.max_drawdown_pct,
                      winRate: data.summary.win_rate,
                      avgHoldings: data.summary.avg_holdings_per_period,
                    })
                  } catch {
                    // Skip failed combinations
                    continue
                  }

                  // Update progress periodically
                  if (tested % 5 === 0) {
                    setResults([...allResults])
                  }
                }
              }
            }
          }
        }
      }

      // Sort by optimization target
      allResults.sort((a, b) => {
        switch (config.optimizeFor) {
          case 'sharpe': return b.sharpe - a.sharpe
          case 'return': return b.totalReturn - a.totalReturn
          case 'drawdown': return a.maxDrawdown - b.maxDrawdown
          case 'win_rate': return b.winRate - a.winRate
          default: return b.sharpe - a.sharpe
        }
      })

      setResults(allResults.slice(0, 10))
      setProgress(100)
    } catch (e) {
      setError(e instanceof Error ? e.message : 'Optimization failed')
    } finally {
      setIsRunning(false)
    }
  }

  const generateRange = (min: number, max: number, step: number): number[] => {
    const values: number[] = []
    for (let v = min; v <= max + 0.001; v += step) {
      values.push(Math.round(v * 100) / 100)
    }
    return values
  }

  const updateConfig = (partial: Partial<OptimizationConfig>) => {
    setConfig(prev => ({ ...prev, ...partial }))
  }

  const updateRange = (
    key: keyof OptimizationConfig,
    index: 0 | 1 | 2,
    value: number
  ) => {
    const currentRange = config[key] as [number, number, number]
    const newRange: [number, number, number] = [...currentRange]
    newRange[index] = value
    setConfig(prev => ({ ...prev, [key]: newRange }))
  }

  const estimatedCombinations = calculateCombinations()

  return (
    <div className="bg-[#121f2d] rounded-lg border border-[#1e3a5f] p-5 space-y-5">
      <div className="flex items-center justify-between">
        <div>
          <h2 className="text-lg font-semibold text-white flex items-center gap-2">
            <Zap className="w-5 h-5 text-amber-400" />
            Parameter Optimization
          </h2>
          <p className="text-xs text-[#5a7a94] mt-0.5">
            Find the best parameter combinations through grid search
          </p>
        </div>
        <div className="text-xs text-[#6f87a0]">
          Est. {estimatedCombinations.toLocaleString()} combinations
        </div>
      </div>

      {/* Parameters to Optimize */}
      <div className="space-y-3">
        <h3 className="text-sm font-medium text-[#a8c4d9]">Parameters to Optimize</h3>
        <div className="flex flex-wrap gap-4">
          <label className="flex items-center gap-2 cursor-pointer">
            <input
              type="checkbox"
              checked={config.optimizeWeights}
              onChange={(e) => updateConfig({ optimizeWeights: e.target.checked })}
              className="w-4 h-4 rounded border-[#2a4a66] bg-[#1a2d42] text-tao-500"
            />
            <span className="text-sm text-[#a8c4d9]">Viability Weights</span>
          </label>
          <label className="flex items-center gap-2 cursor-pointer">
            <input
              type="checkbox"
              checked={config.optimizeThresholds}
              onChange={(e) => updateConfig({ optimizeThresholds: e.target.checked })}
              className="w-4 h-4 rounded border-[#2a4a66] bg-[#1a2d42] text-tao-500"
            />
            <span className="text-sm text-[#a8c4d9]">Hard Failure Thresholds</span>
          </label>
          <label className="flex items-center gap-2 cursor-pointer">
            <input
              type="checkbox"
              checked={config.optimizePercentile}
              onChange={(e) => updateConfig({ optimizePercentile: e.target.checked })}
              className="w-4 h-4 rounded border-[#2a4a66] bg-[#1a2d42] text-tao-500"
            />
            <span className="text-sm text-[#a8c4d9]">Top Percentile</span>
          </label>
        </div>
      </div>

      {/* Weight Ranges */}
      {config.optimizeWeights && (
        <div className="space-y-3 bg-[#0a1520]/50 rounded-lg p-4 border border-[#1e3a5f]/50">
          <h4 className="text-xs font-medium text-[#6f87a0] uppercase tracking-wider">Weight Ranges</h4>
          <div className="grid grid-cols-2 gap-4">
            <RangeInput
              label="FAI Weight"
              range={config.faiWeightRange}
              onChange={(idx, val) => updateRange('faiWeightRange', idx, val)}
              format={(v) => `${(v * 100).toFixed(0)}%`}
              step={0.05}
            />
            <RangeInput
              label="Reserve Weight"
              range={config.reserveWeightRange}
              onChange={(idx, val) => updateRange('reserveWeightRange', idx, val)}
              format={(v) => `${(v * 100).toFixed(0)}%`}
              step={0.05}
            />
            <RangeInput
              label="Emission Weight"
              range={config.emissionWeightRange}
              onChange={(idx, val) => updateRange('emissionWeightRange', idx, val)}
              format={(v) => `${(v * 100).toFixed(0)}%`}
              step={0.05}
            />
            <RangeInput
              label="Stability Weight"
              range={config.stabilityWeightRange}
              onChange={(idx, val) => updateRange('stabilityWeightRange', idx, val)}
              format={(v) => `${(v * 100).toFixed(0)}%`}
              step={0.05}
            />
          </div>
        </div>
      )}

      {/* Threshold Ranges */}
      {config.optimizeThresholds && (
        <div className="space-y-3 bg-[#0a1520]/50 rounded-lg p-4 border border-[#1e3a5f]/50">
          <h4 className="text-xs font-medium text-[#6f87a0] uppercase tracking-wider">Threshold Ranges</h4>
          <div className="grid grid-cols-2 gap-4">
            <RangeInput
              label="Min Age (days)"
              range={config.minAgeRange}
              onChange={(idx, val) => updateRange('minAgeRange', idx, val)}
              format={(v) => `${v}d`}
              step={15}
            />
            <RangeInput
              label="Min Reserve (TAO)"
              range={config.minReserveRange}
              onChange={(idx, val) => updateRange('minReserveRange', idx, val)}
              format={(v) => `${v}`}
              step={100}
            />
          </div>
        </div>
      )}

      {/* Percentile Range */}
      {config.optimizePercentile && (
        <div className="space-y-3 bg-[#0a1520]/50 rounded-lg p-4 border border-[#1e3a5f]/50">
          <h4 className="text-xs font-medium text-[#6f87a0] uppercase tracking-wider">Percentile Range</h4>
          <RangeInput
            label="Top Percentile"
            range={config.topPercentileRange}
            onChange={(idx, val) => updateRange('topPercentileRange', idx, val)}
            format={(v) => `${v}%`}
            step={10}
          />
        </div>
      )}

      {/* Optimization Target */}
      <div className="space-y-3">
        <h3 className="text-sm font-medium text-[#a8c4d9]">Optimize For</h3>
        <div className="flex flex-wrap gap-3">
          {[
            { value: 'sharpe', label: 'Sharpe Ratio', icon: Target },
            { value: 'return', label: 'Total Return', icon: TrendingUp },
            { value: 'drawdown', label: 'Min Drawdown', icon: AlertTriangle },
          ].map((opt) => {
            const Icon = opt.icon
            return (
              <label key={opt.value} className="flex items-center gap-2 cursor-pointer">
                <input
                  type="radio"
                  checked={config.optimizeFor === opt.value}
                  onChange={() => updateConfig({ optimizeFor: opt.value as OptimizationConfig['optimizeFor'] })}
                  className="w-4 h-4 text-tao-500"
                />
                <Icon className="w-4 h-4 text-[#6f87a0]" />
                <span className="text-sm text-[#a8c4d9]">{opt.label}</span>
              </label>
            )
          })}
        </div>
      </div>

      {/* Run Button */}
      <div className="flex items-center gap-4 pt-2 border-t border-[#1e3a5f]">
        <button
          onClick={isRunning ? () => setIsRunning(false) : runOptimization}
          disabled={isBacktestRunning || (!config.optimizeWeights && !config.optimizeThresholds && !config.optimizePercentile)}
          className={`flex items-center gap-2 px-6 py-2.5 rounded text-sm font-medium disabled:opacity-50 disabled:cursor-not-allowed ${
            isRunning
              ? 'bg-red-600 hover:bg-red-500 text-white'
              : 'bg-amber-600 hover:bg-amber-500 text-white'
          }`}
        >
          {isRunning ? (
            <>
              <Square className="w-4 h-4" />
              Stop Optimization
            </>
          ) : (
            <>
              <Play className="w-4 h-4" />
              Run Optimization
            </>
          )}
        </button>
        {isRunning && (
          <div className="flex-1">
            <div className="flex items-center justify-between text-xs text-[#6f87a0] mb-1">
              <span>Testing configurations...</span>
              <span>{progress}%</span>
            </div>
            <div className="w-full bg-[#1a2d42] rounded-full h-2">
              <div
                className="bg-amber-500 h-2 rounded-full transition-all"
                style={{ width: `${progress}%` }}
              />
            </div>
          </div>
        )}
      </div>

      {/* Error */}
      {error && (
        <div className="text-sm text-red-400 bg-red-900/20 rounded-lg p-3 flex items-center gap-2">
          <AlertTriangle className="w-4 h-4" />
          {error}
        </div>
      )}

      {/* Results */}
      {results.length > 0 && (
        <div className="space-y-3">
          <h3 className="text-sm font-medium text-[#a8c4d9]">
            Top Configurations by {config.optimizeFor === 'sharpe' ? 'Sharpe Ratio' :
              config.optimizeFor === 'return' ? 'Total Return' :
              config.optimizeFor === 'drawdown' ? 'Min Drawdown' : 'Win Rate'}
          </h3>
          <div className="overflow-x-auto">
            <table className="w-full text-xs">
              <thead>
                <tr className="text-[#5a7a94] border-b border-[#1e3a5f]">
                  <th className="text-left py-2 px-2">#</th>
                  <th className="text-left py-2 px-2">Configuration</th>
                  <th
                    className="text-right py-2 px-2 cursor-pointer hover:text-[#a8c4d9] select-none"
                    onClick={() => handleSort('sharpe')}
                  >
                    Sharpe<SortIcon column="sharpe" />
                  </th>
                  <th
                    className="text-right py-2 px-2 cursor-pointer hover:text-[#a8c4d9] select-none"
                    onClick={() => handleSort('return')}
                  >
                    Return<SortIcon column="return" />
                  </th>
                  <th
                    className="text-right py-2 px-2 cursor-pointer hover:text-[#a8c4d9] select-none"
                    onClick={() => handleSort('maxDrawdown')}
                  >
                    Max DD<SortIcon column="maxDrawdown" />
                  </th>
                  <th
                    className="text-right py-2 px-2 cursor-pointer hover:text-[#a8c4d9] select-none"
                    onClick={() => handleSort('winRate')}
                  >
                    Win Rate<SortIcon column="winRate" />
                  </th>
                  <th className="text-center py-2 px-2">Action</th>
                </tr>
              </thead>
              <tbody>
                {sortedResults.map((result, idx) => (
                  <tr key={idx} className="border-b border-[#1e3a5f]/50 hover:bg-[#1a2d42]/30">
                    <td className="py-2 px-2 text-[#6f87a0]">{idx + 1}</td>
                    <td className="py-2 px-2 text-[#a8c4d9]">
                      FAI:{(result.config.faiWeight * 100).toFixed(0)}%
                      RSV:{(result.config.reserveWeight * 100).toFixed(0)}%
                      EM:{(result.config.emissionWeight * 100).toFixed(0)}%
                      ST:{(result.config.stabilityWeight * 100).toFixed(0)}%
                      {config.optimizeThresholds && (
                        <span className="text-[#5a7a94]">
                          {' '}| Age:{result.config.minAgeDays}d RSV:{result.config.minReserveTao}
                        </span>
                      )}
                      {config.optimizePercentile && (
                        <span className="text-[#5a7a94]">
                          {' '}| Top:{result.config.topPercentile}%
                        </span>
                      )}
                    </td>
                    <td className={`py-2 px-2 text-right tabular-nums ${result.sharpe > 5 ? 'text-green-400' : 'text-[#a8c4d9]'}`}>
                      {result.sharpe.toFixed(2)}
                    </td>
                    <td className={`py-2 px-2 text-right tabular-nums ${result.totalReturn > 0 ? 'text-green-400' : 'text-red-400'}`}>
                      {(result.totalReturn * 100).toFixed(1)}%
                    </td>
                    <td className="py-2 px-2 text-right tabular-nums text-red-400">
                      -{(result.maxDrawdown * 100).toFixed(1)}%
                    </td>
                    <td className="py-2 px-2 text-right tabular-nums text-[#a8c4d9]">
                      {(result.winRate * 100).toFixed(0)}%
                    </td>
                    <td className="py-2 px-2 text-center">
                      <button
                        onClick={() => onApplyConfig(result.config)}
                        className="px-2 py-1 bg-tao-600 hover:bg-tao-500 rounded text-[10px] text-white"
                      >
                        Apply
                      </button>
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        </div>
      )}
    </div>
  )
}

function RangeInput({
  label,
  range,
  onChange,
  format,
  step,
}: {
  label: string
  range: [number, number, number]
  onChange: (index: 0 | 1 | 2, value: number) => void
  format: (v: number) => string
  step: number
}) {
  return (
    <div className="space-y-1">
      <label className="text-xs text-[#6f87a0]">{label}</label>
      <div className="flex items-center gap-2">
        <input
          type="number"
          value={range[0]}
          onChange={(e) => onChange(0, parseFloat(e.target.value))}
          step={step}
          className="w-16 bg-[#1a2d42] border border-[#2a4a66] rounded px-2 py-1 text-xs text-[#a8c4d9] text-center"
        />
        <span className="text-[#5a7a94]">to</span>
        <input
          type="number"
          value={range[1]}
          onChange={(e) => onChange(1, parseFloat(e.target.value))}
          step={step}
          className="w-16 bg-[#1a2d42] border border-[#2a4a66] rounded px-2 py-1 text-xs text-[#a8c4d9] text-center"
        />
        <span className="text-[#5a7a94] text-xs">step</span>
        <input
          type="number"
          value={range[2]}
          onChange={(e) => onChange(2, parseFloat(e.target.value))}
          step={step}
          className="w-14 bg-[#1a2d42] border border-[#2a4a66] rounded px-2 py-1 text-xs text-[#a8c4d9] text-center"
        />
      </div>
      <div className="text-[10px] text-[#5a7a94]">
        Range: {format(range[0])} - {format(range[1])}
      </div>
    </div>
  )
}
