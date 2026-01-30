export interface YieldSummary {
  portfolio_apy: string
  daily_yield_tao: string
  weekly_yield_tao: string
  monthly_yield_tao: string
}

export interface PnLSummary {
  total_unrealized_pnl_tao: string
  total_realized_pnl_tao: string
  total_cost_basis_tao: string
  unrealized_pnl_pct: string
}

export interface PositionSummary {
  netuid: number
  subnet_name: string
  tao_value_mid: string
  tao_value_exec_50pct: string
  tao_value_exec_100pct: string
  alpha_balance: string
  weight_pct: string
  entry_price_tao: string
  entry_date: string | null
  current_apy: string
  daily_yield_tao: string
  cost_basis_tao: string
  realized_pnl_tao: string
  unrealized_pnl_tao: string
  unrealized_pnl_pct: string
  exit_slippage_50pct: string
  exit_slippage_100pct: string
  health_status: 'green' | 'yellow' | 'red'
  health_reason: string | null
  validator_hotkey: string | null
  recommended_action: string | null
  action_reason: string | null
  flow_regime: string | null
  emission_share: string | null
}

export interface ActionItem {
  priority: 'high' | 'medium' | 'low'
  action_type: string
  title: string
  description: string
  subnet_id: number | null
  potential_gain_tao: string | null
}

export interface PortfolioHealth {
  status: 'green' | 'yellow' | 'red'
  score: number
  top_issue: string | null
  issues_count: number
}

export interface Portfolio {
  wallet_address: string
  nav_mid: string
  nav_exec_50pct: string
  nav_exec_100pct: string
  tao_price_usd: string
  nav_usd: string
  allocation: {
    root_tao: string
    root_pct: string
    dtao_tao: string
    dtao_pct: string
    unstaked_tao: string
    unstaked_pct: string
  }
  yield_summary: YieldSummary
  pnl_summary: PnLSummary
  executable_drawdown_pct: string
  drawdown_from_ath_pct: string
  nav_ath: string
  active_positions: number
  eligible_subnets: number
  overall_regime: string
  daily_turnover_pct: string
  weekly_turnover_pct: string
  as_of: string
}

export interface Dashboard {
  portfolio: Portfolio
  portfolio_health: PortfolioHealth
  top_positions: PositionSummary[]
  action_items: ActionItem[]
  alerts: {
    critical: number
    warning: number
    info: number
  }
  pending_recommendations: number
  urgent_recommendations: number
  last_sync: string | null
  data_stale: boolean
  generated_at: string
  market_pulse: MarketPulse | null
}

export interface Subnet {
  id: number
  netuid: number
  name: string
  description: string | null
  owner_address: string | null
  owner_take: string
  registered_at: string | null
  age_days: number
  emission_share: string
  total_stake_tao: string
  pool_tao_reserve: string
  pool_alpha_reserve: string
  alpha_price_tao: string
  rank: number | null
  market_cap_tao: string
  holder_count: number
  taoflow_1d: string
  taoflow_3d: string
  taoflow_7d: string
  taoflow_14d: string
  flow_regime: string
  flow_regime_since: string | null
  validator_apy: string
  is_eligible: boolean
  ineligibility_reasons: string | null
  category: string | null
  created_at: string
  updated_at: string
}

// Enriched subnet types (volatile pool data from TaoStats)
export interface SparklinePoint {
  timestamp: string
  price: number
}

export interface VolatilePoolData {
  price_change_1h: number | null
  price_change_24h: number | null
  price_change_7d: number | null
  price_change_30d: number | null
  high_24h: number | null
  low_24h: number | null
  market_cap_change_24h: number | null
  tao_volume_24h: number | null
  tao_buy_volume_24h: number | null
  tao_sell_volume_24h: number | null
  buys_24h: number | null
  sells_24h: number | null
  buyers_24h: number | null
  sellers_24h: number | null
  fear_greed_index: number | null
  fear_greed_sentiment: string | null
  sparkline_7d: SparklinePoint[] | null
  alpha_in_pool: number | null
  alpha_staked: number | null
  total_alpha: number | null
  root_prop: number | null
  startup_mode: boolean | null
}

