import { Routes, Route } from 'react-router-dom'
import Layout from './components/common/Layout'
import Dashboard from './pages/Dashboard'
import Analysis from './pages/Analysis'
import Subnets from './pages/Subnets'
import Alerts from './pages/Alerts'
import Recommendations from './pages/Recommendations'
import Strategy from './pages/Strategy'
import Examples from './pages/Examples'

function App() {
  return (
    <Layout>
      <Routes>
        <Route path="/" element={<Dashboard />} />
        <Route path="/analysis" element={<Analysis />} />
        <Route path="/subnets" element={<Subnets />} />
        <Route path="/alerts" element={<Alerts />} />
        <Route path="/recommendations" element={<Recommendations />} />
        <Route path="/strategy" element={<Strategy />} />
        <Route path="/examples/*" element={<Examples />} />
      </Routes>
    </Layout>
  )
}

export default App
