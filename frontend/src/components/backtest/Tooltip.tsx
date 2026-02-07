import { useState, ReactNode } from 'react'
import { HelpCircle } from 'lucide-react'

interface TooltipProps {
  content: string
  children?: ReactNode
}

export default function Tooltip({ content, children }: TooltipProps) {
  const [isVisible, setIsVisible] = useState(false)

  return (
    <span
      className="relative inline-flex items-center"
      onMouseEnter={() => setIsVisible(true)}
      onMouseLeave={() => setIsVisible(false)}
    >
      {children || <HelpCircle className="w-3.5 h-3.5 text-[#5a7a94] hover:text-[#8faabe] cursor-help" />}
      {isVisible && (
        <div className="absolute z-50 bottom-full left-1/2 -translate-x-1/2 mb-2 px-3 py-2 text-xs text-white bg-[#1a2d42] rounded-lg shadow-lg border border-[#2a4a66] whitespace-normal w-64">
          {content}
          <div className="absolute top-full left-1/2 -translate-x-1/2 -mt-1">
            <div className="border-4 border-transparent border-t-[#1a2d42]" />
          </div>
        </div>
      )}
    </span>
  )
}

// Predefined tooltip content for backtest metrics
export const TOOLTIP_CONTENT = {
  sharpeRatio: "Risk-adjusted return metric. Higher is better. Calculated as (Return / Max Drawdown). A Sharpe > 1 is good, > 2 is excellent.",
  totalReturn: "Total portfolio return over the backtest period, expressed as a percentage of initial capital.",
  maxDrawdown: "Largest peak-to-trough decline during the backtest. Lower is better. Indicates worst-case loss scenario.",
  winRate: "Percentage of rebalancing periods with positive returns. Higher indicates more consistent performance.",
  avgHoldings: "Average number of subnets held in the portfolio per rebalancing period.",

  minAge: "Minimum age requirement for subnet viability. Older subnets have more established track records.",
  minReserve: "Minimum TAO reserve in the pool. Higher reserves indicate more liquidity and stability.",
  maxOutflow: "Maximum allowed 7-day outflow as percentage of reserve. Protects against sudden capital flight.",
  maxDrawdown30d: "Maximum allowed 30-day drawdown. Filters out highly volatile or declining subnets.",

  faiWeight: "Flow Accumulation Index weight. Measures net TAO inflow momentum relative to pool size.",
  reserveWeight: "TAO Reserve weight. Larger reserves indicate better liquidity and market confidence.",
  emissionWeight: "Emission Share weight. Higher emissions mean more TAO rewards flowing to the subnet.",
  stabilityWeight: "Stability weight. Based on inverse of max drawdown - lower volatility scores higher.",

  topPercentile: "After scoring all viable subnets, select the top N% by viability score for the portfolio.",
  maxPosition: "Maximum weight allowed for a single position. Limits concentration risk.",
  rebalanceDays: "How often to rebalance the portfolio. Weekly (7 days) recommended for lower turnover.",

  equalWeight: "Each selected subnet gets equal weight in the portfolio. Research shows this outperforms on risk-adjusted basis.",
  faiWeighted: "Weight positions by their viability score. Higher-scored subnets get larger allocations.",
}
