import { ReactNode, useState, useRef, useEffect } from 'react'
import { Link, useLocation } from 'react-router-dom'
import {
  RefreshCw,
  ChevronDown,
  TrendingUp,
  Shield,
  AlertTriangle,
  ArrowRightLeft,
  BookOpen,
  FlaskConical,
} from 'lucide-react'
import { useQuery, useMutation, useQueryClient } from '@tanstack/react-query'
import { api } from '../../services/api'
import type { PortfolioOverview, HealthResponse } from '../../types'

function formatRelativeTime(dateString: string | null): string {
  if (!dateString) return 'Never'
  const date = new Date(dateString)
  const now = new Date()
  const diffMs = now.getTime() - date.getTime()
  const diffMins = Math.floor(diffMs / 60000)

  if (diffMins < 1) return 'Just now'
  if (diffMins === 1) return '1 min ago'
  if (diffMins < 60) return `${diffMins} min ago`

  const diffHours = Math.floor(diffMins / 60)
  if (diffHours === 1) return '1 hour ago'
  if (diffHours < 24) return `${diffHours} hours ago`

  return date.toLocaleDateString()
}

interface LayoutProps {
  children: ReactNode
}

// Analyze dropdown items
const analyzeItems = [
  { path: '/analysis', label: 'Analysis', icon: TrendingUp },
  { path: '/strategy', label: 'Strategy', icon: Shield },
  { path: '/backtest', label: 'Backtest', icon: FlaskConical },
  { path: '/alerts', label: 'Alerts', icon: AlertTriangle },
  { path: '/recommendations', label: 'Rebalance', icon: ArrowRightLeft },
  { path: '/examples', label: 'Examples', icon: BookOpen },
]

