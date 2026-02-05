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
  DollarSign,
  BookOpen,
  SlidersHorizontal,
} from 'lucide-react'
import { useQuery, useMutation, useQueryClient } from '@tanstack/react-query'
import { api } from '../../services/api'
import type { PortfolioOverview } from '../../types'

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

  const { data: health } = useQuery({
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
    <div className="min-h-screen flex">
      {/* Sidebar */}
      <aside className="w-64 bg-gray-800 border-r border-gray-700">
        <div className="p-4">
          <h1 className="text-xl font-bold text-tao-400">TAO Treasury</h1>
          <p className="text-xs text-gray-500 mt-1">Management Console</p>
        </div>

        {/* TAO Price */}
        {taoPrice != null && (
          <div className="mx-4 mb-2 px-3 py-2 bg-gray-900/60 rounded-lg flex items-center justify-between">
            <div className="flex items-center gap-1.5 text-xs text-gray-400">
              <DollarSign className="w-3.5 h-3.5" />
              <span>TAO</span>
            </div>
            <div className="text-right">
              <span className="text-sm font-mono text-white font-semibold">
                ${taoPrice.toLocaleString(undefined, { minimumFractionDigits: 2, maximumFractionDigits: 2 })}
              </span>
              {taoChange != null && (
                <span className={`ml-1.5 text-xs font-mono ${taoChange >= 0 ? 'text-green-400' : 'text-red-400'}`}>
                  {taoChange >= 0 ? '+' : ''}{taoChange.toFixed(1)}%
                </span>
              )}
            </div>
          </div>
        )}

        <nav className="mt-2">
          {navItems.map((item) => {
            const isActive = item.path === '/'
              ? location.pathname === '/'
              : location.pathname.startsWith(item.path)
            const Icon = item.icon
            return (
              <Link
                key={item.path}
                to={item.path}
                className={`flex items-center gap-3 px-4 py-3 text-sm transition-colors ${
                  isActive
                    ? 'bg-tao-600/20 text-tao-400 border-r-2 border-tao-400'
                    : 'text-gray-400 hover:bg-gray-700/50 hover:text-gray-200'
                }`}
              >
                <Icon size={18} />
                {item.label}
              </Link>
            )
          })}
        </nav>

        {/* Status */}
        <div className="absolute bottom-0 left-0 w-64 p-4 border-t border-gray-700">
          <div className="flex items-center justify-between text-xs">
            <span className="text-gray-500">Status</span>
            <span className={`${health?.status === 'healthy' ? 'text-green-400' : 'text-yellow-400'}`}>
              {health?.status || 'checking...'}
            </span>
          </div>
          {health?.data_stale && (
            <p className="text-xs text-yellow-500 mt-1">Data may be stale</p>
          )}
          <button
            onClick={() => refreshMutation.mutate()}
            disabled={refreshMutation.isPending}
            className="mt-2 w-full flex items-center justify-center gap-2 px-3 py-2 bg-gray-700 hover:bg-gray-600 rounded text-xs text-gray-300 disabled:opacity-50"
          >
            <RefreshCw size={14} className={refreshMutation.isPending ? 'animate-spin' : ''} />
            {refreshMutation.isPending ? 'Syncing...' : 'Refresh Data'}
          </button>
        </div>
      </aside>

      {/* Main content */}
      <main className="flex-1 overflow-auto">
        <div className="p-6">
          {children}
        </div>
      </main>
    </div>
  )
}
