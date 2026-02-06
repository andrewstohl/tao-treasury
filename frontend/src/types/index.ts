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

export interface ClosedPosition {
  netuid: number
  subnet_name: string
  total_staked_tao: string
  total_unstaked_tao: string
  realized_pnl_tao: string
  first_entry: string | null
  last_trade: string | null
}

export interface Dashboard {
  portfolio: Portfolio
  top_positions: PositionSummary[]
  closed_positions: ClosedPosition[]
  free_tao_balance: string
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
  fee_rate: string
  incentive_burn: string
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
  viability_score: string | null
  viability_tier: string | null
  viability_factors: string | null
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

// ---------------------------------------------------------------------------
// Phase 1 – Portfolio Overview (dual-currency, rolling returns, projections)
// ---------------------------------------------------------------------------

export interface DualCurrencyValue {
  tao: string
  usd: string
}

export interface RollingReturn {
  period: string // "1d" | "7d" | "30d" | "90d" | "inception"
  return_pct: string | null
  return_tao: string | null
  nav_start: string | null
  nav_end: string | null
  data_points: number
}

export interface TaoPriceContext {
  price_usd: string
  change_24h_pct: string | null
  change_7d_pct: string | null
}

export interface OverviewPnL {
  unrealized: DualCurrencyValue
  realized: DualCurrencyValue
  total: DualCurrencyValue
  cost_basis: DualCurrencyValue
  total_pnl_pct: string
}

export interface OverviewYield {
  daily: DualCurrencyValue
  weekly: DualCurrencyValue
  monthly: DualCurrencyValue
  annualized: DualCurrencyValue
  portfolio_apy: string
  cumulative_tao: string
  yield_1d_tao: string
  yield_7d_tao: string
  yield_30d_tao: string
  // Yield decomposition: total = unrealized (open) + realized (closed)
  total_yield: DualCurrencyValue
  unrealized_yield: DualCurrencyValue
  realized_yield: DualCurrencyValue
}

export interface CompoundingProjection {
  current_nav_tao: string
  current_apy: string
  projected_30d_tao: string
  projected_90d_tao: string
  projected_365d_tao: string
  compounded_30d_tao: string
  compounded_90d_tao: string
  compounded_365d_tao: string
  projected_nav_365d_tao: string
}

export interface ConversionExposure {
  // Cost basis (at stake time)
  usd_cost_basis: string
  tao_cost_basis: string
  // Current value
  current_usd_value: string
  current_tao_value: string
  // Total P&L
  total_pnl_usd: string
  total_pnl_pct: string
  // Decomposition
  alpha_tao_effect_usd: string  // P&L from α/τ movement
  tao_usd_effect: string        // P&L from τ/$ movement
  // Entry reference
  weighted_avg_entry_tao_price_usd: string
  // Data quality
  has_complete_usd_history: boolean
  positions_with_usd_data: number
  total_positions: number
}

export interface PortfolioOverview {
  nav_mid: DualCurrencyValue
  nav_exec: DualCurrencyValue
  tao_price: TaoPriceContext
  returns_mid: RollingReturn[]
  returns_exec: RollingReturn[]
  pnl: OverviewPnL
  yield_income: OverviewYield
  compounding: CompoundingProjection
  nav_ath_tao: string
  drawdown_from_ath_pct: string
  active_positions: number
  eligible_subnets: number
  overall_regime: string
  conversion_exposure: ConversionExposure
  as_of: string
}

// ---------------------------------------------------------------------------
// Phase 2 – Performance Attribution & Income Analysis
// ---------------------------------------------------------------------------

export interface WaterfallStep {
  label: string
  value_tao: string
  is_total: boolean
}

export interface PositionContribution {
  netuid: number
  subnet_name: string
  start_value_tao: string
  return_tao: string
  return_pct: string
  yield_tao: string
  price_effect_tao: string
  weight_pct: string
  contribution_pct: string
}

export interface IncomeStatement {
  yield_income_tao: string
  realized_gains_tao: string
  fees_tao: string
  net_income_tao: string
}

export interface Attribution {
  period_days: number
  start: string
  end: string
  nav_start_tao: string
  nav_end_tao: string
  total_return_tao: string
  total_return_pct: string
  yield_income_tao: string
  yield_income_pct: string
  price_effect_tao: string
  price_effect_pct: string
  fees_tao: string
  fees_pct: string
  net_flows_tao: string
  waterfall: WaterfallStep[]
  position_contributions: PositionContribution[]
  income_statement: IncomeStatement
}

// ---------------------------------------------------------------------------
// Phase 3 – TAO Price Sensitivity & Scenario Analysis
// ---------------------------------------------------------------------------

export interface SensitivityPoint {
  shock_pct: number
  tao_price_usd: string
  nav_tao: string
  nav_usd: string
  usd_change: string
  usd_change_pct: string
}

export interface StressScenario {
  id: string
  name: string
  description: string
  tao_price_change_pct: number
  alpha_impact_pct: number
  new_tao_price_usd: string
  nav_tao: string
  nav_usd: string
  tao_impact: string
  usd_impact: string
  usd_impact_pct: string
}

export interface AllocationExposure {
  root_tao: string
  root_pct: string
  dtao_tao: string
  dtao_pct: string
  unstaked_tao: string
}

export interface RiskExposure {
  tao_beta: string
  dtao_weight_pct: string
  root_weight_pct: string
  total_exit_slippage_pct: string
  total_exit_slippage_tao: string
  note: string
}

export interface ScenarioAnalysis {
  current_tao_price_usd: string
  nav_tao: string
  nav_usd: string
  allocation: AllocationExposure
  sensitivity: SensitivityPoint[]
  scenarios: StressScenario[]
  risk_exposure: RiskExposure
}

// ---------------------------------------------------------------------------
// Phase 4 – Risk-Adjusted Returns & Benchmarking
// ---------------------------------------------------------------------------

export interface DailyReturnPoint {
  date: string
  return_pct: string
  nav_tao: string
}

export interface BenchmarkComparison {
  id: string
  name: string
  description: string
  annualized_return_pct: string
  annualized_volatility_pct: string | null
  sharpe_ratio: string | null
  alpha_pct: string
}

export interface RiskMetrics {
  period_days: number
  start: string
  end: string
  annualized_return_pct: string
  annualized_volatility_pct: string
  downside_deviation_pct: string
  sharpe_ratio: string
  sortino_ratio: string
  calmar_ratio: string
  max_drawdown_pct: string
  max_drawdown_tao: string
  risk_free_rate_pct: string
  risk_free_source: string
  win_rate_pct: string
  best_day_pct: string
  worst_day_pct: string
  benchmarks: BenchmarkComparison[]
  daily_returns: DailyReturnPoint[]
}

// ==================== Settings ====================

export interface ViabilityConfig {
  id: number | null
  config_name: string
  is_active: boolean
  source: 'database' | 'defaults'

