/**
 * Shared formatting utilities used across Dashboard, Positions, and Subnets tabs.
 */

/** Safe parseFloat that returns `fallback` for null, undefined, empty string, or NaN. */
export function safeFloat(value: string | number | null | undefined, fallback: number = 0): number {
  if (value == null || value === '') return fallback
  const num = typeof value === 'string' ? parseFloat(value) : value
  return isNaN(num) ? fallback : num
}

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

export function formatRegimeLabel(regime: string): string {
  return regime.replace(/_/g, ' ')
}
