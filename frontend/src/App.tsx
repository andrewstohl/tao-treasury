import { Routes, Route } from 'react-router-dom'
import Layout from './components/common/Layout'
import Dashboard from './pages/Dashboard'
import Subnets from './pages/Subnets'
import Alerts from './pages/Alerts'
import Recommendations from './pages/Recommendations'
import Strategy from './pages/Strategy'

function App() {
  return (
    <Layout>
      <Routes>
        <Route path="/" element={<Dashboard />} />
        <Route path="/subnets" element={<Subnets />} />
        <Route path="/alerts" element={<Alerts />} />
        <Route path="/recommendations" element={<Recommendations />} />
        <Route path="/strategy" element={<Strategy />} />
      </Routes>
    </Layout>
  )
}

export default App
