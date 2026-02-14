import { useState } from 'react'
import { ChevronDown, ChevronUp } from 'lucide-react'
import { TradingSystem } from './mockData'
import { EquityCurveChart, PnlDistributionChart, WinLossDonut, SignalStrengthBar } from './Charts'

interface SystemPanelProps {
  system: TradingSystem
}

export function SystemPanel({ system }: SystemPanelProps) {
  const [activeTab, setActiveTab] = useState<'metrics' | 'trades'>('metrics')
  const [showAnalysis, setShowAnalysis] = useState(false)

  const formatCurrency = (val: number) => {
    if (val >= 1000) return `$${(val / 1000).toFixed(1)}K`
    return `$${val.toFixed(0)}`
  }

  const formatNumber = (val: number) => val.toLocaleString()

  const signalColor = system.currentSignal === 'LONG' ? 'bg-green-500/20 text-green-400 border-green-500/30' : 
                      system.currentSignal === 'SHORT' ? 'bg-red-500/20 text-red-400 border-red-500/30' :
                      'bg-gray-500/20 text-gray-400 border-gray-500/30'

  return (
    <div className="bg-[#16181d] rounded-xl border border-[#2a2f38] overflow-hidden">
      {/* Header */}
      <div className="px-4 py-3 border-b border-[#2a2f38]">
        <div className="flex items-center justify-between">
          <div>
            <h3 className="text-lg font-semibold text-white">{system.name}</h3>
            <p className="text-xs text-[#6b7280]">{system.params}</p>
          </div>
          <div className={`px-3 py-1 rounded-lg border text-sm font-medium ${signalColor}`}>
            {system.currentSignal}
          </div>
        </div>
      </div>

      {/* Signal Status */}
      <div className="px-4 py-3 bg-[#0d1117]/50 border-b border-[#2a2f38]">
        <div className="grid grid-cols-2 gap-4">
          <div>
            <div className="text-xs text-[#6b7280] mb-1">Signal Age</div>
            <div className="text-sm text-white">
              <span className="font-medium">{system.signalAgeBars}</span>
              <span className="text-[#6b7280]"> bars / </span>
              <span className="font-medium">{system.signalAgeDays}</span>
              <span className="text-[#6b7280]"> days</span>
            </div>
          </div>
          <div>
            <div className="text-xs text-[#6b7280] mb-1">Key Levels</div>
            <div className="text-sm text-white">
              <span className="text-green-400">{system.upperBand.toFixed(2)}</span>
              <span className="text-[#6b7280]"> / </span>
              <span className="text-red-400">{system.lowerBand.toFixed(2)}</span>
            </div>
          </div>
        </div>
        <div className="mt-3">
          <div className="text-xs text-[#6b7280] mb-2">Signal Strength</div>
          <SignalStrengthBar strength={system.strength} />
        </div>
      </div>

      {/* Tabs */}
      <div className="px-4 pt-3">
        <div className="flex gap-1 bg-[#0d1117] p-1 rounded-lg">
          <button
            onClick={() => setActiveTab('metrics')}
            className={`flex-1 px-3 py-1.5 text-sm font-medium rounded-md transition-colors ${
              activeTab === 'metrics' ? 'bg-[#2a3ded] text-white' : 'text-[#9ca3af] hover:text-white'
            }`}
          >
            Metrics
          </button>
          <button
            onClick={() => setActiveTab('trades')}
            className={`flex-1 px-3 py-1.5 text-sm font-medium rounded-md transition-colors ${
              activeTab === 'trades' ? 'bg-[#2a3ded] text-white' : 'text-[#9ca3af] hover:text-white'
            }`}
          >
            List of Trades
          </button>
        </div>
      </div>

      {/* Content */}
      <div className="p-4">
        {activeTab === 'metrics' ? (
          <div className="space-y-4">
            {/* KPI Cards */}
            <div className="grid grid-cols-5 gap-2">
              <div className="bg-[#0d1117] rounded-lg p-2 text-center">
                <div className="text-xs text-[#6b7280]">Total P&L</div>
                <div className={`text-sm font-semibold ${system.metrics.totalPnl >= 0 ? 'text-green-400' : 'text-red-400'}`}>
                  {formatCurrency(system.metrics.totalPnl)}
                </div>
              </div>
              <div className="bg-[#0d1117] rounded-lg p-2 text-center">
                <div className="text-xs text-[#6b7280]">Max DD</div>
                <div className="text-sm font-semibold text-red-400">{system.metrics.maxDD}%</div>
              </div>
              <div className="bg-[#0d1117] rounded-lg p-2 text-center">
                <div className="text-xs text-[#6b7280]">Trades</div>
                <div className="text-sm font-semibold text-white">{formatNumber(system.metrics.trades)}</div>
              </div>
              <div className="bg-[#0d1117] rounded-lg p-2 text-center">
                <div className="text-xs text-[#6b7280]">Win Rate</div>
                <div className="text-sm font-semibold text-green-400">{system.metrics.winRate}%</div>
              </div>
              <div className="bg-[#0d1117] rounded-lg p-2 text-center">
                <div className="text-xs text-[#6b7280]">PF</div>
                <div className="text-sm font-semibold text-white">{system.metrics.profitFactor}</div>
              </div>
            </div>

            {/* Equity Curve */}
            <div className="bg-[#0d1117] rounded-lg p-3">
              <div className="flex items-center justify-between mb-2">
                <span className="text-xs text-[#6b7280]">Equity Curve</span>
                <span className="text-xs text-green-400">Sharpe: {system.metrics.sharpe}</span>
              </div>
              <div className="h-32">
                <EquityCurveChart 
                  data={system.equityCurve} 
                  color={system.metrics.totalPnl >= 0 ? '#10b981' : '#ef4444'}
                />
              </div>
            </div>

            {/* Collapsible Trades Analysis */}
            <div className="border border-[#2a2f38] rounded-lg overflow-hidden">
              <button
                onClick={() => setShowAnalysis(!showAnalysis)}
                className="w-full px-3 py-2 bg-[#0d1117] flex items-center justify-between hover:bg-[#16181d] transition-colors"
              >
                <span className="text-sm font-medium text-white">Trades Analysis</span>
                {showAnalysis ? <ChevronUp className="w-4 h-4 text-[#6b7280]" /> : <ChevronDown className="w-4 h-4 text-[#6b7280]" />}
              </button>
              {showAnalysis && (
                <div className="p-3 grid grid-cols-2 gap-4">
                  <div>
                    <div className="text-xs text-[#6b7280] mb-2 text-center">P&L Distribution</div>
                    <div className="h-24">
                      <PnlDistributionChart distribution={system.pnlDistribution} />
                    </div>
                  </div>
                  <div>
                    <div className="text-xs text-[#6b7280] mb-2 text-center">Win/Loss</div>
                    <div className="h-24 flex items-center justify-center">
                      <WinLossDonut wins={system.winLossStats.wins} losses={system.winLossStats.losses} />
                    </div>
                  </div>
                </div>
              )}
            </div>
          </div>
        ) : (
          <div className="overflow-x-auto">
            <table className="w-full text-xs">
              <thead>
                <tr className="text-left text-[#6b7280] border-b border-[#2a2f38]">
                  <th className="pb-2 font-medium">#</th>
                  <th className="pb-2 font-medium">Type</th>
                  <th className="pb-2 font-medium">Date</th>
                  <th className="pb-2 font-medium">Signal</th>
                  <th className="pb-2 font-medium text-right">Price</th>
                  <th className="pb-2 font-medium text-right">Size</th>
                  <th className="pb-2 font-medium text-right">P&L</th>
                  <th className="pb-2 font-medium text-right">Cum P&L</th>
                </tr>
              </thead>
              <tbody className="divide-y divide-[#2a2f38]/50">
                {system.trades.map((trade) => (
                  <tr key={trade.id} className="hover:bg-[#0d1117]/50">
                    <td className="py-2">
                      <span className={`px-1.5 py-0.5 rounded text-xs font-medium ${
                        trade.signal === 'LONG' ? 'bg-green-500/20 text-green-400' : 'bg-red-500/20 text-red-400'
                      }`}>
                        #{trade.id}
                      </span>
                    </td>
                    <td className="py-2 text-[#9ca3af]">{trade.entryExit}</td>
                    <td className="py-2 text-[#9ca3af]">{trade.date}</td>
                    <td className="py-2">
                      <span className={trade.signal === 'LONG' ? 'text-green-400' : 'text-red-400'}>
                        {trade.signal}
                      </span>
                    </td>
                    <td className="py-2 text-right tabular-nums text-white">{trade.price.toFixed(2)}</td>
                    <td className="py-2 text-right">
                      <div className="tabular-nums text-white">{trade.sizeTao} TAO</div>
                      <div className="text-[#6b7280] text-[10px]">${(trade.sizeUsd / 1000).toFixed(1)}K</div>
                    </td>
                    <td className="py-2 text-right tabular-nums">
                      {trade.pnlUsd !== 0 ? (
                        <span className={trade.pnlUsd >= 0 ? 'text-green-400' : 'text-red-400'}>
                          {trade.pnlUsd >= 0 ? '+' : ''}{formatCurrency(trade.pnlUsd)}
                        </span>
                      ) : (
                        <span className="text-[#6b7280]">-</span>
                      )}
                    </td>
                    <td className="py-2 text-right tabular-nums">
                      <span className={trade.cumulative >= 0 ? 'text-green-400' : 'text-red-400'}>
                        {trade.cumulative >= 0 ? '+' : ''}{formatCurrency(trade.cumulative)}
                      </span>
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        )}
      </div>

      {/* Position Sizing Block */}
      <div className="px-4 py-3 bg-[#0d1117] border-t border-[#2a2f38]">
        <div className="text-xs font-medium text-[#6b7280] mb-2">Position Sizing</div>
        <div className="grid grid-cols-2 gap-3">
          <div className="space-y-1">
            <div className="flex justify-between text-xs">
              <span className="text-[#6b7280]">Current Position:</span>
              <span className={system.position.side === 'flat' ? 'text-[#9ca3af]' : system.position.side === 'long' ? 'text-green-400' : 'text-red-400'}>
                {system.position.side === 'flat' ? 'Flat' : `${system.position.side === 'long' ? '+' : '-'}${system.position.size} TAO`}
              </span>
            </div>
            <div className="flex justify-between text-xs">
              <span className="text-[#6b7280]">Entry Price:</span>
              <span className="text-white">{system.position.entry > 0 ? `$${system.position.entry}` : '-'}</span>
            </div>
            <div className="flex justify-between text-xs">
              <span className="text-[#6b7280]">Unrealized P&L:</span>
              <span className={system.position.pnl >= 0 ? 'text-green-400' : 'text-red-400'}>
                {system.position.pnl > 0 ? '+' : ''}{system.position.pnl !== 0 ? `$${system.position.pnl}` : '-'}
              </span>
            </div>
          </div>
          <div className="space-y-1">
            <div className="flex justify-between text-xs">
              <span className="text-[#6b7280]">Kelly Optimal:</span>
              <span className="text-white">{system.position.kelly}x</span>
            </div>
            <div className="flex justify-between text-xs">
              <span className="text-[#6b7280]">Max Size (2x):</span>
              <span className="text-white">{system.position.maxSize2x} TAO</span>
            </div>
            <div className="flex justify-between text-xs">
              <span className="text-[#6b7280]">Liquidation (5x):</span>
              <span className="text-red-400">${system.position.liqPrice5x}</span>
            </div>
          </div>
        </div>
      </div>
    </div>
  )
}
