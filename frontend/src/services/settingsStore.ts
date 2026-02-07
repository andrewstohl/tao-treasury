/**
 * Local storage persistence for rebalance configuration.
 * These settings control how the Rebalance Advisor computes target portfolios.
 */

export interface RebalanceConfig {
  // Schedule
  rebalanceIntervalDays: number  // 3, 7, or 14
  lastRebalanceDate: string | null  // ISO date string

  // Thresholds
  positionThresholdPct: number  // Don't trade if position delta < this %
  portfolioThresholdPct: number  // Don't rebalance if total drift < this %

  // Strategy
  strategy: 'equal_weight' | 'fai_weighted'
  topPercentile: number  // 30-70, select top N% by viability score
  maxPositionPct: number  // 10-25, max weight per position

  // Viability config
  useBackendViabilityConfig: boolean  // true = use Settings page values from backend
  // If false, use these overrides:
  minAgeDays: number
  minReserveTao: number
  maxOutflow7dPct: number
  maxDrawdownPct: number
  faiWeight: number
  reserveWeight: number
  emissionWeight: number
  stabilityWeight: number
}

const STORAGE_KEY = 'tao-treasury-rebalance-config'

export const DEFAULT_REBALANCE_CONFIG: RebalanceConfig = {
  // Schedule - 3 days as recommended by backtest
  rebalanceIntervalDays: 3,
  lastRebalanceDate: null,

  // Thresholds
  positionThresholdPct: 3,  // Don't adjust positions with < 3% delta
  portfolioThresholdPct: 5,  // Don't rebalance if total drift < 5%

  // Strategy
  strategy: 'equal_weight',
  topPercentile: 50,
  maxPositionPct: 12.5,

  // Viability - use backend config by default
  useBackendViabilityConfig: true,
  minAgeDays: 60,
  minReserveTao: 500,
  maxOutflow7dPct: 50,
  maxDrawdownPct: 50,
  faiWeight: 0.35,
  reserveWeight: 0.25,
  emissionWeight: 0.25,
  stabilityWeight: 0.15,
}

/**
 * Load rebalance config from localStorage, with defaults for missing fields.
 */
export function loadRebalanceConfig(): RebalanceConfig {
  try {
    const stored = localStorage.getItem(STORAGE_KEY)
    if (!stored) {
      return { ...DEFAULT_REBALANCE_CONFIG }
    }
    const parsed = JSON.parse(stored)
    // Merge with defaults to handle missing fields from older versions
    return { ...DEFAULT_REBALANCE_CONFIG, ...parsed }
  } catch {
    console.error('Failed to load rebalance config from localStorage')
    return { ...DEFAULT_REBALANCE_CONFIG }
  }
}

/**
 * Save rebalance config to localStorage.
 */
export function saveRebalanceConfig(config: RebalanceConfig): void {
  try {
    localStorage.setItem(STORAGE_KEY, JSON.stringify(config))
  } catch (e) {
    console.error('Failed to save rebalance config to localStorage', e)
  }
}

/**
 * Reset rebalance config to defaults.
 */
export function resetRebalanceConfig(): RebalanceConfig {
  const defaults = { ...DEFAULT_REBALANCE_CONFIG }
  saveRebalanceConfig(defaults)
  return defaults
}

/**
 * Update the last rebalance date to now.
 */
export function updateLastRebalanceDate(): void {
  const config = loadRebalanceConfig()
  config.lastRebalanceDate = new Date().toISOString().split('T')[0]
  saveRebalanceConfig(config)
}

/**
 * Calculate days until next rebalance.
 */
export function getDaysUntilRebalance(): number | null {
  const config = loadRebalanceConfig()
  if (!config.lastRebalanceDate) return 0  // Never rebalanced, due now

  const lastDate = new Date(config.lastRebalanceDate)
  const nextDate = new Date(lastDate)
  nextDate.setDate(nextDate.getDate() + config.rebalanceIntervalDays)

  const today = new Date()
  today.setHours(0, 0, 0, 0)
  nextDate.setHours(0, 0, 0, 0)

  const diffMs = nextDate.getTime() - today.getTime()
  const diffDays = Math.ceil(diffMs / (1000 * 60 * 60 * 24))

  return diffDays
}

/**
 * Check if rebalance is due (based on schedule).
 */
export function isRebalanceDue(): boolean {
  const days = getDaysUntilRebalance()
  return days !== null && days <= 0
}
