import { Routes, Route, Navigate } from 'react-router-dom'
import ExamplesSidebar from '../components/examples/ExamplesSidebar'
import AlphaGrowthOverTime from '../components/examples/portfolio/AlphaGrowthOverTime'
import StakeDistribution from '../components/examples/portfolio/StakeDistribution'
import StakeBalanceHistory from '../components/examples/portfolio/StakeBalanceHistory'
import AlphaHeatmap from '../components/examples/portfolio/AlphaHeatmap'
import AccountBalanceHistory from '../components/examples/portfolio/AccountBalanceHistory'
import StakeEarnings from '../components/examples/portfolio/StakeEarnings'
import TaxAccountingExport from '../components/examples/accounting/TaxAccountingExport'
import HotkeyProfits from '../components/examples/accounting/HotkeyProfits'
import ParentHotkeyReturns from '../components/examples/accounting/ParentHotkeyReturns'
import SubnetMarketCap from '../components/examples/subnet/SubnetMarketCap'
import DailyAlphaBurns from '../components/examples/subnet/DailyAlphaBurns'
import SubnetEmissions from '../components/examples/subnet/SubnetEmissions'
import DailyRecycleHalvening from '../components/examples/subnet/DailyRecycleHalvening'
import PriceStakeRatio from '../components/examples/subnet/PriceStakeRatio'

export default function Examples() {
  return (
    <div className="flex h-[calc(100vh-0px)] -m-6">
      <ExamplesSidebar />
      <div className="flex-1 overflow-auto p-6">
        <Routes>
          <Route path="/" element={<Navigate to="alpha-growth" replace />} />
          <Route path="alpha-growth" element={<AlphaGrowthOverTime />} />
          <Route path="stake-distribution" element={<StakeDistribution />} />
          <Route path="stake-balance-history" element={<StakeBalanceHistory />} />
          <Route path="alpha-heatmap" element={<AlphaHeatmap />} />
          <Route path="account-balance-history" element={<AccountBalanceHistory />} />
          <Route path="stake-earnings" element={<StakeEarnings />} />
          <Route path="tax-export" element={<TaxAccountingExport />} />
          <Route path="hotkey-profits" element={<HotkeyProfits />} />
          <Route path="parent-hotkey-returns" element={<ParentHotkeyReturns />} />
          <Route path="subnet-market-cap" element={<SubnetMarketCap />} />
          <Route path="daily-alpha-burns" element={<DailyAlphaBurns />} />
          <Route path="subnet-emissions" element={<SubnetEmissions />} />
          <Route path="daily-recycle" element={<DailyRecycleHalvening />} />
          <Route path="price-stake-ratio" element={<PriceStakeRatio />} />
        </Routes>
      </div>
    </div>
  )
}
