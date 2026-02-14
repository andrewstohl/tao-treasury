import { createClient } from '@supabase/supabase-js'

const SUPABASE_URL = 'https://lmwoptvosjfiecygztqk.supabase.co'
const SUPABASE_KEY = 'sb_publishable_PlvrQ_TLGbxiSw4tt4LbPw_ASFAmTSd'

export const supabase = createClient(SUPABASE_URL, SUPABASE_KEY)

// Types matching actual Supabase table schemas
export interface StrategyLedger {
  id?: number
  strategy_id: string
  date: string
  nav: number
  daily_return_pct: number
  cumulative_return_pct: number
  max_drawdown_pct: number
  sn88_score: number | null
  sn88_mar: number | null
  sn88_lsr: number | null
  sn88_odds: number | null
  sn88_daily: number | null
  win_rate: number | null
  turnover: number | null
  notes: string | null
  created_at: string
}

export interface AgentHeartbeat {
  id?: number
  agent_id: string
  last_run: string
  status: string
  errors: any | null
  run_duration_ms: number | null
  notes: string | null
  created_at: string
}

export interface DataFreshness {
  id?: number
  source: string
  last_updated: string
  status: string
  record_count: number | null
  threshold_minutes: number | null
  notes: string | null
}

export interface Escalation {
  id?: number
  agent_id: string
  severity: string
  title: string
  details: string | null
  resolved: boolean
  created_at: string
}

export const supabaseQueries = {
  // Strategy Ledger
  getLatestStrategyLedger: async () => {
    const { data, error } = await supabase
      .from('strategy_ledger')
      .select('*')
      .order('date', { ascending: false })
    if (error) throw error
    return data as StrategyLedger[]
  },

  getStrategyLedgerByStrategy: async (strategyId: string) => {
    const { data, error } = await supabase
      .from('strategy_ledger')
      .select('*')
      .eq('strategy_id', strategyId)
      .order('date', { ascending: true })
    if (error) throw error
    return data as StrategyLedger[]
  },

  getLatestNAVByStrategy: async () => {
    const { data, error } = await supabase
      .from('strategy_ledger')
      .select('strategy_id, nav, date, sn88_score, daily_return_pct, max_drawdown_pct, cumulative_return_pct')
      .order('date', { ascending: false })
    if (error) throw error
    
    const latestByStrategy = new Map<string, StrategyLedger>()
    data?.forEach((row) => {
      if (!latestByStrategy.has(row.strategy_id)) {
        latestByStrategy.set(row.strategy_id, row as StrategyLedger)
      }
    })
    return Array.from(latestByStrategy.values())
  },

  // Agent Heartbeats
  getAgentHeartbeats: async () => {
    const { data, error } = await supabase
      .from('agent_heartbeats')
      .select('*')
      .order('last_run', { ascending: false })
    if (error) throw error
    return data as AgentHeartbeat[]
  },

  // Data Freshness
  getDataFreshness: async () => {
    const { data, error } = await supabase
      .from('data_freshness')
      .select('*')
      .order('source', { ascending: true })
    if (error) throw error
    return data as DataFreshness[]
  },

  // Escalations
  getRecentEscalations: async (limit: number = 10) => {
    const { data, error } = await supabase
      .from('escalations')
      .select('*')
      .order('created_at', { ascending: false })
      .limit(limit)
    if (error) throw error
    return data as Escalation[]
  },

  // Strategy comparison for tournament
  getStrategyComparison: async () => {
    const { data, error } = await supabase
      .from('strategy_ledger')
      .select('strategy_id, nav, daily_return_pct, max_drawdown_pct, cumulative_return_pct, sn88_score, sn88_mar, sn88_lsr, date')
      .order('date', { ascending: false })
    if (error) throw error
    
    const latestByStrategy = new Map<string, any>()
    data?.forEach((row) => {
      if (!latestByStrategy.has(row.strategy_id)) {
        latestByStrategy.set(row.strategy_id, row)
      }
    })
    return Array.from(latestByStrategy.values())
  },

  // Historical data for charts
  getStrategyHistory: async (strategyId?: string, startDate?: string, endDate?: string) => {
    let query = supabase
      .from('strategy_ledger')
      .select('*')
      .order('date', { ascending: true })
    
    if (strategyId) query = query.eq('strategy_id', strategyId)
    if (startDate) query = query.gte('date', startDate)
    if (endDate) query = query.lte('date', endDate)
    
    const { data, error } = await query
    if (error) throw error
    return data as StrategyLedger[]
  },

  // Get unique strategy IDs
  getStrategyIds: async () => {
    const { data, error } = await supabase
      .from('strategy_ledger')
      .select('strategy_id')
    if (error) throw error
    const uniqueIds = [...new Set(data?.map((d) => d.strategy_id))]
    return uniqueIds as string[]
  },
}
