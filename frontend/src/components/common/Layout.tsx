import { ReactNode, useState, useRef, useEffect } from 'react'
import { Link, useLocation } from 'react-router-dom'
import {
  ChevronDown,
  Command,
  Trophy,
  Table,
  TrendingUp,
  Shield,
  AlertTriangle,
  ArrowRightLeft,
  BookOpen,
  FlaskConical,
  Settings,
} from 'lucide-react'
import { useQuery } from '@tanstack/react-query'
import { supabaseQueries } from '../../services/supabase'

interface LayoutProps {
  children: ReactNode
}

// Primary Operations nav items
const operationsItems = [
  { path: '/command-center', label: 'Command Center', icon: Command },
  { path: '/tournament', label: 'Tournament', icon: Trophy },
  { path: '/ledger', label: 'Ledger', icon: Table },
]

// Legacy dropdown items (hidden pages that need Python backend)
const legacyItems = [
  { path: '/analysis', label: 'Analysis', icon: TrendingUp },
  { path: '/subnets', label: 'Discover', icon: Shield },
  { path: '/strategy', label: 'Strategy', icon: Shield },
  { path: '/backtest', label: 'Backtest', icon: FlaskConical },
  { path: '/alerts', label: 'Alerts', icon: AlertTriangle },
  { path: '/recommendations', label: 'Rebalance', icon: ArrowRightLeft },
  { path: '/examples', label: 'Examples', icon: BookOpen },
]

