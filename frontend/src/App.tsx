import { Routes, Route, Navigate } from 'react-router-dom'
import Layout from './components/common/Layout'
import PasswordGate from './components/auth/PasswordGate'
import Discover from './pages/Discover'
import Track from './pages/Track'
import Trading from './pages/Trading'
import Wiki from './pages/Wiki'
import Kanban from './pages/Kanban'

function App() {
  return (
    <PasswordGate>
      <Layout>
        <Routes>
          <Route path="/" element={<Navigate to="/track" replace />} />
          <Route path="/track" element={<Track />} />
          <Route path="/discover" element={<Discover />} />
          <Route path="/trading" element={<Trading />} />
          <Route path="/wiki" element={<Wiki />} />
          <Route path="/kanban" element={<Kanban />} />
          <Route path="*" element={<Navigate to="/track" replace />} />
        </Routes>
      </Layout>
    </PasswordGate>
  )
}

export default App
