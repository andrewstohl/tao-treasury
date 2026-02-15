import { useState, useMemo } from 'react'
import { useQuery, useMutation, useQueryClient } from '@tanstack/react-query'
import {
  BookOpen, Search, FolderOpen, FileText, Download, MessageSquare, ChevronRight, ChevronDown,
  Plus, Clock, User, Tag, X, Send, Trash2, Edit3, Eye
} from 'lucide-react'
import { format } from 'date-fns/format'
import { parseISO } from 'date-fns/parseISO'
import { supabase } from '../services/supabase'

// ─── Types ───
interface WikiEntry {
  id: number
  entry_type: string
  title: string
  content: string
  tags: string[]
  summary: string
  supersedes_id: number | null
  created_at: string
  updated_at: string
}

interface DocComment {
  id: string
  doc_id: number
  author: string
  text: string
  created_at: string
  parent_id: string | null
}

// ─── Folder Structure ───
const FOLDERS: Record<string, { label: string; icon: typeof BookOpen; types: string[] }> = {
  strategies: { label: 'Strategy Research', icon: FileText, types: ['strategy_research', 'playbook'] },
  subnets: { label: 'Subnet Analysis', icon: FolderOpen, types: ['subnet_analysis'] },
  market: { label: 'Market & Regime', icon: BookOpen, types: ['market_regime'] },
  operations: { label: 'Operations', icon: FolderOpen, types: ['operations', 'agent_report'] },
  reviews: { label: 'Performance Reviews', icon: User, types: ['performance_review'] },
}

// ─── Helpers ───
function downloadDoc(title: string, content: string) {
  const blob = new Blob([content], { type: 'text/markdown' })
  const url = URL.createObjectURL(blob)
  const a = document.createElement('a')
  a.href = url
  a.download = `${title.replace(/\s+/g, '-').toLowerCase()}.md`
  a.click()
  URL.revokeObjectURL(url)
}

function renderMarkdown(md: string) {
  // Simple markdown rendering — headers, bold, lists, code
  return md.split('\n').map((line, i) => {
    if (line.startsWith('### ')) return <h3 key={i} className="text-lg font-bold mt-4 mb-1 text-white">{line.slice(4)}</h3>
    if (line.startsWith('## ')) return <h2 key={i} className="text-xl font-bold mt-5 mb-2 text-white">{line.slice(3)}</h2>
    if (line.startsWith('# ')) return <h1 key={i} className="text-2xl font-bold mt-6 mb-3 text-white">{line.slice(2)}</h1>
    if (line.startsWith('- ')) return <li key={i} className="ml-4 text-gray-300">{line.slice(2)}</li>
    if (line.startsWith('```')) return <div key={i} className="bg-gray-900 rounded px-3 py-1 my-1 font-mono text-sm text-green-400">{line.slice(3)}</div>
    if (line.trim() === '') return <br key={i} />
    const formatted = line
      .replace(/\*\*(.*?)\*\*/g, '<strong class="text-white">$1</strong>')
      .replace(/`(.*?)`/g, '<code class="bg-gray-800 px-1 rounded text-green-400">$1</code>')
    return <p key={i} className="text-gray-300 leading-relaxed" dangerouslySetInnerHTML={{ __html: formatted }} />
  })
}

