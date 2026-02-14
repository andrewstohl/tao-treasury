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

export interface TradeProposal {
  id?: number
  proposal_id: string
  strategy_id: string
  action: 'buy' | 'sell' | 'rebalance' | string
  status: 'pending' | 'approved' | 'executed' | 'rejected' | string
  subnets_involved: number[] | null
  amounts: number[] | null
  total_amount_tao: number | null
  rationale: string | null
  proposed_at: string
  executed_at: string | null
  created_at: string
}

export interface WikiEntry {
  id?: number
  entry_id: string
  title: string
  category: 'strategy_research' | 'subnet_analysis' | 'market_regime' | string
  content: string
  tags: string[] | null
  author: string | null
  created_at: string
  updated_at: string
}

export interface SubnetProfile {
  id?: number
  netuid: number
  subnet_name: string | null
  description: string | null
  token_symbol: string | null
  market_cap: number | null
  price: number | null
  daily_return_pct: number | null
  volatility: number | null
  sharpe_ratio: number | null
  sn88_score: number | null
  fundamentals: any | null
  created_at: string
  updated_at: string
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

  // Trade Proposals
  getTradeProposals: async (status?: string) => {
    let query = supabase
      .from('trade_proposals')
      .select('*')
      .order('proposed_at', { ascending: false })
    
    if (status) query = query.eq('status', status)
    
    const { data, error } = await query
    if (error) throw error
    return data as TradeProposal[]
  },

  updateTradeProposalStatus: async (proposalId: string, status: string) => {
    const { data, error } = await supabase
      .from('trade_proposals')
      .update({ status, executed_at: status === 'executed' ? new Date().toISOString() : null })
      .eq('proposal_id', proposalId)
    if (error) throw error
    return data
  },

  // Wiki Entries
  getWikiEntries: async (category?: string) => {
    let query = supabase
      .from('wiki_entries')
      .select('*')
      .order('updated_at', { ascending: false })
    
    if (category) query = query.eq('category', category)
    
    const { data, error } = await query
    if (error) throw error
    return data as WikiEntry[]
  },

  searchWikiEntries: async (searchTerm: string) => {
    const { data, error } = await supabase
      .from('wiki_entries')
      .select('*')
      .or(`title.ilike.%${searchTerm}%,content.ilike.%${searchTerm}%`)
      .order('updated_at', { ascending: false })
    if (error) throw error
    return data as WikiEntry[]
  },

  // Subnet Profiles
  getSubnetProfiles: async () => {
    const { data, error } = await supabase
      .from('subnet_profiles')
      .select('*')
      .order('netuid', { ascending: true })
    if (error) throw error
    return data as SubnetProfile[]
  },

  getSubnetProfileByNetuid: async (netuid: number) => {
    const { data, error } = await supabase
      .from('subnet_profiles')
      .select('*')
      .eq('netuid', netuid)
      .single()
    if (error) throw error
    return data as SubnetProfile
  },
}