export default function Layout({ children }: LayoutProps) {
  const location = useLocation()
  const [legacyOpen, setLegacyOpen] = useState(false)
  const legacyRef = useRef<HTMLDivElement>(null)

  // Close dropdown when clicking outside
  useEffect(() => {
    function handleClickOutside(e: MouseEvent) {
      if (legacyRef.current && !legacyRef.current.contains(e.target as Node)) {
        setLegacyOpen(false)
      }
    }
    if (legacyOpen) {
      document.addEventListener('mousedown', handleClickOutside)
      return () => document.removeEventListener('mousedown', handleClickOutside)
    }
  }, [legacyOpen])

  // Get latest NAV data for TAO price from Supabase
  const { data: latestNavData } = useQuery({
    queryKey: ['supabase-latest-nav-header'],
    queryFn: supabaseQueries.getLatestNAVByStrategy,
    refetchInterval: 120000,
  })

  // Calculate total NAV
  const totalNav = latestNavData?.reduce((sum, item) => sum + (item.nav || 0), 0) || 0

  // Check if any operations path is active
  const isOperationsActive = operationsItems.some(item =>
    location.pathname === item.path
  )

  // Check if any legacy path is active
  const isLegacyActive = legacyItems.some(item =>
    item.path === '/examples'
      ? location.pathname.startsWith(item.path)
      : location.pathname === item.path
  )

  return (
    <div className="min-h-screen flex flex-col">
      {/* Top Navigation Bar */}
      <header className="bg-[#16181d] border-b border-[#2a2f38] px-6 flex items-center h-16 flex-shrink-0 relative">
        {/* Left: Logo */}
        <Link to="/command-center" className="flex items-center gap-2">
          <div className="w-8 h-8 rounded-lg bg-[#2a3ded] flex items-center justify-center">
            <span className="text-white font-bold text-sm">TAO</span>
          </div>
          <span className="text-xl font-bold text-white">TAOFund</span>
        </Link>

        {/* Center: Navigation - absolutely centered */}
        <nav className="absolute left-1/2 -translate-x-1/2 flex items-center gap-1">
          {/* Operations dropdown */}
          <div className="relative" ref={legacyRef}>
            <button
              onClick={() => setLegacyOpen(!legacyOpen)}
              className={`flex items-center gap-1.5 px-4 py-2 text-sm font-medium rounded-lg transition-colors ${
                isOperationsActive
                  ? 'bg-[#2a3ded]/20 text-[#2a3ded]'
                  : 'text-[#9ca3af] hover:bg-[#2a3ded]/10 hover:text-[#2a3ded]'
              }`}
            >
              Operations
              <ChevronDown className={`w-4 h-4 transition-transform ${legacyOpen ? 'rotate-180' : ''}`} />
            </button>

            {legacyOpen && (
              <div className="absolute top-full left-0 mt-1 bg-[#1e2128] border border-[#2a2f38] rounded-lg shadow-xl z-50 py-1 min-w-[180px]">
                {operationsItems.map((item) => {
                  const Icon = item.icon
                  const isActive = location.pathname === item.path
                  return (
                    <Link
                      key={item.path}
                      to={item.path}
                      onClick={() => setLegacyOpen(false)}
                      className={`flex items-center gap-2 px-4 py-2 text-sm transition-colors ${
                        isActive
                          ? 'bg-[#2a3ded]/20 text-[#2a3ded]'
                          : 'text-[#9ca3af] hover:bg-[#2a3ded]/10 hover:text-[#2a3ded]'
                      }`}
                    >
                      <Icon className="w-4 h-4" />
                      {item.label}
                    </Link>
                  )
                })}
              </div>
            )}
          </div>

          {/* Legacy dropdown */}
          <div className="relative" ref={legacyRef}>
            <button
              onClick={() => setLegacyOpen(!legacyOpen)}
              className={`flex items-center gap-1.5 px-4 py-2 text-sm font-medium rounded-lg transition-colors ${
                isLegacyActive
                  ? 'bg-[#2a3ded]/20 text-[#2a3ded]'
                  : 'text-[#9ca3af] hover:bg-[#2a3ded]/10 hover:text-[#2a3ded]'
              }`}
            >
              Legacy
              <ChevronDown className={`w-4 h-4 transition-transform ${legacyOpen ? 'rotate-180' : ''}`} />
            </button>

            {legacyOpen && (
              <div className="absolute top-full left-0 mt-1 bg-[#1e2128] border border-[#2a2f38] rounded-lg shadow-xl z-50 py-1 min-w-[180px]">
                {legacyItems.map((item) => {
                  const Icon = item.icon
                  const isActive = item.path === '/examples'
                    ? location.pathname.startsWith(item.path)
                    : location.pathname === item.path
                  return (
                    <Link
                      key={item.path}
                      to={item.path}
                      onClick={() => setLegacyOpen(false)}
                      className={`flex items-center gap-2 px-4 py-2 text-sm transition-colors ${
                        isActive
                          ? 'bg-[#2a3ded]/20 text-[#2a3ded]'
                          : 'text-[#9ca3af] hover:bg-[#2a3ded]/10 hover:text-[#2a3ded]'
                      }`}
                    >
                      <Icon className="w-4 h-4" />
                      {item.label}
                    </Link>
                  )
                })}
              </div>
            )}
          </div>

          {/* Settings */}
          <Link
            to="/settings"
            className={`flex items-center gap-1.5 px-4 py-2 text-sm font-medium rounded-lg transition-colors ${
              location.pathname === '/settings'
                ? 'bg-[#2a3ded]/20 text-[#2a3ded]'
                : 'text-[#9ca3af] hover:bg-[#2a3ded]/10 hover:text-[#2a3ded]'
            }`}
          >
            <Settings className="w-4 h-4" />
            Settings
          </Link>
        </nav>

        {/* Right: Total NAV */}
        <div className="flex items-center gap-3 ml-auto">
          <div className="flex items-center gap-2">
            <span className="text-sm text-[#6b7280]">Total NAV</span>
            <span className="text-lg tabular-nums text-white font-semibold">
              {totalNav.toLocaleString(undefined, { minimumFractionDigits: 2, maximumFractionDigits: 2 })} τ
            </span>
          </div>
        </div>
      </header>

      {/* Main content */}
      <main className="flex-1 overflow-auto">
        <div className="p-6">
          {children}
        </div>
      </main>
    </div>
  )
}
