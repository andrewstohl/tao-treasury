import { useState } from 'react'
import { useQuery, useMutation, useQueryClient } from '@tanstack/react-query'
import {
  ClipboardList,
  CheckCircle,
  XCircle,
  Clock,
  AlertCircle,
  ArrowRightLeft,
  TrendingUp,
  TrendingDown,
  Filter,
  Search,
  RefreshCw,
  ChevronRight,
  ChevronDown,
  ExternalLink,
} from 'lucide-react'
import { format, parseISO } from 'date-fns'
import { supabaseQueries, type TradeProposal } from '../services/supabase'

// Status badge styles
function getStatusStyles(status: string): { bg: string; text: string; border: string; icon: React.ReactNode } {
  switch (status.toLowerCase()) {
    case 'pending':
      return {
        bg: 'bg-yellow-500/10',
        text: 'text-yellow-400',
        border: 'border-yellow-500/30',
        icon: <Clock className="w-4 h-4" />,
      }
    case 'approved':
      return {
        bg: 'bg-blue-500/10',
        text: 'text-blue-400',
        border: 'border-blue-500/30',
        icon: <CheckCircle className="w-4 h-4" />,
      }
    case 'executed':
      return {
        bg: 'bg-green-500/10',
        text: 'text-green-400',
        border: 'border-green-500/30',
        icon: <CheckCircle className="w-4 h-4" />,
      }
    case 'rejected':
      return {
        bg: 'bg-red-500/10',
        text: 'text-red-400',
        border: 'border-red-500/30',
        icon: <XCircle className="w-4 h-4" />,
      }
    default:
      return {
        bg: 'bg-gray-500/10',
        text: 'text-gray-400',
        border: 'border-gray-500/30',
        icon: <AlertCircle className="w-4 h-4" />,
      }
  }
}

// Action badge styles
function getActionStyles(action: string): { bg: string; text: string; icon: React.ReactNode } {
  switch (action.toLowerCase()) {
    case 'buy':
      return {
        bg: 'bg-green-500/20',
        text: 'text-green-400',
        icon: <TrendingUp className="w-3 h-3" />,
      }
    case 'sell':
      return {
        bg: 'bg-red-500/20',
        text: 'text-red-400',
        icon: <TrendingDown className="w-3 h-3" />,
      }
    case 'rebalance':
      return {
        bg: 'bg-blue-500/20',
        text: 'text-blue-400',
        icon: <ArrowRightLeft className="w-3 h-3" />,
      }
    default:
      return {
        bg: 'bg-gray-500/20',
        text: 'text-gray-400',
        icon: <AlertCircle className="w-3 h-3" />,
      }
  }
}

// Strategy display names
const STRATEGY_DISPLAY_NAMES: Record<string, string> = {
  bedrock: 'Bedrock',
  yield_hunter: 'Sharpe Hunter',
  contrarian: 'Vol-Targeted',
}

