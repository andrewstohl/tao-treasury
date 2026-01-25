import { Routes, Route } from 'react-router-dom'
import Layout from './components/common/Layout'
import Dashboard from './pages/Dashboard'
import Positions from './pages/Positions'
import Subnets from './pages/Subnets'
import Alerts from './pages/Alerts'
import Recommendations from './pages/Recommendations'

function App() {
  return (
    <Layout>
      <Routes>
        <Route path="/" element={<Dashboard />} />
        <Route path="/positions" element={<Positions />} />
        <Route path="/subnets" element={<Subnets />} />
        <Route path="/alerts" element={<Alerts />} />
        <Route path="/recommendations" element={<Recommendations />} />
      </Routes>
    </Layout>
  )
}

export default App
