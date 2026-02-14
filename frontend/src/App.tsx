import { Routes, Route, Navigate } from 'react-router-dom'
import Layout from './components/common/Layout'
import CommandCenter from './pages/CommandCenter'
import Tournament from './pages/Tournament'
import Ledger from './pages/Ledger'

function App() {
  return (
    <Layout>
      <Routes>
        <Route path="/" element={<Navigate to="/command-center" replace />} />
        <Route path="/command-center" element={<CommandCenter />} />
        <Route path="/tournament" element={<Tournament />} />
        <Route path="/ledger" element={<Ledger />} />
        <Route path="*" element={<Navigate to="/command-center" replace />} />
      </Routes>
    </Layout>
  )
}

export default App