export interface SubnetIdentity {
  tagline: string | null
  summary: string | null
  tags: string[] | null
  github_repo: string | null
  subnet_url: string | null
  logo_url: string | null
  discord: string | null
  twitter: string | null
  subnet_contact: string | null
}

export interface DevActivity {
  repo_url: string | null
  commits_1d: number | null
  commits_7d: number | null
  commits_30d: number | null
  prs_opened_7d: number | null
  prs_merged_7d: number | null
  issues_opened_30d: number | null
  issues_closed_30d: number | null
  reviews_30d: number | null
  unique_contributors_7d: number | null
  unique_contributors_30d: number | null
  last_event_at: string | null
  days_since_last_event: number | null
}

export interface EnrichedSubnet extends Subnet {
  volatile: VolatilePoolData | null
  identity: SubnetIdentity | null
  dev_activity: DevActivity | null
}

export interface EnrichedSubnetListResponse {
  subnets: EnrichedSubnet[]
  total: number
  eligible_count: number
  taostats_available: boolean
  cache_age_seconds: number | null
}

export interface MarketPulse {
  portfolio_24h_change_pct: string | null
  portfolio_7d_change_pct: string | null
  avg_sentiment_index: number | null
  avg_sentiment_label: string | null
  total_volume_24h_tao: string | null
  net_buy_pressure_pct: string | null
  top_mover_netuid: number | null
  top_mover_name: string | null
  top_mover_change_24h: string | null
  taostats_available: boolean
}

export interface Alert {
  id: number
  severity: 'critical' | 'warning' | 'info'
  category: string
  title: string
  message: string
  wallet_address: string | null
  netuid: number | null
  is_active: boolean
  is_acknowledged: boolean
  acknowledged_at: string | null
  created_at: string
}

export interface Recommendation {
  id: number
  wallet_address: string
  netuid: number
  subnet_name: string | null
  direction: 'buy' | 'sell'
  size_alpha: string
  size_tao: string
  size_pct_of_position: string
  estimated_slippage_pct: string
  estimated_slippage_tao: string
  total_estimated_cost_tao: string
  expected_nav_impact_tao: string
  trigger_type: string
  reason: string
  priority: number
  is_urgent: boolean
  tranche_number: number | null
  total_tranches: number | null
  status: string
  expires_at: string | null
  created_at: string
}

// Strategy types
export interface StrategyAnalysis {
  analyzed_at: string
  data_as_of: string | null
  portfolio_state: 'healthy' | 'caution' | 'risk_off' | 'emergency'
  state_reason: string
  regime_summary: Record<string, number>
  portfolio_regime: string
  total_subnets: number
  eligible_subnets: number
  ineligible_reasons: Record<string, number>
  positions_analyzed: number
  overweight_count: number
  underweight_count: number
  positions_to_exit: number
  concentration_ok: boolean
  category_caps_ok: boolean
  turnover_budget_remaining_pct: number
  pending_recommendations: number
  urgent_recommendations: number
  explanation: string
}

export interface ConstraintViolation {
  constraint: string
  severity: 'critical' | 'warning' | 'info'
  current: string
  limit: string
  utilization_pct: number
  explanation: string
  action_required: string
  netuid: number | null
  category: string | null
}

export interface ConstraintStatus {
  checked_at: string
  all_constraints_ok: boolean
  total_checked: number
  violation_count: number
  warning_count: number
  summary: string
  violations: ConstraintViolation[]
  warnings: ConstraintViolation[]
}

export interface EligibleSubnet {
  netuid: number
  name: string
  is_eligible: boolean
  reasons: string[]
  score: number | null
}

export interface PositionLimit {
  netuid: number
  subnet_name: string
  exitability_cap_tao: number
  concentration_cap_tao: number
  category_cap_tao: number
  max_position_tao: number
  binding_constraint: string
  current_position_tao: number
  available_headroom_tao: number
  explanation: string
}

export interface RebalanceResult {
  recommendation_count: number
  total_buys_tao: number
  total_sells_tao: number
  turnover_pct: number
  constrained_by_turnover: boolean
  summary: string
}