  // Hard failure thresholds
  min_tao_reserve: string
  min_emission_share: string
  min_age_days: number
  min_holders: number
  max_drawdown_30d: string
  max_negative_flow_ratio: string

  // Scored metric weights
  weight_tao_reserve: string
  weight_net_flow_7d: string
  weight_emission_share: string
  weight_price_trend_7d: string
  weight_subnet_age: string
  weight_max_drawdown_30d: string

  // Tier boundaries
  tier_1_min: number
  tier_2_min: number
  tier_3_min: number

  // Age cap
  age_cap_days: number

  // Feature flag
  enabled: boolean

  // Timestamps
  created_at: string | null
  updated_at: string | null
}

// ==================== Backtest ====================

export interface BacktestTierSummary {
  count: number
  avg_return_1d: number | null
  avg_return_3d: number | null
  avg_return_7d: number | null
  median_return_1d: number | null
  median_return_3d: number | null
  median_return_7d: number | null
  win_rate_1d: number | null
  win_rate_3d: number | null
  win_rate_7d: number | null
}

export interface BacktestDayResult {
  date: string
  tier_counts: Record<string, number>
  subnets: unknown[]
}

export interface BacktestResult {
  scoring_dates: string[]
  data_range: { start: string; end: string }
  summary: Record<string, BacktestTierSummary>
  tier_separation: Record<string, number | null>
  daily_results: BacktestDayResult[]
}

export interface PortfolioEquityPoint {
  date: string
  value: number
  return_pct: number
  in_root: boolean
  num_holdings: number
}

export interface PortfolioHolding {
  netuid: number
  name: string
  tier?: string
  score: number | null
  weight: number
  entry_price: number
  exit_price: number | null
  return_pct: number
}

export interface PortfolioPeriod {
  date: string
  holdings: PortfolioHolding[]
  period_return: number
  portfolio_value: number
  in_root: boolean
}

export interface PortfolioSimResult {
  start_date: string
  end_date: string
  initial_capital: number
  final_value: number
  total_return: number
  num_periods: number
  periods_in_root: number
  equity_curve: PortfolioEquityPoint[]
  periods: PortfolioPeriod[]
  summary: {
    total_return_pct: number
    avg_period_return_pct: number
    median_period_return_pct: number
    win_rate: number
    max_drawdown_pct: number
    best_period: number
    worst_period: number
    avg_holdings_per_period: number
    tier_weights?: Record<string, number>
  }
}

export interface BackfillStatus {
  running: boolean
  total_subnets: number
  completed_subnets: number
  total_records_created: number
  total_records_skipped: number
  errors: string[]
  started_at: string | null
  finished_at: string | null
  current_netuid: number | null
}

export interface HealthResponse {
  status: 'healthy' | 'degraded'
  timestamp: string
  version: string
  database: string
  redis: string
  taostats_api: string
  last_sync: string | null
  data_stale: boolean
}