export default function Layout({ children }: LayoutProps) {
  const location = useLocation()
  const queryClient = useQueryClient()
  const [analyzeOpen, setAnalyzeOpen] = useState(false)
  const analyzeRef = useRef<HTMLDivElement>(null)

  // Close dropdown when clicking outside
  useEffect(() => {
    function handleClickOutside(e: MouseEvent) {
      if (analyzeRef.current && !analyzeRef.current.contains(e.target as Node)) {
        setAnalyzeOpen(false)
      }
    }
    if (analyzeOpen) {
      document.addEventListener('mousedown', handleClickOutside)
      return () => document.removeEventListener('mousedown', handleClickOutside)
    }
  }, [analyzeOpen])

  const { data: health } = useQuery<HealthResponse>({
    queryKey: ['health'],
    queryFn: api.getHealth,
    refetchInterval: 120000,  // 2 min - reduced to avoid rate limits
  })

  const { data: overview } = useQuery<PortfolioOverview>({
    queryKey: ['portfolio-overview'],
    queryFn: () => api.getPortfolioOverview(),
    refetchInterval: 120000,  // 2 min - reduced to avoid rate limits
  })

  const refreshMutation = useMutation({
    mutationFn: (mode: string) => api.triggerRefresh(mode),
    onSuccess: () => {
      queryClient.invalidateQueries()
    },
  })

  const taoPrice = overview?.tao_price?.price_usd
    ? parseFloat(overview.tao_price.price_usd)
    : null
  const taoChange = overview?.tao_price?.change_24h_pct
    ? parseFloat(overview.tao_price.change_24h_pct)
    : null

  // Check if any analyze path is active
  const isAnalyzeActive = analyzeItems.some(item =>
    item.path === '/examples'
      ? location.pathname.startsWith(item.path)
      : location.pathname === item.path
  )

  return (
    <div className="min-h-screen flex flex-col">
      {/* Top Navigation Bar - taller */}
      <header className="bg-[#16181d] border-b border-[#2a2f38] px-6 flex items-center h-16 flex-shrink-0 relative">
        {/* Left: Logo */}
        <Link to="/" className="flex items-center">
          <img
            src="/vora-logo.png"
            alt="VORA"
            className="h-8"
          />
        </Link>

        {/* Center: Navigation - absolutely centered */}
        <nav className="absolute left-1/2 -translate-x-1/2 flex items-center gap-1">
          {/* Track (Dashboard) */}
          <Link
            to="/"
            className={`flex items-center gap-1.5 px-4 py-2 text-sm font-medium rounded-lg transition-colors ${
              location.pathname === '/'
                ? 'bg-[#2a3ded] text-white'
                : 'text-[#9ca3af] hover:bg-[#2a3ded]/10 hover:text-[#2a3ded]'
            }`}
          >
            Track
          </Link>

          {/* Discover (Subnets) */}
          <Link
            to="/subnets"
            className={`flex items-center gap-1.5 px-4 py-2 text-sm font-medium rounded-lg transition-colors ${
              location.pathname === '/subnets' || location.pathname.startsWith('/subnets/')
                ? 'bg-[#2a3ded] text-white'
                : 'text-[#9ca3af] hover:bg-[#2a3ded]/10 hover:text-[#2a3ded]'
            }`}
          >
            Discover
          </Link>

          {/* Analyze (Dropdown) */}
          <div className="relative" ref={analyzeRef}>
            <button
              onClick={() => setAnalyzeOpen(!analyzeOpen)}
              className={`flex items-center gap-1.5 px-4 py-2 text-sm font-medium rounded-lg transition-colors ${
                isAnalyzeActive
                  ? 'bg-[#2a3ded] text-white'
                  : 'text-[#9ca3af] hover:bg-[#2a3ded]/10 hover:text-[#2a3ded]'
              }`}
            >
              Analyze
              <ChevronDown className={`w-4 h-4 transition-transform ${analyzeOpen ? 'rotate-180' : ''}`} />
            </button>

            {analyzeOpen && (
              <div className="absolute top-full left-0 mt-1 bg-[#1e2128] border border-[#2a2f38] rounded-lg shadow-xl z-50 py-1 min-w-[160px]">
                {analyzeItems.map((item) => {
                  const Icon = item.icon
                  const isActive = item.path === '/examples'
                    ? location.pathname.startsWith(item.path)
                    : location.pathname === item.path
                  return (
                    <Link
                      key={item.path}
                      to={item.path}
                      onClick={() => setAnalyzeOpen(false)}
                      className={`flex items-center gap-2 px-4 py-2 text-sm transition-colors ${
                        isActive
                          ? 'bg-[#2a3ded] text-white'
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
                ? 'bg-[#2a3ded] text-white'
                : 'text-[#9ca3af] hover:bg-[#2a3ded]/10 hover:text-[#2a3ded]'
            }`}
          >
            Settings
          </Link>
        </nav>

        {/* Right: TAO Price */}
        <div className="flex items-center gap-3 ml-auto">
          {taoPrice != null && (
            <div className="flex items-center gap-2">
              <span className="text-sm text-[#6b7280]">TAO</span>
              <span className="text-lg tabular-nums text-white font-semibold">
                ${taoPrice.toLocaleString(undefined, { minimumFractionDigits: 2, maximumFractionDigits: 2 })}
              </span>
              {taoChange != null && (
                <span className={`text-sm tabular-nums ${taoChange >= 0 ? 'text-green-400' : 'text-red-400'}`}>
                  {taoChange >= 0 ? '+' : ''}{taoChange.toFixed(1)}%
                </span>
              )}
            </div>
          )}
        </div>
      </header>

      {/* Sync Status Bar - below header, right aligned */}
      <div className="bg-[#0d0f12] border-b border-[#2a2f38] px-6 py-1 flex justify-end">
        <div className="flex items-center gap-2">
          {/* Last Synced Status */}
          <div
            className={`flex items-center gap-1.5 px-2 py-0.5 rounded ${
              health?.data_stale ? 'bg-yellow-900/30' : 'bg-[#1e2128]/50'
            }`}
            title={health?.last_sync ? `Last synced: ${new Date(health.last_sync).toLocaleString()}` : 'Never synced'}
          >
            <div className={`w-1.5 h-1.5 rounded-full ${
              health?.data_stale ? 'bg-yellow-400' :
              health?.status === 'healthy' ? 'bg-green-400' : 'bg-yellow-400'
            }`} />
            <span className={`text-xs ${health?.data_stale ? 'text-yellow-400' : 'text-[#6b7280]'}`}>
              {formatRelativeTime(health?.last_sync ?? null)}
            </span>
          </div>

          {/* Sync Button — click=refresh, shift+click=full */}
          <button
            onClick={(e) => refreshMutation.mutate(e.shiftKey ? 'full' : 'refresh')}
            disabled={refreshMutation.isPending}
            className="flex items-center gap-1 px-2 py-0.5 bg-[#1e2128] hover:bg-[#262b33] rounded text-xs text-[#6b7280] disabled:opacity-50 transition-colors"
            title="Sync data (Shift+click for full sync)"
          >
            <RefreshCw className={`w-3 h-3 ${refreshMutation.isPending ? 'animate-spin' : ''}`} />
            {refreshMutation.isPending ? 'Syncing...' : 'Sync'}
          </button>
        </div>
      </div>

      {/* Main content */}
      <main className="flex-1 overflow-auto">
        <div className="p-6">
          {children}
        </div>
      </main>
    </div>
  )
}
