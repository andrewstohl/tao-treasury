import { Routes, Route, Navigate } from 'react-router-dom'
import Layout from './components/common/Layout'
import PasswordGate from './components/auth/PasswordGate'
import CommandCenter from './pages/CommandCenter'
import Tournament from './pages/Tournament'
import StrategyDetail from './pages/StrategyDetail'
import Compare from './pages/Compare'
import Ledger from './pages/Ledger'
import ProposalQueue from './pages/ProposalQueue'
import Wiki from './pages/Wiki'
import Discover from './pages/Discover'
import Track from './pages/Track'
import Trading from './pages/Trading'

function App() {
  return (
    <PasswordGate>
      <Layout>
        <Routes>
          <Route path="/" element={<Navigate to="/track" replace />} />
          <Route path="/track" element={<Track />} />
          <Route path="/trading" element={<Trading />} />
          <Route path="/command-center" element={<CommandCenter />} />
          <Route path="/tournament" element={<Tournament />} />
          <Route path="/strategy/:strategyId" element={<StrategyDetail />} />
          <Route path="/compare" element={<Compare />} />
          <Route path="/ledger" element={<Ledger />} />
          <Route path="/proposals" element={<ProposalQueue />} />
          <Route path="/wiki" element={<Wiki />} />
          <Route path="/discover" element={<Discover />} />
          <Route path="*" element={<Navigate to="/track" replace />} />
        </Routes>
      </Layout>
    </PasswordGate>
  )
}

export default App
