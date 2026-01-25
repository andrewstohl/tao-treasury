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
}

export interface Position {
  id: number
  wallet_address: string
  netuid: number
  alpha_balance: string
  tao_value_mid: string
  tao_value_exec_50pct: string
  tao_value_exec_100pct: string
  weight_pct: string
  entry_price_tao: string
  entry_date: string | null
  cost_basis_tao: string
  realized_pnl_tao: string
  unrealized_pnl_tao: string
  unrealized_pnl_pct: string
  exit_slippage_50pct: string
  exit_slippage_100pct: string
  validator_hotkey: string | null
  recommended_action: string | null
  action_reason: string | null
  subnet_name: string | null
  flow_regime: string | null
  emission_share: string | null
  created_at: string
  updated_at: string
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
