import axios from 'axios'

const API_URL = import.meta.env.VITE_API_URL || 'http://localhost:8050'

const client = axios.create({
  baseURL: API_URL,
  headers: {
    'Content-Type': 'application/json',
  },
})

export const api = {
  // Health
  getHealth: async () => {
    const { data } = await client.get('/api/v1/health')
    return data
  },

  // Wallets
  getWallets: async () => {
    const { data } = await client.get('/api/v1/wallets')
    return data
  },

  addWallet: async (address: string, label?: string) => {
    const { data } = await client.post('/api/v1/wallets', { address, label })
    return data
  },

  updateWallet: async (address: string, updates: { label?: string; is_active?: boolean }) => {
    const { data } = await client.patch(`/api/v1/wallets/${encodeURIComponent(address)}`, updates)
    return data
  },

  deleteWallet: async (address: string) => {
    await client.delete(`/api/v1/wallets/${encodeURIComponent(address)}`)
  },

  // Portfolio
  getPortfolio: async () => {
    const { data } = await client.get('/api/v1/portfolio')
    return data
  },

  getDashboard: async () => {
    const { data } = await client.get('/api/v1/portfolio/dashboard')
    return data
  },

  getPortfolioOverview: async () => {
    const { data } = await client.get('/api/v1/portfolio/overview')
    return data
  },

  getAttribution: async (days: number = 7) => {
    const { data } = await client.get(`/api/v1/portfolio/attribution?days=${days}`)
    return data
  },

  getScenarios: async () => {
    const { data } = await client.get('/api/v1/portfolio/scenarios')
    return data
  },

  getRiskMetrics: async (days: number = 90) => {
    const { data } = await client.get(`/api/v1/portfolio/risk-metrics?days=${days}`)
    return data
  },

  getPortfolioHistory: async (days: number = 30) => {
    const { data } = await client.get(`/api/v1/portfolio/history?days=${days}`)
    return data
  },

  // Subnets
  getSubnets: async (eligibleOnly: boolean = false) => {
    const { data } = await client.get(`/api/v1/subnets?eligible_only=${eligibleOnly}`)
    return data
  },

  getSubnet: async (netuid: number) => {
    const { data } = await client.get(`/api/v1/subnets/${netuid}`)
    return data
  },

  getEnrichedSubnets: async (eligibleOnly: boolean = false) => {
    const { data } = await client.get(`/api/v1/subnets/enriched?eligible_only=${eligibleOnly}`)
    return data
  },

  getSubnetChart: async (netuid: number, resolution: string = '60', days: number = 30) => {
    const { data } = await client.get(`/api/v1/subnets/${netuid}/chart`, {
      params: { resolution, days }
    })
    return data
  },

  // Alerts
  getAlerts: async (activeOnly: boolean = true) => {
    const { data } = await client.get(`/api/v1/alerts?active_only=${activeOnly}`)
    return data
  },

  acknowledgeAlert: async (alertId: number, action: string = 'acknowledged', notes?: string) => {
    const { data } = await client.post(`/api/v1/alerts/${alertId}/ack`, {
      action,
      notes,
      acknowledged_by: 'user',
    })
    return data
  },

  // Recommendations
  getRecommendations: async (status: string = 'pending') => {
    const { data } = await client.get(`/api/v1/recommendations?status=${status}`)
    return data
  },

  markExecuted: async (recId: number, actualSlippage?: number, notes?: string) => {
    const { data } = await client.post(`/api/v1/recommendations/${recId}/mark_executed`, {
      actual_slippage_pct: actualSlippage,
      notes,
    })
    return data
  },

  // Tasks
  triggerRefresh: async () => {
    const { data } = await client.post('/api/v1/tasks/refresh')
    return data
  },

  // Strategy
  getStrategyAnalysis: async () => {
    const { data } = await client.get('/api/v1/strategy/analysis')
    return data
  },

  getConstraintStatus: async () => {
    const { data } = await client.get('/api/v1/strategy/constraints')
    return data
  },

  getEligibleUniverse: async () => {
    const { data } = await client.get('/api/v1/strategy/eligible')
    return data
  },

  getPositionLimits: async () => {
    const { data } = await client.get('/api/v1/strategy/position-limits')
    return data
  },

  triggerWeeklyRebalance: async () => {
    const { data } = await client.post('/api/v1/strategy/rebalance/weekly')
    return data
  },

  triggerEventRebalance: async (eventType: string, netuids?: number[]) => {
    const params = new URLSearchParams({ event_type: eventType })
    if (netuids && netuids.length > 0) {
      params.append('netuids', netuids.join(','))
    }
    const { data } = await client.post(`/api/v1/strategy/rebalance/event?${params}`)
    return data
  },

  checkTradeAllowed: async (netuid: number, direction: 'buy' | 'sell', sizeTao: number) => {
    const { data } = await client.get('/api/v1/strategy/check-trade', {
      params: { netuid, direction, size_tao: sizeTao }
    })
    return data
  },

  getRecommendationSummary: async () => {
    const { data } = await client.get('/api/v1/strategy/recommendation-summary')
    return data
  },

  // Settings
  getViabilityConfig: async () => {
    const { data } = await client.get('/api/v1/settings/viability')
    return data
  },

  updateViabilityConfig: async (config: Record<string, unknown>) => {
    const { data } = await client.put('/api/v1/settings/viability', config)
    return data
  },

  resetViabilityConfig: async () => {
    const { data } = await client.post('/api/v1/settings/viability/reset')
    return data
  },

  // Backtest
  runBacktest: async (intervalDays: number = 1) => {
    const { data } = await client.get(`/api/v1/backtest/run?interval_days=${intervalDays}`)
    return data
  },

  simulatePortfolio: async (intervalDays: number = 3, tier: string = 'tier_1', startDate?: string, initialCapital: number = 100, tierWeights?: Record<string, number>) => {
    const params = new URLSearchParams({
      interval_days: String(intervalDays),
      initial_capital: String(initialCapital),
      tier,
    })
    if (startDate) params.append('start_date', startDate)
    if (tierWeights) {
      const tw = Object.entries(tierWeights).map(([t, w]) => `${t}:${w}`).join(',')
      params.append('tier_weights', tw)
    }
    const { data } = await client.get(`/api/v1/backtest/simulate?${params}`)
    return data
  },

  // NEW: Viability-based simulation (v2)
  simulatePortfolioV2: async (config: {
    intervalDays?: number
    initialCapital?: number
    startDate?: string
    endDate?: string
    minAgeDays?: number
    minReserveTao?: number
    maxOutflow7dPct?: number
    maxDrawdownPct?: number
    faiWeight?: number
    reserveWeight?: number
    emissionWeight?: number
    stabilityWeight?: number
    strategy?: 'equal_weight' | 'fai_weighted'
    topPercentile?: number
    maxPositionPct?: number
  }) => {
    const params = new URLSearchParams()
    if (config.intervalDays !== undefined) params.append('interval_days', String(config.intervalDays))
    if (config.initialCapital !== undefined) params.append('initial_capital', String(config.initialCapital))
    if (config.startDate) params.append('start_date', config.startDate)
    if (config.endDate) params.append('end_date', config.endDate)
    if (config.minAgeDays !== undefined) params.append('min_age_days', String(config.minAgeDays))
    if (config.minReserveTao !== undefined) params.append('min_reserve_tao', String(config.minReserveTao))
    if (config.maxOutflow7dPct !== undefined) params.append('max_outflow_7d_pct', String(config.maxOutflow7dPct))
    if (config.maxDrawdownPct !== undefined) params.append('max_drawdown_pct', String(config.maxDrawdownPct))
    if (config.faiWeight !== undefined) params.append('fai_weight', String(config.faiWeight))
    if (config.reserveWeight !== undefined) params.append('reserve_weight', String(config.reserveWeight))
    if (config.emissionWeight !== undefined) params.append('emission_weight', String(config.emissionWeight))
    if (config.stabilityWeight !== undefined) params.append('stability_weight', String(config.stabilityWeight))
    if (config.strategy) params.append('strategy', config.strategy)
    if (config.topPercentile !== undefined) params.append('top_percentile', String(config.topPercentile))
    if (config.maxPositionPct !== undefined) params.append('max_position_pct', String(config.maxPositionPct))
    const { data } = await client.get(`/api/v1/backtest/simulate-v2?${params}`)
    return data
  },

  triggerBackfill: async (lookbackDays: number = 365) => {
    const { data } = await client.post(`/api/v1/backtest/backfill?lookback_days=${lookbackDays}`)
    return data
  },

  getBackfillStatus: async () => {
    const { data } = await client.get('/api/v1/backtest/backfill/status')
    return data
  },

  // Rebalance Advisor
  computeTargetPortfolio: async (config: {
    strategy: 'equal_weight' | 'fai_weighted'
    top_percentile: number
    max_position_pct: number
    position_threshold_pct: number
    portfolio_threshold_pct: number
    use_backend_viability_config: boolean
    viability_config?: {
      min_age_days: number
      min_reserve_tao: number
      max_outflow_7d_pct: number
      max_drawdown_pct: number
      fai_weight: number
      reserve_weight: number
      emission_weight: number
      stability_weight: number
    }
  }) => {
    const { data } = await client.post('/api/v1/rebalance/compute-target', config)
    return data
  },

  getViableSubnets: async (config?: {
    min_age_days?: number
    min_reserve_tao?: number
    max_outflow_7d_pct?: number
    max_drawdown_pct?: number
    fai_weight?: number
    reserve_weight?: number
    emission_weight?: number
    stability_weight?: number
  }) => {
    const params = new URLSearchParams()
    if (config?.min_age_days !== undefined) params.append('min_age_days', String(config.min_age_days))
    if (config?.min_reserve_tao !== undefined) params.append('min_reserve_tao', String(config.min_reserve_tao))
    if (config?.max_outflow_7d_pct !== undefined) params.append('max_outflow_7d_pct', String(config.max_outflow_7d_pct))
    if (config?.max_drawdown_pct !== undefined) params.append('max_drawdown_pct', String(config.max_drawdown_pct))
    if (config?.fai_weight !== undefined) params.append('fai_weight', String(config.fai_weight))
    if (config?.reserve_weight !== undefined) params.append('reserve_weight', String(config.reserve_weight))
    if (config?.emission_weight !== undefined) params.append('emission_weight', String(config.emission_weight))
    if (config?.stability_weight !== undefined) params.append('stability_weight', String(config.stability_weight))
    const { data } = await client.get(`/api/v1/rebalance/viable-subnets?${params}`)
    return data
  },
}
