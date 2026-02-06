import { ReactNode } from 'react'
import { Link, useLocation } from 'react-router-dom'
import {
  LayoutDashboard,
  TrendingUp,
  Globe,
  AlertTriangle,
  ArrowRightLeft,
  RefreshCw,
  Shield,
  BookOpen,
  SlidersHorizontal,
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

const navItems = [
  { path: '/', label: 'Dashboard', icon: LayoutDashboard },
  { path: '/analysis', label: 'Analysis', icon: TrendingUp },
  { path: '/subnets', label: 'Subnets', icon: Globe },
  { path: '/strategy', label: 'Strategy', icon: Shield },
  { path: '/alerts', label: 'Alerts', icon: AlertTriangle },
  { path: '/recommendations', label: 'Rebalance', icon: ArrowRightLeft },
  { path: '/settings', label: 'Settings', icon: SlidersHorizontal },
  { path: '/examples', label: 'Examples', icon: BookOpen },
]

export default function Layout({ children }: LayoutProps) {
  const location = useLocation()
  const queryClient = useQueryClient()

  const { data: health } = useQuery<HealthResponse>({
    queryKey: ['health'],
    queryFn: api.getHealth,
    refetchInterval: 30000,
  })

  const { data: overview } = useQuery<PortfolioOverview>({
    queryKey: ['portfolio-overview'],
    queryFn: api.getPortfolioOverview,
    refetchInterval: 30000,
  })

  const refreshMutation = useMutation({
    mutationFn: api.triggerRefresh,
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

  return (
    <div className="min-h-screen flex flex-col">
      {/* Top Navigation Bar */}
      <header className="bg-[#16181d] border-b border-[#2a2f38] px-6 py-0 flex items-center h-14 flex-shrink-0">
        {/* Left: Logo + TAO Price */}
        <div className="flex items-center gap-4">
          <Link to="/" className="flex items-center gap-2">
            <h1 className="text-2xl font-bold text-[#2a3ded] font-display">TAO Treasury</h1>
          </Link>

          {taoPrice != null && (
            <div className="flex items-center gap-2 px-3 py-1 bg-[#0d0f12]/80 rounded-md">
              <span className="text-base tabular-nums text-white font-semibold">
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

        {/* Right: Navigation + Status + Refresh */}
        <div className="flex items-center gap-3 ml-auto">
          <nav className="flex items-center gap-1">
            {navItems.map((item) => {
              const isActive = item.path === '/'
                ? location.pathname === '/'
                : location.pathname.startsWith(item.path)
              const Icon = item.icon
              return (
                <Link
                  key={item.path}
                  to={item.path}
                  className={`flex items-center gap-1.5 px-3 py-1.5 text-sm rounded-lg transition-colors ${
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
          </nav>

          {/* Last Synced Status */}
          <div
            className={`flex items-center gap-1.5 px-3 py-1.5 rounded-lg ${
              health?.data_stale ? 'bg-yellow-900/30' : 'bg-[#1e2128]/50'
            }`}
            title={health?.last_sync ? `Last synced: ${new Date(health.last_sync).toLocaleString()}` : 'Never synced'}
          >
            <div className={`w-2 h-2 rounded-full ${
              health?.data_stale ? 'bg-yellow-400' :
              health?.status === 'healthy' ? 'bg-green-400' : 'bg-yellow-400'
            }`} />
            <span className={`text-sm ${health?.data_stale ? 'text-yellow-400' : 'text-[#9ca3af]'}`}>
              {formatRelativeTime(health?.last_sync ?? null)}
            </span>
          </div>

          {/* Sync Button */}
          <button
            onClick={() => refreshMutation.mutate()}
            disabled={refreshMutation.isPending}
            className="flex items-center gap-1.5 px-3 py-1.5 bg-[#1e2128] hover:bg-[#262b33] rounded-lg text-sm text-[#9ca3af] disabled:opacity-50 transition-colors"
            title="Sync data from TaoStats"
          >
            <RefreshCw className={`w-4 h-4 ${refreshMutation.isPending ? 'animate-spin' : ''}`} />
            {refreshMutation.isPending ? 'Syncing...' : 'Sync'}
          </button>
        </div>
      </header>

      {/* Main content — full width */}
      <main className="flex-1 overflow-auto">
        <div className="p-6">
          {children}
        </div>
      </main>
    </div>
  )
}