export default function Wiki() {
  const queryClient = useQueryClient()
  const [selectedFolder, setSelectedFolder] = useState<string | null>(null)
  const [selectedDoc, setSelectedDoc] = useState<WikiEntry | null>(null)
  const [searchQuery, setSearchQuery] = useState('')
  const [viewMode, setViewMode] = useState<'browse' | 'view'>('browse')
  const [commentText, setCommentText] = useState('')
  const [expandedFolders, setExpandedFolders] = useState<Set<string>>(new Set(['strategies']))

  // Fetch wiki entries
  const { data: entries = [] } = useQuery({
    queryKey: ['wiki-entries'],
    queryFn: async () => {
      const { data } = await supabase.from('wiki_entries').select('*').order('updated_at', { ascending: false })
      return (data || []) as WikiEntry[]
    }
  })

  // Fetch comments for selected doc
  const { data: comments = [] } = useQuery({
    queryKey: ['doc-comments', selectedDoc?.id],
    queryFn: async () => {
      if (!selectedDoc) return []
      const { data } = await supabase
        .from('raw_api_data')
        .select('*')
        .eq('endpoint', 'doc_comment')
        .eq('notes', String(selectedDoc.id))
        .order('fetched_at', { ascending: true })
      return (data || []).map(r => ({
        id: r.source,
        doc_id: selectedDoc.id,
        author: r.response?.author || 'Unknown',
        text: r.response?.text || '',
        created_at: r.fetched_at,
        parent_id: r.response?.parent_id || null
      })) as DocComment[]
    },
    enabled: !!selectedDoc
  })

  // Add comment mutation
  const addComment = useMutation({
    mutationFn: async (text: string) => {
      if (!selectedDoc) return
      const id = `comment_${selectedDoc.id}_${Date.now()}`
      await supabase.from('raw_api_data').insert({
        source: id,
        endpoint: 'doc_comment',
        response: { author: 'Drew', text, parent_id: null },
        fetched_at: new Date().toISOString(),
        api_status: 200,
        notes: String(selectedDoc.id)
      })
    },
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ['doc-comments', selectedDoc?.id] })
      setCommentText('')
    }
  })

  // Filter entries
  const filteredEntries = useMemo(() => {
    let result = entries
    if (searchQuery) {
      const q = searchQuery.toLowerCase()
      result = result.filter(e =>
        e.title.toLowerCase().includes(q) ||
        e.content.toLowerCase().includes(q) ||
        e.tags?.some(t => t.toLowerCase().includes(q))
      )
    }
    return result
  }, [entries, searchQuery])

  // Group by folder
  const entriesByFolder = useMemo(() => {
    const grouped: Record<string, WikiEntry[]> = {}
    for (const [key, folder] of Object.entries(FOLDERS)) {
      grouped[key] = filteredEntries.filter(e => folder.types.includes(e.entry_type))
    }
    // "Other" for uncategorized
    const allTypes = Object.values(FOLDERS).flatMap(f => f.types)
    const other = filteredEntries.filter(e => !allTypes.includes(e.entry_type))
    if (other.length > 0) grouped['other'] = other
    return grouped
  }, [filteredEntries])

  const toggleFolder = (key: string) => {
    const next = new Set(expandedFolders)
    next.has(key) ? next.delete(key) : next.add(key)
    setExpandedFolders(next)
  }

  const openDoc = (entry: WikiEntry) => {
    setSelectedDoc(entry)
    setViewMode('view')
  }

  // ─── Browse View ───
  if (viewMode === 'browse') {
    return (
      <div className="p-6 max-w-6xl mx-auto">
        <div className="flex items-center justify-between mb-6">
          <div>
            <h1 className="text-2xl font-bold text-white flex items-center gap-2">
              <BookOpen size={24} /> Document Library
            </h1>
            <p className="text-gray-400 text-sm mt-1">{entries.length} documents · Browse, search, download</p>
          </div>
        </div>

        {/* Search */}
        <div className="relative mb-6">
          <Search size={18} className="absolute left-3 top-1/2 -translate-y-1/2 text-gray-500" />
          <input
            type="text"
            placeholder="Search documents..."
            value={searchQuery}
            onChange={(e) => setSearchQuery(e.target.value)}
            className="w-full bg-gray-800 border border-gray-700 rounded-lg pl-10 pr-4 py-2.5 text-gray-200 placeholder-gray-500 focus:border-blue-500 focus:outline-none"
          />
          {searchQuery && (
            <button onClick={() => setSearchQuery('')} className="absolute right-3 top-1/2 -translate-y-1/2 text-gray-500 hover:text-white">
              <X size={16} />
            </button>
          )}
        </div>

        {/* Folder Tree */}
        <div className="space-y-1">
          {Object.entries(FOLDERS).map(([key, folder]) => {
            const docs = entriesByFolder[key] || []
            const isExpanded = expandedFolders.has(key)
            const Icon = folder.icon

            return (
              <div key={key}>
                <button
                  onClick={() => toggleFolder(key)}
                  className="w-full flex items-center gap-2 px-3 py-2 rounded-lg hover:bg-gray-800 text-left"
                >
                  {isExpanded ? <ChevronDown size={16} className="text-gray-500" /> : <ChevronRight size={16} className="text-gray-500" />}
                  <Icon size={18} className="text-blue-400" />
                  <span className="text-gray-200 font-medium">{folder.label}</span>
                  <span className="text-gray-500 text-sm ml-auto">{docs.length}</span>
                </button>

                {isExpanded && docs.length > 0 && (
                  <div className="ml-8 space-y-0.5">
                    {docs.map(doc => (
                      <div
                        key={doc.id}
                        onClick={() => openDoc(doc)}
                        className="flex items-center gap-2 px-3 py-2 rounded-lg hover:bg-gray-800/60 cursor-pointer group"
                      >
                        <FileText size={14} className="text-gray-500" />
                        <span className="text-gray-300 text-sm flex-1 truncate">{doc.title}</span>
                        <span className="text-gray-600 text-xs">{format(parseISO(doc.updated_at), 'MMM d')}</span>
                        <button
                          onClick={(e) => { e.stopPropagation(); downloadDoc(doc.title, doc.content) }}
                          className="opacity-0 group-hover:opacity-100 text-gray-500 hover:text-blue-400"
                        >
                          <Download size={14} />
                        </button>
                      </div>
                    ))}
                  </div>
                )}

                {isExpanded && docs.length === 0 && (
                  <p className="ml-12 text-gray-600 text-sm py-1">No documents</p>
                )}
              </div>
            )
          })}

          {/* Other / Uncategorized */}
          {(entriesByFolder['other'] || []).length > 0 && (
            <div>
              <button
                onClick={() => toggleFolder('other')}
                className="w-full flex items-center gap-2 px-3 py-2 rounded-lg hover:bg-gray-800 text-left"
              >
                {expandedFolders.has('other') ? <ChevronDown size={16} className="text-gray-500" /> : <ChevronRight size={16} className="text-gray-500" />}
                <FolderOpen size={18} className="text-gray-400" />
                <span className="text-gray-200 font-medium">Other</span>
                <span className="text-gray-500 text-sm ml-auto">{entriesByFolder['other'].length}</span>
              </button>
              {expandedFolders.has('other') && (
                <div className="ml-8 space-y-0.5">
                  {entriesByFolder['other'].map(doc => (
                    <div
                      key={doc.id}
                      onClick={() => openDoc(doc)}
                      className="flex items-center gap-2 px-3 py-2 rounded-lg hover:bg-gray-800/60 cursor-pointer group"
                    >
                      <FileText size={14} className="text-gray-500" />
                      <span className="text-gray-300 text-sm flex-1 truncate">{doc.title}</span>
                      <span className="text-gray-600 text-xs">{format(parseISO(doc.updated_at), 'MMM d')}</span>
                      <button
                        onClick={(e) => { e.stopPropagation(); downloadDoc(doc.title, doc.content) }}
                        className="opacity-0 group-hover:opacity-100 text-gray-500 hover:text-blue-400"
                      >
                        <Download size={14} />
                      </button>
                    </div>
                  ))}
                </div>
              )}
            </div>
          )}
        </div>
      </div>
    )
  }

  // ─── Document View ───
  return (
    <div className="p-6 max-w-6xl mx-auto">
      {/* Header */}
      <div className="flex items-center gap-3 mb-6">
        <button onClick={() => { setViewMode('browse'); setSelectedDoc(null) }} className="text-gray-400 hover:text-white">
          <ChevronRight size={20} className="rotate-180" />
        </button>
        <div className="flex-1">
          <h1 className="text-xl font-bold text-white">{selectedDoc?.title}</h1>
          <div className="flex items-center gap-4 text-sm text-gray-500 mt-1">
            <span className="flex items-center gap-1"><Clock size={12} /> {selectedDoc && format(parseISO(selectedDoc.updated_at), 'MMM d, yyyy h:mm a')}</span>
            <span className="flex items-center gap-1"><Tag size={12} /> {selectedDoc?.entry_type}</span>
          </div>
        </div>
        <button
          onClick={() => selectedDoc && downloadDoc(selectedDoc.title, selectedDoc.content)}
          className="flex items-center gap-1.5 px-3 py-1.5 bg-gray-800 hover:bg-gray-700 rounded-lg text-sm text-gray-300"
        >
          <Download size={14} /> Download
        </button>
      </div>

      {/* Tags */}
      {selectedDoc?.tags && selectedDoc.tags.length > 0 && (
        <div className="flex gap-2 mb-4">
          {selectedDoc.tags.map(tag => (
            <span key={tag} className="px-2 py-0.5 bg-blue-500/10 text-blue-400 rounded text-xs">{tag}</span>
          ))}
        </div>
      )}

      <div className="grid grid-cols-1 lg:grid-cols-3 gap-6">
        {/* Document Content */}
        <div className="lg:col-span-2 bg-gray-800/50 rounded-xl p-6 border border-gray-700/50">
          {selectedDoc && renderMarkdown(selectedDoc.content)}
        </div>

        {/* Comments Panel */}
        <div className="bg-gray-800/50 rounded-xl border border-gray-700/50 flex flex-col" style={{ maxHeight: '80vh' }}>
          <div className="px-4 py-3 border-b border-gray-700/50 flex items-center gap-2">
            <MessageSquare size={16} className="text-blue-400" />
            <span className="text-sm font-medium text-gray-200">Comments ({comments.length})</span>
          </div>

          <div className="flex-1 overflow-y-auto p-4 space-y-3">
            {comments.length === 0 && (
              <p className="text-gray-500 text-sm text-center py-4">No comments yet. Start a discussion.</p>
            )}
            {comments.map(comment => (
              <div key={comment.id} className="bg-gray-900/50 rounded-lg p-3">
                <div className="flex items-center gap-2 mb-1">
                  <span className={`text-xs font-medium ${comment.author === 'Drew' ? 'text-blue-400' : 'text-green-400'}`}>
                    {comment.author}
                  </span>
                  <span className="text-gray-600 text-xs">{format(parseISO(comment.created_at), 'MMM d, h:mm a')}</span>
                </div>
                <p className="text-gray-300 text-sm">{comment.text}</p>
              </div>
            ))}
          </div>

          {/* Comment Input */}
          <div className="p-3 border-t border-gray-700/50">
            <div className="flex gap-2">
              <input
                type="text"
                placeholder="Add a comment..."
                value={commentText}
                onChange={(e) => setCommentText(e.target.value)}
                onKeyDown={(e) => { if (e.key === 'Enter' && commentText.trim()) addComment.mutate(commentText.trim()) }}
                className="flex-1 bg-gray-900 border border-gray-700 rounded px-3 py-1.5 text-sm text-gray-200 placeholder-gray-600 focus:border-blue-500 focus:outline-none"
              />
              <button
                onClick={() => commentText.trim() && addComment.mutate(commentText.trim())}
                disabled={!commentText.trim()}
                className="px-3 py-1.5 bg-blue-600 hover:bg-blue-500 disabled:bg-gray-700 disabled:text-gray-500 rounded text-sm text-white"
              >
                <Send size={14} />
              </button>
            </div>
          </div>
        </div>
      </div>
    </div>
  )
}
