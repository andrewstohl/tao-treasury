import { Routes, Route, Navigate } from 'react-router-dom'
import Layout from './components/common/Layout'
import CommandCenter from './pages/CommandCenter'
import Tournament from './pages/Tournament'
import StrategyDetail from './pages/StrategyDetail'
import Compare from './pages/Compare'
import Ledger from './pages/Ledger'
import ProposalQueue from './pages/ProposalQueue'
import Wiki from './pages/Wiki'
import Portfolio from './pages/Portfolio'
import Discover from './pages/Discover'
import Track from './pages/Track'

function App() {
  return (
    <Layout>
      <Routes>
        <Route path="/" element={<Navigate to="/portfolio" replace />} />
        <Route path="/portfolio" element={<Portfolio />} />
        <Route path="/track" element={<Track />} />
        <Route path="/command-center" element={<CommandCenter />} />
        <Route path="/tournament" element={<Tournament />} />
        <Route path="/strategy/:strategyId" element={<StrategyDetail />} />
        <Route path="/compare" element={<Compare />} />
        <Route path="/ledger" element={<Ledger />} />
        <Route path="/proposals" element={<ProposalQueue />} />
        <Route path="/wiki" element={<Wiki />} />
        <Route path="/discover" element={<Discover />} />
        <Route path="*" element={<Navigate to="/portfolio" replace />} />
      </Routes>
    </Layout>
  )
}

export default App
