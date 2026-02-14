import { ReactNode } from 'react'
import { Link, useLocation } from 'react-router-dom'
import { Command, Trophy, Table, ClipboardList, BookOpen } from 'lucide-react'
import { useQuery } from '@tanstack/react-query'
import { supabaseQueries } from '../../services/supabase'

interface LayoutProps {
  children: ReactNode
}

const navItems = [
  { path: '/command-center', label: 'Command Center', icon: Command },
  { path: '/tournament', label: 'Tournament', icon: Trophy },
  { path: '/ledger', label: 'Ledger', icon: Table },
  { path: '/proposals', label: 'Proposals', icon: ClipboardList },
  { path: '/wiki', label: 'Wiki', icon: BookOpen },
]

export default function Layout({ children }: LayoutProps) {
  const location = useLocation()

  const { data: latestNavData } = useQuery({
    queryKey: ['supabase-latest-nav-header'],
    queryFn: supabaseQueries.getLatestNAVByStrategy,
    refetchInterval: 120000,
  })

  const totalNav = latestNavData?.reduce((sum, item) => sum + (item.nav || 0), 0) || 0

  return (
    <div className="min-h-screen flex flex-col bg-[#0d1117]">
      <header className="bg-[#16181d] border-b border-[#2a2f38] px-6 flex items-center h-16 flex-shrink-0">
        <Link to="/command-center" className="flex items-center gap-2">
          <div className="w-8 h-8 rounded-lg bg-[#2a3ded] flex items-center justify-center">
            <span className="text-white font-bold text-sm">τ</span>
          </div>
          <span className="text-xl font-bold text-white">TAOFund</span>
        </Link>

        <nav className="flex items-center gap-1 ml-8">
          {navItems.map((item) => {
            const Icon = item.icon
            const isActive = location.pathname === item.path
            return (
              <Link
                key={item.path}
                to={item.path}
                className={`flex items-center gap-1.5 px-4 py-2 text-sm font-medium rounded-lg transition-colors ${
                  isActive
                    ? 'bg-[#2a3ded]/20 text-[#2a3ded]'
                    : 'text-[#9ca3af] hover:bg-[#2a3ded]/10 hover:text-white'
                }`}
              >
                <Icon className="w-4 h-4" />
                {item.label}
              </Link>
            )
          })}
        </nav>

        <div className="flex items-center gap-3 ml-auto">
          <span className="text-sm text-[#6b7280]">Total NAV</span>
          <span className="text-lg tabular-nums text-white font-semibold">
            {totalNav.toFixed(4)} τ
          </span>
        </div>
      </header>

      <main className="flex-1 overflow-auto">
        <div className="p-6">
          {children}
        </div>
      </main>
    </div>
  )
}
