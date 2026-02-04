import PerformanceAttribution from '../components/dashboard/PerformanceAttribution'
import RiskMetricsPanel from '../components/dashboard/RiskMetrics'
import PriceSensitivity from '../components/dashboard/PriceSensitivity'
import PositionContributions from '../components/dashboard/PositionContributions'

export default function Analysis() {
  return (
    <div className="space-y-6">
      <h1 className="text-2xl font-bold">Analysis</h1>

      {/* Performance Attribution & Income Statement */}
      <PerformanceAttribution />

      {/* Risk-Adjusted Returns & Benchmarking */}
      <RiskMetricsPanel />

      {/* TAO Price Sensitivity & Scenario Analysis */}
      <PriceSensitivity />

      {/* Per-Position Contribution Breakdown */}
      <PositionContributions />
    </div>
  )
}
