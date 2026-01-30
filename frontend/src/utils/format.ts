/**
 * Shared formatting utilities used across Dashboard, Positions, and Subnets tabs.
 */

export function formatTao(value: string | number): string {
  const num = typeof value === 'string' ? parseFloat(value) : value
  if (isNaN(num)) return '--'
  return num.toLocaleString(undefined, { minimumFractionDigits: 2, maximumFractionDigits: 4 })
}

export function formatTaoShort(value: string | number): string {
  const num = typeof value === 'string' ? parseFloat(value) : value
  if (isNaN(num)) return '--'
  return num.toLocaleString(undefined, { minimumFractionDigits: 2, maximumFractionDigits: 2 })
}

export function formatPercent(value: string | number): string {
  const num = typeof value === 'string' ? parseFloat(value) : value
  if (isNaN(num)) return '--'
  return `${num >= 0 ? '+' : ''}${num.toFixed(2)}%`
}

export function formatApy(value: string | number): string {
  const num = typeof value === 'string' ? parseFloat(value) : value
  if (isNaN(num)) return '--'
  return `${num.toFixed(1)}%`
}

export function formatUsd(value: string | number): string {
  const num = typeof value === 'string' ? parseFloat(value) : value
  if (isNaN(num)) return '--'
  return `$${num.toLocaleString(undefined, { minimumFractionDigits: 2, maximumFractionDigits: 2 })}`
}

export function formatCompact(value: number): string {
  if (isNaN(value)) return '--'
  if (value >= 1_000_000) return `${(value / 1_000_000).toFixed(1)}M`
  if (value >= 1_000) return `${(value / 1_000).toFixed(1)}K`
  return value.toFixed(1)
}

export function getRegimeColor(regime: string | null): string {
  switch (regime) {
    case 'risk_on': return 'text-green-400'
    case 'risk_off': return 'text-red-400'
    case 'quarantine': return 'text-orange-400'
    case 'dead': return 'text-red-600'
    default: return 'text-yellow-400'
  }
}

export function getRegimeBgColor(regime: string | null): string {
  switch (regime) {
    case 'risk_on': return 'bg-green-600/20 text-green-400'
    case 'risk_off': return 'bg-red-600/20 text-red-400'
    case 'quarantine': return 'bg-orange-600/20 text-orange-400'
    case 'dead': return 'bg-red-800/20 text-red-600'
    default: return 'bg-yellow-600/20 text-yellow-400'
  }
}

export function getHealthColor(status: string): string {
  switch (status) {
    case 'green': return 'bg-green-500'
    case 'yellow': return 'bg-yellow-500'
    case 'red': return 'bg-red-500'
    default: return 'bg-gray-500'
  }
}

export function getHealthBgColor(status: string): string {
  switch (status) {
    case 'green': return 'bg-green-600/10 border-green-600/30'
    case 'yellow': return 'bg-yellow-600/10 border-yellow-600/30'
    case 'red': return 'bg-red-600/10 border-red-600/30'
    default: return ''
  }
}

export function formatRegimeLabel(regime: string): string {
  return regime.replace(/_/g, ' ')
}