export default function ProposalQueue() {
  const [statusFilter, setStatusFilter] = useState<string>('all')
  const [searchQuery, setSearchQuery] = useState('')
  const [expandedRows, setExpandedRows] = useState<Set<string>>(new Set())
  const queryClient = useQueryClient()

  // Fetch proposals
  const { data: proposals, isLoading } = useQuery({
    queryKey: ['supabase-trade-proposals', statusFilter],
    queryFn: () => supabaseQueries.getTradeProposals(statusFilter === 'all' ? undefined : statusFilter),
    refetchInterval: 30000,
  })

  // Update status mutation
  const updateStatusMutation = useMutation({
    mutationFn: ({ proposalId, status }: { proposalId: string; status: string }) =>
      supabaseQueries.updateTradeProposalStatus(proposalId, status),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ['supabase-trade-proposals'] })
    },
  })

  // Toggle row expansion
  const toggleRow = (proposalId: string) => {
    setExpandedRows((prev) => {
      const newSet = new Set(prev)
      if (newSet.has(proposalId)) {
        newSet.delete(proposalId)
      } else {
        newSet.add(proposalId)
      }
      return newSet
    })
  }

  // Filter proposals by search
  const filteredProposals = proposals?.filter((proposal) => {
    if (!searchQuery) return true
    const query = searchQuery.toLowerCase()
    return (
      proposal.proposal_id.toLowerCase().includes(query) ||
      proposal.strategy_id.toLowerCase().includes(query) ||
      proposal.action.toLowerCase().includes(query) ||
      (proposal.rationale || '').toLowerCase().includes(query)
    )
  })

  // Stats
  const stats = {
    total: proposals?.length || 0,
    pending: proposals?.filter((p) => p.status === 'pending').length || 0,
    approved: proposals?.filter((p) => p.status === 'approved').length || 0,
    executed: proposals?.filter((p) => p.status === 'executed').length || 0,
    rejected: proposals?.filter((p) => p.status === 'rejected').length || 0,
  }

  return (
    <div className="space-y-6">
      {/* Header */}
      <div className="flex items-center justify-between">
        <div>
          <h1 className="text-2xl font-bold text-[#2a3ded] flex items-center gap-2">
            <ClipboardList className="w-6 h-6" />
            Proposal Queue
          </h1>
          <p className="text-sm text-[#8a8f98] mt-1">
            Review and approve trade proposals from strategies
          </p>
        </div>

        <button
          onClick={() => queryClient.invalidateQueries({ queryKey: ['supabase-trade-proposals'] })}
          className="flex items-center gap-2 px-4 py-2 bg-[#2a3ded] hover:bg-[#3a4dff] rounded-lg text-sm font-medium text-white transition-colors"
        >
          <RefreshCw className="w-4 h-4" />
          Refresh
        </button>
      </div>

      {/* Stats Cards */}
      <div className="grid grid-cols-2 md:grid-cols-5 gap-4">
        <div className="bg-[#16181d] rounded-lg border border-[#2a2f38] p-4">
          <div className="text-xs text-[#6b7280] mb-1">Total</div>
          <div className="text-2xl font-bold text-white">{stats.total}</div>
        </div>
        <div className="bg-[#16181d] rounded-lg border border-[#2a2f38] p-4">
          <div className="text-xs text-[#6b7280] mb-1">Pending</div>
          <div className="text-2xl font-bold text-yellow-400">{stats.pending}</div>
        </div>
        <div className="bg-[#16181d] rounded-lg border border-[#2a2f38] p-4">
          <div className="text-xs text-[#6b7280] mb-1">Approved</div>
          <div className="text-2xl font-bold text-blue-400">{stats.approved}</div>
        </div>
        <div className="bg-[#16181d] rounded-lg border border-[#2a2f38] p-4">
          <div className="text-xs text-[#6b7280] mb-1">Executed</div>
          <div className="text-2xl font-bold text-green-400">{stats.executed}</div>
        </div>
        <div className="bg-[#16181d] rounded-lg border border-[#2a2f38] p-4">
          <div className="text-xs text-[#6b7280] mb-1">Rejected</div>
          <div className="text-2xl font-bold text-red-400">{stats.rejected}</div>
        </div>
      </div>

      {/* Filters */}
      <div className="bg-[#16181d] rounded-lg border border-[#2a2f38] p-4">
        <div className="flex flex-col md:flex-row gap-4">
          {/* Status Filter */}
          <div className="flex items-center gap-2">
            <Filter className="w-4 h-4 text-[#6b7280]" />
            <select
              value={statusFilter}
              onChange={(e) => setStatusFilter(e.target.value)}
              className="bg-[#0d0f12] border border-[#2a2f38] rounded-lg px-3 py-2 text-sm text-[#8faabe] focus:outline-none focus:border-[#2a3ded]"
            >
              <option value="all">All Status</option>
              <option value="pending">Pending</option>
              <option value="approved">Approved</option>
              <option value="executed">Executed</option>
              <option value="rejected">Rejected</option>
            </select>
          </div>

          {/* Search */}
          <div className="flex-1 relative">
            <Search className="absolute left-3 top-2.5 w-4 h-4 text-[#6b7280]" />
            <input
              type="text"
              placeholder="Search proposals..."
              value={searchQuery}
              onChange={(e) => setSearchQuery(e.target.value)}
              className="w-full bg-[#0d0f12] border border-[#2a2f38] rounded-lg pl-10 pr-3 py-2 text-sm text-[#8faabe] placeholder-gray-500 focus:outline-none focus:border-[#2a3ded]"
            />
          </div>
        </div>
      </div>

      {/* Proposals Table */}
      <div className="bg-[#16181d] rounded-lg border border-[#2a2f38] overflow-hidden">
        <div className="px-5 py-4 border-b border-[#2a2f38] flex items-center justify-between">
          <div className="flex items-center gap-2">
            <ClipboardList className="w-5 h-5 text-[#2a3ded]" />
            <h3 className="font-semibold text-white">Trade Proposals</h3>
          </div>
          <span className="text-xs text-[#6b7280]">
            {filteredProposals?.length || 0} proposals
          </span>
        </div>

        {isLoading ? (
          <div className="p-8">
            <div className="space-y-2">
              {[1, 2, 3, 4, 5].map((i) => (
                <div key={i} className="h-16 bg-[#1e2128] rounded animate-pulse" />
              ))}
            </div>
          </div>
        ) : (
          <div className="overflow-x-auto">
            <table className="w-full">
              <thead>
                <tr className="bg-[#0d0f12]">
                  <th className="px-4 py-3 text-left text-xs font-semibold text-[#6b7280] uppercase tracking-wider w-8" />
                  <th className="px-4 py-3 text-left text-xs font-semibold text-[#6b7280] uppercase tracking-wider">
                    Proposal ID
                  </th>
                  <th className="px-4 py-3 text-left text-xs font-semibold text-[#6b7280] uppercase tracking-wider">
                    Strategy
                  </th>
                  <th className="px-4 py-3 text-left text-xs font-semibold text-[#6b7280] uppercase tracking-wider">
                    Action
                  </th>
                  <th className="px-4 py-3 text-right text-xs font-semibold text-[#6b7280] uppercase tracking-wider">
                    Amount
                  </th>
                  <th className="px-4 py-3 text-center text-xs font-semibold text-[#6b7280] uppercase tracking-wider">
                    Subnets
                  </th>
                  <th className="px-4 py-3 text-left text-xs font-semibold text-[#6b7280] uppercase tracking-wider">
                    Status
                  </th>
                  <th className="px-4 py-3 text-left text-xs font-semibold text-[#6b7280] uppercase tracking-wider">
                    Proposed
                  </th>
                  <th className="px-4 py-3 text-right text-xs font-semibold text-[#6b7280] uppercase tracking-wider">
                    Actions
                  </th>
                </tr>
              </thead>
              <tbody className="divide-y divide-[#2a2f38]">
                {filteredProposals?.map((proposal) => {
                  const rowKey = proposal.proposal_id
                  const isExpanded = expandedRows.has(rowKey)
                  const statusStyles = getStatusStyles(proposal.status)
                  const actionStyles = getActionStyles(proposal.action)
                  const canApprove = proposal.status === 'pending'

                  return (
                    <>
                      <tr
                        key={rowKey}
                        className="hover:bg-[#1e2128]/50 cursor-pointer"
                        onClick={() => toggleRow(rowKey)}
                      >
                        <td className="px-4 py-4">
                          {proposal.subnets_involved && proposal.subnets_involved.length > 0 ? (
                            isExpanded ? (
                              <ChevronDown className="w-4 h-4 text-[#6b7280]" />
                            ) : (
                              <ChevronRight className="w-4 h-4 text-[#6b7280]" />
                            )
                          ) : (
                            <div className="w-4 h-4" />
                          )}
                        </td>
                        <td className="px-4 py-4">
                          <div className="flex items-center gap-2">
                            <span className="text-sm font-mono text-white">
                              {proposal.proposal_id.slice(0, 12)}...
                            </span>
                          </div>
                        </td>
                        <td className="px-4 py-4">
                          <span className="text-sm font-medium text-[#9ca3af]">
                            {STRATEGY_DISPLAY_NAMES[proposal.strategy_id] || proposal.strategy_id}
                          </span>
                        </td>
                        <td className="px-4 py-4">
                          <span
                            className={`inline-flex items-center gap-1.5 px-2.5 py-1 rounded-full text-xs font-medium ${actionStyles.bg} ${actionStyles.text}`}
                          >
                            {actionStyles.icon}
                            {proposal.action.charAt(0).toUpperCase() + proposal.action.slice(1)}
                          </span>
                        </td>
                        <td className="px-4 py-4 text-right">
                          <span className="text-sm text-white tabular-nums">
                            {proposal.total_amount_tao
                              ? `${proposal.total_amount_tao.toFixed(4)} τ`
                              : '—'}
                          </span>
                        </td>
                        <td className="px-4 py-4 text-center">
                          <span className="text-sm text-[#9ca3af]">
                            {proposal.subnets_involved?.length || 0}
                          </span>
                        </td>
                        <td className="px-4 py-4">
                          <span
                            className={`inline-flex items-center gap-1.5 px-2.5 py-1 rounded-full text-xs font-medium border ${statusStyles.bg} ${statusStyles.text} ${statusStyles.border}`}
                          >
                            {statusStyles.icon}
                            {proposal.status.charAt(0).toUpperCase() + proposal.status.slice(1)}
                          </span>
                        </td>
                        <td className="px-4 py-4">
                          <span className="text-sm text-[#6b7280]">
                            {format(parseISO(proposal.proposed_at), 'MMM d, HH:mm')}
                          </span>
                        </td>
                        <td className="px-4 py-4">
                          <div className="flex items-center justify-end gap-2">
                            {canApprove && (
                              <>
                                <button
                                  onClick={(e) => {
                                    e.stopPropagation()
                                    updateStatusMutation.mutate({
                                      proposalId: proposal.proposal_id,
                                      status: 'approved',
                                    })
                                  }}
                                  disabled={updateStatusMutation.isPending}
                                  className="px-3 py-1.5 bg-green-500/20 hover:bg-green-500/30 text-green-400 rounded text-xs font-medium transition-colors"
                                >
                                  Approve
                                </button>
                                <button
                                  onClick={(e) => {
                                    e.stopPropagation()
                                    updateStatusMutation.mutate({
                                      proposalId: proposal.proposal_id,
                                      status: 'rejected',
                                    })
                                  }}
                                  disabled={updateStatusMutation.isPending}
                                  className="px-3 py-1.5 bg-red-500/20 hover:bg-red-500/30 text-red-400 rounded text-xs font-medium transition-colors"
                                >
                                  Reject
                                </button>
                              </>
                            )}
                            {proposal.status === 'approved' && (
                              <button
                                onClick={(e) => {
                                  e.stopPropagation()
                                  updateStatusMutation.mutate({
                                    proposalId: proposal.proposal_id,
                                    status: 'executed',
                                  })
                                }}
                                disabled={updateStatusMutation.isPending}
                                className="px-3 py-1.5 bg-blue-500/20 hover:bg-blue-500/30 text-blue-400 rounded text-xs font-medium transition-colors"
                              >
                                Execute
                              </button>
                            )}
                            {proposal.status !== 'pending' && proposal.status !== 'approved' && (
                              <span className="text-xs text-[#6b7280]">—</span>
                            )}
                          </div>
                        </td>
                      </tr>

                      {/* Expanded Details */}
                      {isExpanded && (
                        <tr key={`${rowKey}-expanded`}>
                          <td colSpan={9} className="px-4 py-4 bg-[#0d0f12]">
                            <div className="pl-8 space-y-4">
                              {/* Rationale */}
                              {proposal.rationale && (
                                <div>
                                  <div className="text-xs text-[#6b7280] mb-1 uppercase tracking-wider">
                                    Rationale
                                  </div>
                                  <p className="text-sm text-[#9ca3af]">{proposal.rationale}</p>
                                </div>
                              )}

                              {/* Subnets and Amounts */}
                              {proposal.subnets_involved && proposal.subnets_involved.length > 0 && (
                                <div>
                                  <div className="text-xs text-[#6b7280] mb-2 uppercase tracking-wider">
                                    Target Subnets
                                  </div>
                                  <div className="grid grid-cols-2 md:grid-cols-4 lg:grid-cols-6 gap-2">
                                    {proposal.subnets_involved.map((netuid, idx) => (
                                      <div
                                        key={netuid}
                                        className="flex items-center justify-between p-2 bg-[#16181d] rounded border border-[#2a2f38]"
                                      >
                                        <span className="text-sm font-medium text-white">
                                          SN{netuid}
                                        </span>
                                        {proposal.amounts && proposal.amounts[idx] && (
                                          <span className="text-xs text-[#9ca3af] tabular-nums">
                                            {proposal.amounts[idx].toFixed(4)} τ
                                          </span>
                                        )}
                                      </div>
                                    ))}
                                  </div>
                                </div>
                              )}

                              {/* Metadata */}
                              <div className="flex items-center gap-6 text-xs text-[#6b7280]">
                                <span>ID: {proposal.proposal_id}</span>
                                {proposal.executed_at && (
                                  <span>
                                    Executed: {format(parseISO(proposal.executed_at), 'MMM d, yyyy HH:mm')}
                                  </span>
                                )}
                              </div>
                            </div>
                          </td>
                        </tr>
                      )}
                    </>
                  )
                })}
              </tbody>
            </table>

            {filteredProposals?.length === 0 && (
              <div className="text-center py-12 text-[#6b7280]">
                <ClipboardList className="w-8 h-8 mx-auto mb-3 opacity-50" />
                <p className="text-sm">No proposals found</p>
                <p className="text-xs mt-1">
                  {searchQuery
                    ? 'Try adjusting your search or filters'
                    : 'Proposals will appear when strategies submit them'}
                </p>
              </div>
            )}
          </div>
        )}
      </div>

      {/* Instructions */}
      <div className="bg-[#16181d] rounded-lg border border-[#2a2f38] p-4">
        <div className="flex items-start gap-3">
          <AlertCircle className="w-5 h-5 text-[#2a3ded] flex-shrink-0 mt-0.5" />
          <div>
            <h4 className="text-sm font-medium text-white mb-1">Workflow</h4>
            <p className="text-xs text-[#9ca3af]">
              Proposals flow through: <span className="text-yellow-400">Pending</span> →{' '}
              <span className="text-blue-400">Approved</span> →{' '}
              <span className="text-green-400">Executed</span>. Click any row to view details.
              Use Approve/Reject buttons for pending proposals. Once approved, use Execute to mark as completed.
            </p>
          </div>
        </div>
      </div>
    </div>
  )
}
