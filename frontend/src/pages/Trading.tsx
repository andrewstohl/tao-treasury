import { TrendingUp, TrendingDown, Scale, AlertTriangle, Activity, Wallet } from 'lucide-react'
import { MOCK_TAO_PRICE, MOCK_PORTFOLIO, MOCK_HEDGE_SYSTEM, MOCK_SWING_SYSTEM, CAPITAL_ALLOCATION } from './trading/mockData'
import { SystemPanel } from './trading/SystemPanel'

export default function Trading() {
  const formatCurrency = (val: number) => {
    if (Math.abs(val) >= 1000) return `$${(val / 1000).toFixed(1)}K`
    return `$${val.toFixed(0)}`
  }

  const accountEquity = MOCK_PORTFOLIO.hyperliquidBalance + MOCK_PORTFOLIO.unrealizedPnl

  const kpiCards = [
    {
      label: 'TAO Price',
      value: `$${MOCK_TAO_PRICE.current.toFixed(2)}`,
      subtext: `${MOCK_TAO_PRICE.change24h >= 0 ? '+' : ''}${MOCK_TAO_PRICE.change24hPct}% ($${MOCK_TAO_PRICE.change24h})`,
      icon: MOCK_TAO_PRICE.change24h >= 0 ? TrendingUp : TrendingDown,
      positive: MOCK_TAO_PRICE.change24h >= 0
    },
    {
      label: 'Net Exposure',
      value: `${MOCK_PORTFOLIO.netExposure} TAO`,
      subtext: `${MOCK_PORTFOLIO.spotTao} spot / ${MOCK_PORTFOLIO.shortTao} short`,
      icon: Scale,
      positive: null
    },
    {
      label: 'Unrealized P&L',
      value: formatCurrency(MOCK_PORTFOLIO.unrealizedPnl),
      subtext: 'Open position P&L',
      icon: Activity,
      positive: MOCK_PORTFOLIO.unrealizedPnl >= 0
    },
    {
      label: 'Gap to Close',
      value: formatCurrency(MOCK_PORTFOLIO.gapToClose),
      subtext: 'To achieve delta neutral',
      icon: AlertTriangle,
      positive: null
    },
    {
      label: 'Daily VaR',
      value: formatCurrency(MOCK_PORTFOLIO.dailyVar),
      subtext: '95% confidence',
      icon: AlertTriangle,
      positive: null
    },
    {
      label: 'Account Equity',
      value: formatCurrency(accountEquity),
      subtext: `Balance: ${formatCurrency(MOCK_PORTFOLIO.hyperliquidBalance)}`,
      icon: Wallet,
      positive: accountEquity >= MOCK_PORTFOLIO.hyperliquidBalance
    }
  ]

  return (
    <div className="space-y-6">
      {/* Header */}
      <div className="flex items-center justify-between">
        <div>
          <h1 className="text-2xl font-bold text-white">Trading</h1>
          <p className="text-sm text-[#6b7280]">Strategy monitoring & position management</p>
        </div>
      </div>

      {/* KPI Cards */}
      <div className="grid grid-cols-2 md:grid-cols-3 lg:grid-cols-6 gap-4">
        {kpiCards.map((card, index) => {
          const Icon = card.icon
          return (
            <div key={index} className="bg-[#16181d] rounded-xl border border-[#2a2f38] p-4">
              <div className="flex items-start justify-between">
                <div className="flex-1 min-w-0">
                  <p className="text-xs text-[#6b7280] mb-1">{card.label}</p>
                  <p className={`text-lg font-semibold ${
                    card.positive === null ? 'text-white' :
                    card.positive ? 'text-green-400' : 'text-red-400'
                  }`}>
                    {card.value}
                  </p>
                  <p className="text-xs text-[#6b7280] mt-1 truncate">{card.subtext}</p>
                </div>
                <Icon className={`w-5 h-5 flex-shrink-0 ${
                  card.positive === null ? 'text-[#6b7280]' :
                  card.positive ? 'text-green-400' : 'text-red-400'
                }`} />
              </div>
            </div>
          )
        })}
      </div>

      {/* System Panels Grid */}
      <div className="grid grid-cols-1 xl:grid-cols-2 gap-6">
        <SystemPanel system={MOCK_HEDGE_SYSTEM} />
        <SystemPanel system={MOCK_SWING_SYSTEM} />
      </div>

      {/* Capital Allocation Flywheel */}
      <div className="bg-[#16181d] rounded-xl border border-[#2a2f38] p-6">
        <h2 className="text-lg font-semibold text-white mb-4">Capital Allocation Flywheel</h2>
        
        <div className="grid grid-cols-1 md:grid-cols-3 gap-6">
          {/* Recovery Progress */}
          <div>
            <div className="flex items-center justify-between mb-2">
              <span className="text-sm text-[#9ca3af]">Recovery Progress</span>
              <span className="text-sm font-medium text-white">{(CAPITAL_ALLOCATION.recoveryProgress * 100).toFixed(1)}%</span>
            </div>
            <div className="h-3 bg-[#0d1117] rounded-full overflow-hidden border border-[#2a2f38]">
              <div
                className="h-full bg-gradient-to-r from-[#2a3ded] to-[#5b6cf6] rounded-full transition-all duration-500"
                style={{ width: `${CAPITAL_ALLOCATION.recoveryProgress * 100}%` }}
              />
            </div>
            <p className="text-xs text-[#6b7280] mt-2">Progress toward target NAV recovery</p>
          </div>

          {/* Profit Split Visualization */}
          <div className="md:col-span-2">
            <div className="text-sm text-[#9ca3af] mb-3">Short Profit Split</div>
            <div className="flex h-12 rounded-lg overflow-hidden">
              <div 
                className="flex items-center justify-center bg-blue-500/80 text-white text-sm font-medium"
                style={{ width: `${CAPITAL_ALLOCATION.shortProfitSplit.dca}%` }}
              >
                <div className="text-center">
                  <div>DCA</div>
                  <div className="text-xs opacity-80">{CAPITAL_ALLOCATION.shortProfitSplit.dca}%</div>
                </div>
              </div>
              <div 
                className="flex items-center justify-center bg-purple-500/80 text-white text-sm font-medium"
                style={{ width: `${CAPITAL_ALLOCATION.shortProfitSplit.margin}%` }}
              >
                <div className="text-center">
                  <div>Margin</div>
                  <div className="text-xs opacity-80">{CAPITAL_ALLOCATION.shortProfitSplit.margin}%</div>
                </div>
              </div>
            </div>
            <div className="flex justify-between text-xs text-[#6b7280] mt-2">
              <span>Short profits are split between DCA accumulation and margin buffer</span>
              <span>Total: 100%</span>
            </div>
          </div>
        </div>

        {/* Legend */}
        <div className="flex flex-wrap gap-4 mt-4 pt-4 border-t border-[#2a2f38]">
          <div className="flex items-center gap-2">
            <div className="w-3 h-3 rounded bg-blue-500/80"></div>
            <span className="text-xs text-[#9ca3af]">DCA — Dollar cost average into spot position</span>
          </div>
          <div className="flex items-center gap-2">
            <div className="w-3 h-3 rounded bg-purple-500/80"></div>
            <span className="text-xs text-[#9ca3af]">Margin — Reinforce short position buffer</span>
          </div>
        </div>
      </div>
    </div>
  )
}
