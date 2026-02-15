import { useState } from 'react'
import { useQuery, useMutation, useQueryClient } from '@tanstack/react-query'
import { Layout, Plus, GripVertical, Clock, User, AlertCircle, CheckCircle2, Circle, Pause, X } from 'lucide-react'
import { supabase } from '../services/supabase'

interface KanbanItem {
  source: string
  id: number
  title: string
  status: 'backlog' | 'in_progress' | 'review' | 'done' | 'blocked'
  owner: string
  priority: 'low' | 'medium' | 'high' | 'critical'
  created: string
  notes?: string
}

const COLUMNS = [
  { key: 'backlog', label: 'Backlog', icon: Circle, color: 'text-gray-400', bg: 'border-gray-600' },
  { key: 'in_progress', label: 'In Progress', icon: Clock, color: 'text-blue-400', bg: 'border-blue-500' },
  { key: 'review', label: 'Review', icon: AlertCircle, color: 'text-yellow-400', bg: 'border-yellow-500' },
  { key: 'done', label: 'Done', icon: CheckCircle2, color: 'text-green-400', bg: 'border-green-500' },
  { key: 'blocked', label: 'Blocked', icon: Pause, color: 'text-red-400', bg: 'border-red-500' },
]

const PRIORITY_COLORS: Record<string, string> = {
  critical: 'bg-red-500/20 text-red-400',
  high: 'bg-orange-500/20 text-orange-400',
  medium: 'bg-yellow-500/20 text-yellow-400',
  low: 'bg-gray-500/20 text-gray-400',
}

const OWNER_COLORS: Record<string, string> = {
  Doug: 'bg-green-500/20 text-green-400',
  Drew: 'bg-blue-500/20 text-blue-400',
  Kimi: 'bg-purple-500/20 text-purple-400',
}

