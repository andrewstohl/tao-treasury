import { useState, useRef, useEffect } from 'react'
import { Download, Loader2, CheckCircle, AlertTriangle, Info, ChevronDown, ChevronRight } from 'lucide-react'
import { api } from '../services/api'
import type { BackfillStatus, PortfolioPeriod, PortfolioEquityPoint } from '../types'
import ConfigurationPanel, { BacktestConfig, DEFAULT_CONFIG } from '../components/backtest/ConfigurationPanel'
import ResultsPanel, { BacktestResults } from '../components/backtest/ResultsPanel'
import OptimizationPanel from '../components/backtest/OptimizationPanel'

export default function Backtest() {
  const [config, setConfig] = useState<BacktestConfig>(DEFAULT_CONFIG)
  const [results, setResults] = useState<BacktestResults | null>(null)
  const [isRunning, setIsRunning] = useState(false)
  const [error, setError] = useState<string | null>(null)
  const [showOptimization, setShowOptimization] = useState(false)

  // Backfill state
  const [backfillStatus, setBackfillStatus] = useState<BackfillStatus | null>(null)
  const [isBackfilling, setIsBackfilling] = useState(false)
  const pollRef = useRef<ReturnType<typeof setInterval> | null>(null)

  // Handle applying optimization results
  const handleApplyOptimizationConfig = (optimizedConfig: Record<string, number>) => {
    setConfig(prev => ({
      ...prev,
      faiWeight: optimizedConfig.faiWeight ?? prev.faiWeight,
      reserveWeight: optimizedConfig.reserveWeight ?? prev.reserveWeight,
      emissionWeight: optimizedConfig.emissionWeight ?? prev.emissionWeight,
      stabilityWeight: optimizedConfig.stabilityWeight ?? prev.stabilityWeight,
      minAgeDays: optimizedConfig.minAgeDays ?? prev.minAgeDays,
      minReserveTao: optimizedConfig.minReserveTao ?? prev.minReserveTao,
      topPercentile: optimizedConfig.topPercentile ?? prev.topPercentile,
    }))
  }

  // Check backfill status on mount
  useEffect(() => {
    const checkStatus = async () => {
      try {
        const status = await api.getBackfillStatus()
        setBackfillStatus(status)
        if (status.running) {
          setIsBackfilling(true)
          startPolling()
        }
      } catch {
        // ignore
      }
    }
    checkStatus()
    return () => {
      if (pollRef.current) clearInterval(pollRef.current)
    }
  }, [])

  const startPolling = () => {
    if (pollRef.current) clearInterval(pollRef.current)
    pollRef.current = setInterval(async () => {
      try {
        const s = await api.getBackfillStatus()
        setBackfillStatus(s)
        if (!s.running) {
          setIsBackfilling(false)
          if (pollRef.current) clearInterval(pollRef.current)
          pollRef.current = null
        }
      } catch {
        // ignore
      }
    }, 3000)
  }

  const triggerBackfill = async () => {
    try {
      await api.triggerBackfill(365)
      setIsBackfilling(true)
      startPolling()
    } catch (e: unknown) {
      setError(e instanceof Error ? e.message : 'Backfill trigger failed')
    }
  }

  const runBacktest = async () => {
    setIsRunning(true)
    setError(null)

    try {
      // Use the new v2 endpoint with full viability config
      const simData = await api.simulatePortfolioV2({
        intervalDays: config.rebalanceDays,
        initialCapital: 100,
        startDate: config.startDate,
        endDate: config.endDate,
        // Hard failure thresholds
        minAgeDays: config.minAgeDays,
        minReserveTao: config.minReserveTao,
        maxOutflow7dPct: config.maxOutflow7dPct,
        maxDrawdownPct: config.maxDrawdownPct,
        // Viability scoring weights
        faiWeight: config.faiWeight,
        reserveWeight: config.reserveWeight,
        emissionWeight: config.emissionWeight,
        stabilityWeight: config.stabilityWeight,
        // Strategy
        strategy: config.strategy,
        topPercentile: config.topPercentile,
        maxPositionPct: config.maxPositionPct,
      })

      // Also run equal weight for comparison if using FAI strategy
      let comparison: { strategy: 'equal_weight'; total_return: number; sharpe_ratio: number; equity_curve: { date: string; value: number }[] } | undefined = undefined
      if (config.strategy === 'fai_weighted') {
        const ewData = await api.simulatePortfolioV2({
          intervalDays: config.rebalanceDays,
          initialCapital: 100,
          startDate: config.startDate,
          endDate: config.endDate,
          minAgeDays: config.minAgeDays,
          minReserveTao: config.minReserveTao,
          maxOutflow7dPct: config.maxOutflow7dPct,
          maxDrawdownPct: config.maxDrawdownPct,
          faiWeight: config.faiWeight,
          reserveWeight: config.reserveWeight,
          emissionWeight: config.emissionWeight,
          stabilityWeight: config.stabilityWeight,
          strategy: 'equal_weight',  // Compare against equal weight
          topPercentile: config.topPercentile,
          maxPositionPct: config.maxPositionPct,
        })
        comparison = {
          strategy: 'equal_weight' as const,
          total_return: ewData.total_return,
          sharpe_ratio: ewData.summary.win_rate > 0 ? ewData.total_return / Math.max(ewData.summary.max_drawdown_pct, 0.01) : 0,
          equity_curve: ewData.equity_curve.map((e: PortfolioEquityPoint) => ({ date: e.date, value: e.value }))
        }
      }

      // Transform the simulation data to match our results format
      const backtestResults: BacktestResults = {
        strategy: config.strategy,
        start_date: simData.start_date,
        end_date: simData.end_date,
        initial_capital: simData.initial_capital,
        final_value: simData.final_value,
        total_return: simData.total_return,
        sharpe_ratio: simData.summary.win_rate > 0 ? simData.total_return / Math.max(simData.summary.max_drawdown_pct, 0.01) : 0,
        max_drawdown: simData.summary.max_drawdown_pct,
        win_rate: simData.summary.win_rate,
        avg_holdings: simData.summary.avg_holdings_per_period,
        num_periods: simData.num_periods,
        equity_curve: simData.equity_curve,
        periods: simData.periods.map((p: PortfolioPeriod) => ({
          date: p.date,
          portfolio_value: p.portfolio_value,
          period_return: p.period_return,
          cumulative_return: (p.portfolio_value - simData.initial_capital) / simData.initial_capital,
          holdings: p.holdings,
          in_root: p.in_root,
          num_holdings: p.holdings.length
        })),
        comparison
      }

      setResults(backtestResults)
    } catch (e: unknown) {
      setError(e instanceof Error ? e.message : 'Backtest failed')
    } finally {
      setIsRunning(false)
    }
  }

  return (
    <div className="space-y-6 w-full">
      {/* Header */}
      <div>
        <h1 className="text-2xl font-bold">Backtesting</h1>
        <p className="text-sm text-[#6f87a0] mt-1">
          Test viability and allocation strategies against historical data
        </p>
      </div>

      {/* Historical Data Backfill */}
      <div className="bg-[#121f2d] rounded-lg border border-[#1e3a5f] p-5">
        <div className="flex items-center justify-between">
          <div>
            <h2 className="text-lg font-semibold text-white">Historical Data</h2>
            <p className="text-xs text-[#5a7a94] mt-0.5">
              Fetch daily pool snapshots from TaoStats for backtesting (up to 12 months)
            </p>
          </div>
          <button
            onClick={triggerBackfill}
            disabled={isBackfilling}
            className="flex items-center gap-2 px-4 py-2 bg-[#1a2d42] hover:bg-[#243a52] rounded text-sm text-[#8faabe] disabled:opacity-50"
          >
            {isBackfilling ? <Loader2 size={16} className="animate-spin" /> : <Download size={16} />}
            {isBackfilling ? 'Backfilling...' : 'Fetch History'}
          </button>
        </div>

        {backfillStatus && (
          <div className="mt-4 text-sm text-[#6f87a0]">
            {backfillStatus.running ? (
              <div className="space-y-2">
                <div className="flex items-center gap-2">
                  <Loader2 size={14} className="animate-spin text-tao-400" />
                  <span>
                    Processing subnet {backfillStatus.current_netuid} ({backfillStatus.completed_subnets}/{backfillStatus.total_subnets})
                  </span>
                </div>
                <div className="w-full bg-[#1a2d42] rounded-full h-2">
                  <div
                    className="bg-tao-500 h-2 rounded-full transition-all"
                    style={{ width: `${backfillStatus.total_subnets > 0 ? (backfillStatus.completed_subnets / backfillStatus.total_subnets) * 100 : 0}%` }}
                  />
                </div>
                <span className="text-xs text-[#5a7a94]">{backfillStatus.total_records_created.toLocaleString()} records created</span>
              </div>
            ) : backfillStatus.finished_at ? (
              <div className="flex items-center gap-2">
                <CheckCircle size={14} className="text-green-400" />
                <span>
                  Last backfill: {backfillStatus.total_records_created.toLocaleString()} records
                  {backfillStatus.errors.length > 0 && ` (${backfillStatus.errors.length} errors)`}
                </span>
              </div>
            ) : null}
          </div>
        )}

        {/* Important note about data requirements */}
        <div className="mt-4 flex items-start gap-2 text-xs text-[#5a7a94] bg-[#050d15]/40 rounded p-3 border border-[#1e3a5f]/50">
          <Info className="w-4 h-4 mt-0.5 flex-shrink-0 text-tao-400" />
          <div>
            <p className="font-medium text-[#a8c4d9]">Important: AMM Model Change</p>
            <p className="mt-1">
              Bittensor changed their AMM model on November 5, 2025. Only data after this date is relevant
              for flow-based strategy analysis. The backtest automatically enforces this minimum date.
            </p>
          </div>
        </div>
      </div>

      {/* Error Display */}
      {error && (
        <div className="text-sm text-red-400 bg-red-900/20 rounded-lg p-4 flex items-center gap-2 border border-red-900/50">
          <AlertTriangle className="w-5 h-5" />
          <div>
            <p className="font-medium">Backtest Error</p>
            <p className="text-red-300">{error}</p>
          </div>
        </div>
      )}

      {/* Main Content */}
      <div className="grid grid-cols-1 xl:grid-cols-2 gap-6">
        {/* Configuration Panel */}
        <ConfigurationPanel
          config={config}
          onChange={setConfig}
          onRun={runBacktest}
          isRunning={isRunning}
        />

        {/* Results Panel */}
        <ResultsPanel
          results={results}
          isLoading={isRunning}
        />
      </div>

      {/* Optimization Section (Collapsible) */}
      <div className="border border-[#1e3a5f] rounded-lg overflow-hidden">
        <button
          onClick={() => setShowOptimization(!showOptimization)}
          className="w-full flex items-center justify-between p-4 bg-[#121f2d] hover:bg-[#162636] transition-colors"
        >
          <div className="flex items-center gap-3">
            {showOptimization ? (
              <ChevronDown className="w-5 h-5 text-[#6f87a0]" />
            ) : (
              <ChevronRight className="w-5 h-5 text-[#6f87a0]" />
            )}
            <div className="text-left">
              <h2 className="text-lg font-semibold text-white">Parameter Optimization</h2>
              <p className="text-xs text-[#5a7a94]">
                Find optimal parameter combinations through automated grid search
              </p>
            </div>
          </div>
          <span className="text-xs text-[#5a7a94] bg-[#1a2d42] px-2 py-1 rounded">
            {showOptimization ? 'Click to collapse' : 'Click to expand'}
          </span>
        </button>

        {showOptimization && (
          <div className="p-4 bg-[#0a1520] border-t border-[#1e3a5f]">
            <OptimizationPanel
              onApplyConfig={handleApplyOptimizationConfig}
              isBacktestRunning={isRunning}
            />
          </div>
        )}
      </div>
    </div>
  )
}
