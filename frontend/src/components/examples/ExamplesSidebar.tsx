import { useState } from 'react'
import { Link, useLocation } from 'react-router-dom'
import { ChevronDown, ChevronRight, Wallet, Calculator, Globe } from 'lucide-react'

const categories = [
  {
    id: 'portfolio',
    label: 'Portfolio & Stake',
    icon: Wallet,
    items: [
      { path: 'alpha-growth', label: 'Alpha Growth Over Time' },
      { path: 'stake-distribution', label: 'Stake Distribution' },
      { path: 'stake-balance-history', label: 'Stake Balance History' },
      { path: 'alpha-heatmap', label: 'Alpha Heatmap' },
      { path: 'account-balance-history', label: 'Account Balance History' },
      { path: 'stake-earnings', label: 'Stake Earnings' },
    ],
  },
  {
    id: 'accounting',
    label: 'Accounting & P&L',
    icon: Calculator,
    items: [
      { path: 'tax-export', label: 'Tax Accounting Export' },
      { path: 'hotkey-profits', label: 'Hotkey Profits' },
      { path: 'parent-hotkey-returns', label: 'Parent Hotkey Returns' },
    ],
  },
  {
    id: 'subnet',
    label: 'Subnet Analytics',
    icon: Globe,
    items: [
      { path: 'subnet-market-cap', label: 'Subnet Market Cap' },
      { path: 'daily-alpha-burns', label: 'Daily Alpha Burns' },
      { path: 'subnet-emissions', label: 'Subnet Emissions' },
      { path: 'daily-recycle', label: 'Daily Recycle / Halvening' },
      { path: 'price-stake-ratio', label: 'Price:Stake Ratio' },
    ],
  },
]

export default function ExamplesSidebar() {
  const location = useLocation()
  const [expanded, setExpanded] = useState<Record<string, boolean>>({
    portfolio: true,
    accounting: true,
    subnet: true,
  })

  const toggleCategory = (id: string) => {
    setExpanded((prev) => ({ ...prev, [id]: !prev[id] }))
  }

  return (
    <aside className="w-56 min-w-56 bg-[#050d15]/50 border-r border-[#1e3a5f] overflow-y-auto">
      <div className="p-3 border-b border-[#1e3a5f]">
        <h3 className="text-sm font-semibold text-[#8faabe]">API Examples</h3>
      </div>
      <nav className="py-2">
        {categories.map((cat) => {
          const Icon = cat.icon
          const isExpanded = expanded[cat.id] ?? true
          return (
            <div key={cat.id}>
              <button
                onClick={() => toggleCategory(cat.id)}
                className="w-full flex items-center gap-2 px-3 py-2 text-xs font-semibold text-[#6f87a0] hover:text-[#a8c4d9] uppercase tracking-wider"
              >
                {isExpanded ? <ChevronDown size={12} /> : <ChevronRight size={12} />}
                <Icon size={12} />
                {cat.label}
              </button>
              {isExpanded && (
                <div className="pb-1">
                  {cat.items.map((item) => {
                    const fullPath = `/examples/${item.path}`
                    const isActive = location.pathname === fullPath
                    return (
                      <Link
                        key={item.path}
                        to={fullPath}
                        className={`block px-3 py-1.5 pl-8 text-xs transition-colors ${
                          isActive
                            ? 'bg-tao-600/20 text-tao-400 border-r-2 border-tao-400'
                            : 'text-[#5a7a94] hover:bg-[#1a2d42]/50 hover:text-[#8faabe]'
                        }`}
                      >
                        {item.label}
                      </Link>
                    )
                  })}
                </div>
              )}
            </div>
          )
        })}
      </nav>
    </aside>
  )
}