export default function Kanban() {
  const queryClient = useQueryClient()
  const [showAdd, setShowAdd] = useState(false)
  const [newTitle, setNewTitle] = useState('')
  const [newOwner, setNewOwner] = useState('Doug')
  const [newPriority, setNewPriority] = useState('medium')
  const [newStatus, setNewStatus] = useState('backlog')

  const { data: items = [] } = useQuery({
    queryKey: ['kanban-items'],
    queryFn: async () => {
      const { data } = await supabase
        .from('raw_api_data')
        .select('*')
        .eq('endpoint', 'kanban')
        .order('fetched_at', { ascending: true })
      return (data || []).map(r => ({
        source: r.source,
        ...r.response
      })) as KanbanItem[]
    }
  })

  const updateStatus = useMutation({
    mutationFn: async ({ source, status }: { source: string; status: string }) => {
      const item = items.find(i => i.source === source)
      if (!item) return
      await supabase.from('raw_api_data').update({
        response: { ...item, status },
        fetched_at: new Date().toISOString()
      }).eq('source', source)
    },
    onSuccess: () => queryClient.invalidateQueries({ queryKey: ['kanban-items'] })
  })

  const addItem = useMutation({
    mutationFn: async () => {
      const id = Date.now()
      await supabase.from('raw_api_data').insert({
        source: `kanban_${id}`,
        endpoint: 'kanban',
        response: {
          id,
          title: newTitle,
          status: newStatus,
          owner: newOwner,
          priority: newPriority,
          created: new Date().toISOString()
        },
        fetched_at: new Date().toISOString(),
        api_status: 200
      })
    },
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ['kanban-items'] })
      setNewTitle('')
      setShowAdd(false)
    }
  })

  const deleteItem = useMutation({
    mutationFn: async (source: string) => {
      await supabase.from('raw_api_data').delete().eq('source', source)
    },
    onSuccess: () => queryClient.invalidateQueries({ queryKey: ['kanban-items'] })
  })

  return (
    <div className="p-6">
      <div className="flex items-center justify-between mb-6">
        <div>
          <h1 className="text-2xl font-bold text-white flex items-center gap-2">
            <Layout size={24} /> Mission Control
          </h1>
          <p className="text-gray-400 text-sm mt-1">{items.length} tasks · Doug + Drew workflow</p>
        </div>
        <button
          onClick={() => setShowAdd(!showAdd)}
          className="flex items-center gap-1.5 px-3 py-1.5 bg-blue-600 hover:bg-blue-500 rounded-lg text-sm text-white"
        >
          <Plus size={14} /> Add Task
        </button>
      </div>

      {/* Add Task Form */}
      {showAdd && (
        <div className="bg-gray-800 rounded-xl p-4 mb-6 border border-gray-700">
          <div className="grid grid-cols-1 md:grid-cols-4 gap-3">
            <input
              type="text"
              placeholder="Task title..."
              value={newTitle}
              onChange={(e) => setNewTitle(e.target.value)}
              className="md:col-span-2 bg-gray-900 border border-gray-700 rounded px-3 py-2 text-sm text-gray-200 focus:border-blue-500 focus:outline-none"
              onKeyDown={(e) => { if (e.key === 'Enter' && newTitle.trim()) addItem.mutate() }}
            />
            <select value={newOwner} onChange={(e) => setNewOwner(e.target.value)} className="bg-gray-900 border border-gray-700 rounded px-3 py-2 text-sm text-gray-200">
              <option value="Doug">Doug</option>
              <option value="Drew">Drew</option>
              <option value="Kimi">Kimi</option>
            </select>
            <select value={newPriority} onChange={(e) => setNewPriority(e.target.value)} className="bg-gray-900 border border-gray-700 rounded px-3 py-2 text-sm text-gray-200">
              <option value="critical">Critical</option>
              <option value="high">High</option>
              <option value="medium">Medium</option>
              <option value="low">Low</option>
            </select>
          </div>
          <div className="flex gap-2 mt-3">
            <button onClick={() => newTitle.trim() && addItem.mutate()} className="px-4 py-1.5 bg-blue-600 hover:bg-blue-500 rounded text-sm text-white">Add</button>
            <button onClick={() => setShowAdd(false)} className="px-4 py-1.5 bg-gray-700 hover:bg-gray-600 rounded text-sm text-gray-300">Cancel</button>
          </div>
        </div>
      )}

      {/* Kanban Columns */}
      <div className="grid grid-cols-1 md:grid-cols-5 gap-4">
        {COLUMNS.map(col => {
          const colItems = items.filter(i => i.status === col.key)
          const Icon = col.icon
          return (
            <div key={col.key} className={`bg-gray-800/50 rounded-xl border-t-2 ${col.bg} min-h-[200px]`}>
              <div className="px-3 py-2.5 flex items-center gap-2">
                <Icon size={16} className={col.color} />
                <span className="text-sm font-medium text-gray-200">{col.label}</span>
                <span className="ml-auto text-xs text-gray-500 bg-gray-700/50 px-1.5 py-0.5 rounded">{colItems.length}</span>
              </div>
              <div className="px-2 pb-2 space-y-2">
                {colItems.map(item => (
                  <div key={item.source} className="bg-gray-900/70 rounded-lg p-3 border border-gray-700/30 hover:border-gray-600/50 group">
                    <div className="flex items-start justify-between">
                      <p className="text-sm text-gray-200 flex-1">{item.title}</p>
                      <button
                        onClick={() => deleteItem.mutate(item.source)}
                        className="opacity-0 group-hover:opacity-100 text-gray-600 hover:text-red-400 ml-1"
                      >
                        <X size={12} />
                      </button>
                    </div>
                    <div className="flex items-center gap-2 mt-2">
                      <span className={`text-xs px-1.5 py-0.5 rounded ${PRIORITY_COLORS[item.priority] || ''}`}>
                        {item.priority}
                      </span>
                      <span className={`text-xs px-1.5 py-0.5 rounded ${OWNER_COLORS[item.owner] || 'bg-gray-700 text-gray-400'}`}>
                        {item.owner}
                      </span>
                    </div>
                    {/* Move buttons */}
                    <div className="flex gap-1 mt-2 opacity-0 group-hover:opacity-100">
                      {COLUMNS.filter(c => c.key !== col.key).map(target => (
                        <button
                          key={target.key}
                          onClick={() => updateStatus.mutate({ source: item.source, status: target.key })}
                          className="text-xs px-1.5 py-0.5 bg-gray-800 hover:bg-gray-700 rounded text-gray-400 hover:text-white"
                        >
                          → {target.label.split(' ')[0]}
                        </button>
                      ))}
                    </div>
                  </div>
                ))}
              </div>
            </div>
          )
        })}
      </div>
    </div>
  )
}
