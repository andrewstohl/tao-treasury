import Tooltip, { TOOLTIP_CONTENT } from './Tooltip'

interface MetricsSummaryProps {
  totalReturn: number
  sharpeRatio?: number
  maxDrawdown: number
  winRate: number
  avgHoldings: number
  numPeriods: number
  initialCapital: number
  finalValue: number
  comparisonReturn?: number | null
  comparisonSharpe?: number | null
}

export default function MetricsSummary({
  totalReturn,
  sharpeRatio,
  maxDrawdown,
  winRate,
  avgHoldings,
  numPeriods,
  initialCapital,
  finalValue,
  comparisonReturn,
  comparisonSharpe,
}: MetricsSummaryProps) {
  return (
    <div className="grid grid-cols-2 md:grid-cols-3 lg:grid-cols-5 gap-3">
      <StatCard
        label="Total Return"
        value={`${totalReturn >= 0 ? '+' : ''}${(totalReturn * 100).toFixed(1)}%`}
        sub={`${initialCapital} → ${finalValue.toFixed(1)} TAO`}
        color={totalReturn >= 0 ? 'text-green-400' : 'text-red-400'}
        comparison={comparisonReturn != null ? `EW: ${comparisonReturn >= 0 ? '+' : ''}${(comparisonReturn * 100).toFixed(1)}%` : undefined}
        tooltip={TOOLTIP_CONTENT.totalReturn}
      />
      {sharpeRatio != null && (
        <StatCard
          label="Sharpe Ratio"
          value={sharpeRatio.toFixed(2)}
          sub="Risk-adjusted return"
          color={sharpeRatio > 1 ? 'text-green-400' : sharpeRatio > 0 ? 'text-yellow-400' : 'text-red-400'}
          comparison={comparisonSharpe != null ? `EW: ${comparisonSharpe.toFixed(2)}` : undefined}
          tooltip={TOOLTIP_CONTENT.sharpeRatio}
        />
      )}
      <StatCard
        label="Win Rate"
        value={`${(winRate * 100).toFixed(0)}%`}
        sub={`${numPeriods} periods`}
        color={winRate > 0.5 ? 'text-green-400' : 'text-yellow-400'}
        tooltip={TOOLTIP_CONTENT.winRate}
      />
      <StatCard
        label="Max Drawdown"
        value={`-${(maxDrawdown * 100).toFixed(1)}%`}
        sub="Peak to trough"
        color="text-red-400"
        tooltip={TOOLTIP_CONTENT.maxDrawdown}
      />
      <StatCard
        label="Avg Holdings"
        value={`${avgHoldings.toFixed(0)}`}
        sub="Subnets per period"
        color="text-[#8faabe]"
        tooltip={TOOLTIP_CONTENT.avgHoldings}
      />
    </div>
  )
}

function StatCard({
  label,
  value,
  sub,
  color,
  comparison,
  tooltip
}: {
  label: string
  value: string
  sub: string
  color: string
  comparison?: string
  tooltip?: string
}) {
  return (
    <div className="bg-[#050d15]/60 rounded-lg p-3 border border-[#1e3a5f]">
      <div className="text-xs text-[#5a7a94] flex items-center gap-1">
        {label}
        {tooltip && <Tooltip content={tooltip} />}
      </div>
      <div className={`text-xl tabular-nums font-bold mt-1 ${color}`}>{value}</div>
      <div className="text-[10px] text-[#243a52] mt-0.5">{sub}</div>
      {comparison && (
        <div className="text-[10px] text-[#5a7a94] mt-1 border-t border-[#1e3a5f] pt-1">
          {comparison}
        </div>
      )}
    </div>
  )
}
