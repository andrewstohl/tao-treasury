import { useState } from 'react'
import { useQuery, useMutation, useQueryClient } from '@tanstack/react-query'
import {
  Shield,
  AlertTriangle,
  CheckCircle,
  XCircle,
  TrendingUp,
  RefreshCw,
  ChevronDown,
  ChevronUp,
} from 'lucide-react'
import { api } from '../services/api'
import {
  StrategyAnalysis,
  ConstraintStatus,
  EligibleSubnet,
  PositionLimit,
  RebalanceResult,
} from '../types'

function formatTao(value: number): string {
  return value.toLocaleString(undefined, { minimumFractionDigits: 1, maximumFractionDigits: 1 })
}

const stateColors = {
  healthy: 'bg-green-600/20 text-green-400 border-green-600',
  caution: 'bg-yellow-600/20 text-yellow-400 border-yellow-600',
  risk_off: 'bg-orange-600/20 text-orange-400 border-orange-600',
  emergency: 'bg-red-600/20 text-red-400 border-red-600',
}

const stateIcons = {
  healthy: CheckCircle,
  caution: AlertTriangle,
  risk_off: Shield,
  emergency: XCircle,
}

export default function Strategy() {
  const queryClient = useQueryClient()
  const [showEligible, setShowEligible] = useState(false)
  const [showLimits, setShowLimits] = useState(false)

  const { data: analysis, isLoading: analysisLoading } = useQuery<StrategyAnalysis>({
    queryKey: ['strategy-analysis'],
    queryFn: api.getStrategyAnalysis,
    refetchInterval: 60000,
  })

  const { data: constraints, isLoading: constraintsLoading } = useQuery<ConstraintStatus>({
    queryKey: ['constraints'],
    queryFn: api.getConstraintStatus,
    refetchInterval: 60000,
  })

  const { data: eligible } = useQuery<EligibleSubnet[]>({
    queryKey: ['eligible'],
    queryFn: api.getEligibleUniverse,
    enabled: showEligible,
  })

  const { data: limits } = useQuery<PositionLimit[]>({
    queryKey: ['position-limits'],
    queryFn: api.getPositionLimits,
    enabled: showLimits,
  })

  const weeklyRebalance = useMutation<RebalanceResult>({
    mutationFn: api.triggerWeeklyRebalance,
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ['strategy-analysis'] })
      queryClient.invalidateQueries({ queryKey: ['recommendations'] })
    },
  })

  if (analysisLoading || constraintsLoading) {
    return (
      <div className="flex items-center justify-center h-64">
        <div className="animate-spin rounded-full h-8 w-8 border-b-2 border-tao-400"></div>
      </div>
    )
  }

  if (!analysis || !constraints) {
    return (
      <div className="bg-red-900/20 border border-red-700 rounded-lg p-4">
        <p className="text-red-400">Failed to load strategy data. Make sure the backend is running.</p>
      </div>
    )
  }

  const StateIcon = stateIcons[analysis.portfolio_state]

  return (
    <div className="space-y-6">
      <div className="flex items-center justify-between">
        <h1 className="text-2xl font-bold">Strategy Engine</h1>
        <div className="flex gap-2">
          <button
            onClick={() => weeklyRebalance.mutate()}
            disabled={weeklyRebalance.isPending}
            className="flex items-center gap-2 px-4 py-2 bg-tao-600 hover:bg-tao-700 rounded-lg disabled:opacity-50"
          >
            <RefreshCw className={`w-4 h-4 ${weeklyRebalance.isPending ? 'animate-spin' : ''}`} />
            Generate Rebalance
          </button>
        </div>
      </div>

      {/* Portfolio State */}
      <div className={`rounded-lg p-6 border ${stateColors[analysis.portfolio_state]}`}>
        <div className="flex items-center gap-4">
          <StateIcon className="w-12 h-12" />
          <div>
            <div className="text-2xl font-bold capitalize">
              {analysis.portfolio_state.replace('_', ' ')}
            </div>
            <div className="text-sm opacity-80">{analysis.state_reason}</div>
          </div>
        </div>
      </div>

      {/* Summary Cards */}
      <div className="grid grid-cols-1 md:grid-cols-4 gap-4">
        <div className="bg-gray-800 rounded-lg p-4 border border-gray-700">
          <div className="text-sm text-gray-400 mb-1">Portfolio Regime</div>
          <div className="text-xl font-semibold capitalize">{analysis.portfolio_regime.replace('_', ' ')}</div>
        </div>
        <div className="bg-gray-800 rounded-lg p-4 border border-gray-700">
          <div className="text-sm text-gray-400 mb-1">Eligible Subnets</div>
          <div className="text-xl font-semibold">{analysis.eligible_subnets} / {analysis.total_subnets}</div>
        </div>
        <div className="bg-gray-800 rounded-lg p-4 border border-gray-700">
          <div className="text-sm text-gray-400 mb-1">Turnover Budget</div>
          <div className="text-xl font-semibold">{analysis.turnover_budget_remaining_pct.toFixed(1)}%</div>
        </div>
        <div className="bg-gray-800 rounded-lg p-4 border border-gray-700">
          <div className="text-sm text-gray-400 mb-1">Pending Actions</div>
          <div className="text-xl font-semibold">
            {analysis.pending_recommendations}
            {analysis.urgent_recommendations > 0 && (
              <span className="text-red-400 text-sm ml-2">({analysis.urgent_recommendations} urgent)</span>
            )}
          </div>
        </div>
      </div>

      {/* Regime Distribution */}
      <div className="bg-gray-800 rounded-lg p-6 border border-gray-700">
        <h3 className="text-lg font-semibold mb-4">Position Regime Distribution</h3>
        <div className="flex gap-4 flex-wrap">
          {Object.entries(analysis.regime_summary).map(([regime, count]) => (
            <div
              key={regime}
              className={`px-4 py-2 rounded-lg ${
                regime === 'risk_on' ? 'bg-green-600/20 text-green-400' :
                regime === 'risk_off' ? 'bg-red-600/20 text-red-400' :
                regime === 'quarantine' ? 'bg-orange-600/20 text-orange-400' :
                regime === 'dead' ? 'bg-gray-600/20 text-gray-400' :
                'bg-yellow-600/20 text-yellow-400'
              }`}
            >
              <span className="capitalize">{regime.replace('_', ' ')}</span>: {count}
            </div>
          ))}
        </div>
      </div>

      {/* Regime Guide - What Each Regime Means */}
      <div className="bg-gray-800 rounded-lg p-6 border border-gray-700">
        <h3 className="text-lg font-semibold mb-4">Flow Regime Guide</h3>
        <p className="text-gray-400 text-sm mb-4">
          Regimes are determined by <strong>TAO flow</strong> - the net stake/unstake activity into each subnet.
          Positive flow = more people staking, negative flow = more people unstaking.
        </p>

        <div className="space-y-4">
          {/* Risk On */}
          <div className="bg-green-600/10 border border-green-600/30 rounded-lg p-4">
            <div className="flex items-center gap-2 mb-2">
              <div className="w-3 h-3 rounded-full bg-green-500"></div>
              <span className="font-semibold text-green-400">Risk On</span>
            </div>
            <div className="text-sm text-gray-300 mb-2">
              <strong>Criteria:</strong> 7-day flow &gt; +5% AND 14-day flow &gt; 0%
            </div>
            <div className="text-sm text-gray-400">
              <strong>Action:</strong> New buys allowed. Sleeve can expand to upper bound.
              Strong positive momentum - capital is flowing in.
            </div>
          </div>

          {/* Neutral */}
          <div className="bg-yellow-600/10 border border-yellow-600/30 rounded-lg p-4">
            <div className="flex items-center gap-2 mb-2">
              <div className="w-3 h-3 rounded-full bg-yellow-500"></div>
              <span className="font-semibold text-yellow-400">Neutral</span>
            </div>
            <div className="text-sm text-gray-300 mb-2">
              <strong>Criteria:</strong> Mixed or flat flow (doesn't meet other regime criteria)
            </div>
            <div className="text-sm text-gray-400">
              <strong>Action:</strong> Higher bar for new buys. Prefer adding to existing winners.
              Wait for clearer direction before aggressive positioning.
            </div>
          </div>

          {/* Risk Off */}
          <div className="bg-red-600/10 border border-red-600/30 rounded-lg p-4">
            <div className="flex items-center gap-2 mb-2">
              <div className="w-3 h-3 rounded-full bg-red-500"></div>
              <span className="font-semibold text-red-400">Risk Off</span>
            </div>
            <div className="text-sm text-gray-300 mb-2">
              <strong>Criteria:</strong> 7-day flow &lt; -5% OR (3-day &lt; 0 AND 7-day &lt; 0)
            </div>
            <div className="text-sm text-gray-400">
              <strong>Action:</strong> No new buys. Sleeve shrinks toward lower bound.
              Prefer Root network. Capital is leaving - defensive posture.
            </div>
          </div>

          {/* Quarantine */}
          <div className="bg-orange-600/10 border border-orange-600/30 rounded-lg p-4">
            <div className="flex items-center gap-2 mb-2">
              <div className="w-3 h-3 rounded-full bg-orange-500"></div>
              <span className="font-semibold text-orange-400">Quarantine</span>
            </div>
            <div className="text-sm text-gray-300 mb-2">
              <strong>Criteria:</strong> 7-day flow &lt; -5% AND 14-day flow &lt; -5%
            </div>
            <div className="text-sm text-gray-400">
              <strong>Action:</strong> No adds allowed. Trim 25-50% of position.
              Monitor for 48-72 hours. Sustained outflow signals potential trouble.
            </div>
          </div>

          {/* Dead */}
          <div className="bg-gray-600/10 border border-gray-600/30 rounded-lg p-4">
            <div className="flex items-center gap-2 mb-2">
              <div className="w-3 h-3 rounded-full bg-gray-500"></div>
              <span className="font-semibold text-gray-400">Dead</span>
            </div>
            <div className="text-sm text-gray-300 mb-2">
              <strong>Criteria:</strong> 7-day flow &lt; -15% AND 14-day flow &lt; -15%
            </div>
            <div className="text-sm text-gray-400">
              <strong>Action:</strong> Mandatory accelerated exit.
              Exit even if it crystallizes a larger loss - severe sustained outflow indicates fundamental problems.
            </div>
          </div>
        </div>

        <div className="mt-4 p-3 bg-gray-700/50 rounded-lg">
          <div className="text-xs text-gray-400">
            <strong>Note:</strong> These thresholds are configurable. Current settings:
            Risk-Off threshold = -5%, Quarantine threshold = -15%, Persistence = 3 days.
          </div>
        </div>
      </div>

      {/* Eligibility Gate - Why Subnets Get Excluded */}
      <div className="bg-gray-800 rounded-lg p-6 border border-gray-700">
        <h3 className="text-lg font-semibold mb-4">Eligibility Gate</h3>
        <p className="text-gray-400 text-sm mb-4">
          Subnets must pass all eligibility criteria to be considered for investment.
          Here's why subnets get excluded from the investable universe:
        </p>

        <div className="grid grid-cols-1 md:grid-cols-2 gap-3">
          <div className="bg-gray-700/30 rounded-lg p-3">
            <div className="font-medium text-sm mb-1">Low Emission Share</div>
            <div className="text-xs text-gray-400">
              Emission share &lt; 0.1% — Not enough yield generation potential
            </div>
          </div>
          <div className="bg-gray-700/30 rounded-lg p-3">
            <div className="font-medium text-sm mb-1">Low Liquidity</div>
            <div className="text-xs text-gray-400">
              Pool reserve too small — Can't enter/exit positions without excessive slippage
            </div>
          </div>
          <div className="bg-gray-700/30 rounded-lg p-3">
            <div className="font-medium text-sm mb-1">Low Holder Count</div>
            <div className="text-xs text-gray-400">
              Few unique stakers — Concentration risk, potential manipulation
            </div>
          </div>
          <div className="bg-gray-700/30 rounded-lg p-3">
            <div className="font-medium text-sm mb-1">Too New</div>
            <div className="text-xs text-gray-400">
              Below minimum age threshold — Need track record before investing
            </div>
          </div>
          <div className="bg-gray-700/30 rounded-lg p-3">
            <div className="font-medium text-sm mb-1">High Owner Take</div>
            <div className="text-xs text-gray-400">
              Owner take rate &gt; 20% — Too much value extraction from stakers
            </div>
          </div>
          <div className="bg-gray-700/30 rounded-lg p-3">
            <div className="font-medium text-sm mb-1">Negative Flow</div>
            <div className="text-xs text-gray-400">
              Sustained outflow (7d AND 14d negative) — Capital is leaving
            </div>
          </div>
          <div className="bg-gray-700/30 rounded-lg p-3">
            <div className="font-medium text-sm mb-1">High Exit Slippage</div>
            <div className="text-xs text-gray-400">
              Exit costs exceed caps — Would lose too much TAO on exit
            </div>
          </div>
          <div className="bg-gray-700/30 rounded-lg p-3">
            <div className="font-medium text-sm mb-1">Validator Quality</div>
            <div className="text-xs text-gray-400">
              Low vtrust (&lt;0.5) or high take (&gt;20%) — Validator risk
            </div>
          </div>
        </div>

        {/* Show ineligibility breakdown if we have data */}
        {analysis.ineligible_reasons && Object.keys(analysis.ineligible_reasons).length > 0 && (
          <div className="mt-4">
            <div className="text-sm font-medium mb-2">Current Exclusions by Reason:</div>
            <div className="flex gap-2 flex-wrap">
              {Object.entries(analysis.ineligible_reasons).map(([reason, count]) => (
                <div key={reason} className="bg-gray-700/50 px-2 py-1 rounded text-xs">
                  {reason}: {count}
                </div>
              ))}
            </div>
          </div>
        )}
      </div>

      {/* Position Analysis */}
      <div className="grid grid-cols-1 md:grid-cols-3 gap-4">
        <div className="bg-gray-800 rounded-lg p-4 border border-gray-700">
          <div className="flex items-center gap-2 mb-2">
            <TrendingUp className="w-5 h-5 text-yellow-400" />
            <span className="font-semibold">Overweight</span>
          </div>
          <div className="text-3xl font-bold">{analysis.overweight_count}</div>
          <div className="text-sm text-gray-500">positions above limit</div>
        </div>
        <div className="bg-gray-800 rounded-lg p-4 border border-gray-700">
          <div className="flex items-center gap-2 mb-2">
            <TrendingUp className="w-5 h-5 text-blue-400 rotate-180" />
            <span className="font-semibold">Underweight</span>
          </div>
          <div className="text-3xl font-bold">{analysis.underweight_count}</div>
          <div className="text-sm text-gray-500">positions below target</div>
        </div>
        <div className="bg-gray-800 rounded-lg p-4 border border-gray-700">
          <div className="flex items-center gap-2 mb-2">
            <XCircle className="w-5 h-5 text-red-400" />
            <span className="font-semibold">To Exit</span>
          </div>
          <div className="text-3xl font-bold">{analysis.positions_to_exit}</div>
          <div className="text-sm text-gray-500">positions flagged for exit</div>
        </div>
      </div>

      {/* Constraint Status */}
      <div className="bg-gray-800 rounded-lg p-6 border border-gray-700">
        <div className="flex items-center justify-between mb-4">
          <h3 className="text-lg font-semibold">Constraint Status</h3>
          <div className={`px-3 py-1 rounded-full text-sm ${
            constraints.all_constraints_ok ? 'bg-green-600/20 text-green-400' : 'bg-red-600/20 text-red-400'
          }`}>
            {constraints.all_constraints_ok ? 'All Clear' : `${constraints.violation_count} Violations`}
          </div>
        </div>

        {constraints.violations.length > 0 && (
          <div className="mb-4">
            <h4 className="text-sm font-semibold text-red-400 mb-2">Violations</h4>
            <div className="space-y-2">
              {constraints.violations.map((v, i) => (
                <div key={i} className="bg-red-900/20 border border-red-700 rounded-lg p-3">
                  <div className="font-medium">{v.constraint}</div>
                  <div className="text-sm text-gray-400">{v.explanation}</div>
                  <div className="text-sm text-red-400 mt-1">{v.action_required}</div>
                </div>
              ))}
            </div>
          </div>
        )}

        {constraints.warnings.length > 0 && (
          <div>
            <h4 className="text-sm font-semibold text-yellow-400 mb-2">Warnings</h4>
            <div className="space-y-2">
              {constraints.warnings.map((w, i) => (
                <div key={i} className="bg-yellow-900/20 border border-yellow-700 rounded-lg p-3">
                  <div className="font-medium">{w.constraint}</div>
                  <div className="text-sm text-gray-400">{w.explanation}</div>
                </div>
              ))}
            </div>
          </div>
        )}

        {constraints.all_constraints_ok && constraints.warnings.length === 0 && (
          <div className="text-green-400 flex items-center gap-2">
            <CheckCircle className="w-5 h-5" />
            All {constraints.total_checked} constraints satisfied
          </div>
        )}
      </div>

      {/* Eligible Universe (collapsible) */}
      <div className="bg-gray-800 rounded-lg border border-gray-700">
        <button
          onClick={() => setShowEligible(!showEligible)}
          className="w-full p-4 flex items-center justify-between hover:bg-gray-700/50"
        >
          <h3 className="text-lg font-semibold">Eligible Universe</h3>
          {showEligible ? <ChevronUp /> : <ChevronDown />}
        </button>
        {showEligible && eligible && (
          <div className="p-4 pt-0">
            <div className="overflow-x-auto">
              <table className="w-full">
                <thead>
                  <tr className="text-left text-sm text-gray-400 border-b border-gray-700">
                    <th className="pb-2">Subnet</th>
                    <th className="pb-2">Score</th>
                  </tr>
                </thead>
                <tbody>
                  {eligible.map((e) => (
                    <tr key={e.netuid} className="border-b border-gray-700/50">
                      <td className="py-2">
                        <span className="text-gray-500">SN{e.netuid}</span>{' '}
                        <span className="font-medium">{e.name}</span>
                      </td>
                      <td className="py-2">
                        <span className={`font-mono ${
                          (e.score || 0) >= 70 ? 'text-green-400' :
                          (e.score || 0) >= 50 ? 'text-yellow-400' :
                          'text-gray-400'
                        }`}>
                          {e.score || '-'}
                        </span>
                      </td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
          </div>
        )}
      </div>

      {/* Position Limits (collapsible) */}
      <div className="bg-gray-800 rounded-lg border border-gray-700">
        <button
          onClick={() => setShowLimits(!showLimits)}
          className="w-full p-4 flex items-center justify-between hover:bg-gray-700/50"
        >
          <h3 className="text-lg font-semibold">Position Limits</h3>
          {showLimits ? <ChevronUp /> : <ChevronDown />}
        </button>
        {showLimits && limits && (
          <div className="p-4 pt-0">
            <div className="overflow-x-auto">
              <table className="w-full text-sm">
                <thead>
                  <tr className="text-left text-gray-400 border-b border-gray-700">
                    <th className="pb-2">Subnet</th>
                    <th className="pb-2 text-right">Current</th>
                    <th className="pb-2 text-right">Max</th>
                    <th className="pb-2 text-right">Headroom</th>
                    <th className="pb-2">Binding</th>
                  </tr>
                </thead>
                <tbody>
                  {limits.map((l) => (
                    <tr key={l.netuid} className="border-b border-gray-700/50">
                      <td className="py-2">
                        <span className="text-gray-500">SN{l.netuid}</span>{' '}
                        <span>{l.subnet_name}</span>
                      </td>
                      <td className="py-2 text-right font-mono">
                        {formatTao(l.current_position_tao)} TAO
                      </td>
                      <td className="py-2 text-right font-mono">
                        {formatTao(l.max_position_tao)} TAO
                      </td>
                      <td className="py-2 text-right font-mono">
                        <span className={l.available_headroom_tao > 0 ? 'text-green-400' : 'text-red-400'}>
                          {formatTao(l.available_headroom_tao)} TAO
                        </span>
                      </td>
                      <td className="py-2">
                        <span className="px-2 py-1 rounded text-xs bg-gray-700">
                          {l.binding_constraint}
                        </span>
                      </td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
          </div>
        )}
      </div>

      {/* Rebalance Result */}
      {weeklyRebalance.isSuccess && weeklyRebalance.data && (
        <div className="bg-green-900/20 border border-green-700 rounded-lg p-4">
          <h3 className="font-semibold text-green-400 mb-2">Rebalance Generated</h3>
          <pre className="text-sm whitespace-pre-wrap">{weeklyRebalance.data.summary}</pre>
        </div>
      )}

      {weeklyRebalance.isError && (
        <div className="bg-red-900/20 border border-red-700 rounded-lg p-4">
          <p className="text-red-400">Failed to generate rebalance recommendations.</p>
        </div>
      )}
    </div>
  )
}
