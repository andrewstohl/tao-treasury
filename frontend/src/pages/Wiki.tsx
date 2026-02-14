import { useState } from 'react'
import { useQuery } from '@tanstack/react-query'
import {
  BookOpen,
  Search,
  Tag,
  Clock,
  User,
  FileText,
  Lightbulb,
  TrendingUp,
  Globe,
  Filter,
  ChevronRight,
  X,
  ExternalLink,
  Calendar,
  Edit3,
} from 'lucide-react'
import { format, parseISO } from 'date-fns'
import { supabaseQueries, type WikiEntry } from '../services/supabase'

// Category configurations
const CATEGORIES = {
  all: { label: 'All Entries', icon: BookOpen, color: '#2a3ded' },
  strategy_research: { label: 'Strategy Research', icon: Lightbulb, color: '#10b981' },
  subnet_analysis: { label: 'Subnet Analysis', icon: Globe, color: '#f59e0b' },
  market_regime: { label: 'Market Regime', icon: TrendingUp, color: '#ef4444' },
}

// Get category style
function getCategoryStyle(category: string): { bg: string; text: string; border: string } {
  switch (category.toLowerCase()) {
    case 'strategy_research':
      return {
        bg: 'bg-emerald-500/10',
        text: 'text-emerald-400',
        border: 'border-emerald-500/30',
      }
    case 'subnet_analysis':
      return {
        bg: 'bg-amber-500/10',
        text: 'text-amber-400',
        border: 'border-amber-500/30',
      }
    case 'market_regime':
      return {
        bg: 'bg-red-500/10',
        text: 'text-red-400',
        border: 'border-red-500/30',
      }
    default:
      return {
        bg: 'bg-blue-500/10',
        text: 'text-blue-400',
        border: 'border-blue-500/30',
      }
  }
}

// Format category label
function formatCategoryLabel(category: string): string {
  return category
    .split('_')
    .map((word) => word.charAt(0).toUpperCase() + word.slice(1))
    .join(' ')
}

export default function Wiki() {
  const [selectedCategory, setSelectedCategory] = useState<string>('all')
  const [searchQuery, setSearchQuery] = useState('')
  const [selectedEntry, setSelectedEntry] = useState<WikiEntry | null>(null)
  const [isModalOpen, setIsModalOpen] = useState(false)

  // Fetch wiki entries
  const { data: wikiEntries, isLoading } = useQuery({
    queryKey: ['supabase-wiki-entries', selectedCategory],
    queryFn: () =>
      supabaseQueries.getWikiEntries(selectedCategory === 'all' ? undefined : selectedCategory),
    refetchInterval: 60000,
  })

  // Search wiki entries
  const { data: searchResults, isLoading: isSearching } = useQuery({
    queryKey: ['supabase-wiki-search', searchQuery],
    queryFn: () => supabaseQueries.searchWikiEntries(searchQuery),
    enabled: searchQuery.length > 2,
  })

  // Determine which data to display
  const displayEntries = searchQuery.length > 2 ? searchResults : wikiEntries

  // Open entry modal
  const openEntry = (entry: WikiEntry) => {
    setSelectedEntry(entry)
    setIsModalOpen(true)
  }

  // Close modal
  const closeModal = () => {
    setIsModalOpen(false)
    setSelectedEntry(null)
  }

  // Get all unique tags
  const allTags = wikiEntries
    ? [...new Set(wikiEntries.flatMap((e) => e.tags || []))]
    : []

  return (
    <div className="space-y-6">
      {/* Header */}
      <div className="flex items-center justify-between">
        <div>
          <h1 className="text-2xl font-bold text-[#2a3ded] flex items-center gap-2">
            <BookOpen className="w-6 h-6" />
            Research Wiki
          </h1>
          <p className="text-sm text-[#8a8f98] mt-1">
            Strategy research, subnet analysis, and market regime notes
          </p>
        </div>
      </div>

      {/* Category Filter */}
      <div className="bg-[#16181d] rounded-lg border border-[#2a2f38] p-4">
        <div className="flex flex-wrap gap-2">
          {Object.entries(CATEGORIES).map(([key, config]) => {
            const Icon = config.icon
            const isActive = selectedCategory === key
            return (
              <button
                key={key}
                onClick={() => setSelectedCategory(key)}
                className={`flex items-center gap-2 px-4 py-2 rounded-lg text-sm font-medium transition-all ${
                  isActive
                    ? 'bg-[#2a3ded] text-white'
                    : 'bg-[#0d0f12] text-[#9ca3af] hover:bg-[#1e2128] hover:text-white'
                }`}
              >
                <Icon className="w-4 h-4" />
                {config.label}
              </button>
            )
          })}
        </div>
      </div>

      {/* Search Bar */}
      <div className="relative">
        <Search className="absolute left-4 top-3.5 w-5 h-5 text-[#6b7280]" />
        <input
          type="text"
          placeholder="Search wiki entries..."
          value={searchQuery}
          onChange={(e) => setSearchQuery(e.target.value)}
          className="w-full bg-[#16181d] border border-[#2a2f38] rounded-lg pl-12 pr-10 py-3 text-[#8faabe] placeholder-gray-500 focus:outline-none focus:border-[#2a3ded] transition-colors"
        />
        {searchQuery && (
          <button
            onClick={() => setSearchQuery('')}
            className="absolute right-4 top-3.5 text-[#6b7280] hover:text-white"
          >
            <X className="w-5 h-5" />
          </button>
        )}
      </div>

      {/* Stats */}
      <div className="flex items-center gap-4 text-sm text-[#6b7280]">
        <span>{displayEntries?.length || 0} entries</span>
        {allTags.length > 0 && (
          <>
            <span>•</span>
            <span>{allTags.length} tags</span>
          </>
        )}
        {searchQuery.length > 2 && (
          <>
            <span>•</span>
            <span className="text-[#2a3ded]">Search results for "{searchQuery}"</span>
          </>
        )}
      </div>

      {/* Wiki Entries Grid */}
      {isLoading || isSearching ? (
        <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-3 gap-4">
          {[1, 2, 3, 4, 5, 6].map((i) => (
            <div
              key={i}
              className="bg-[#16181d] rounded-lg border border-[#2a2f38] p-5 h-48 animate-pulse"
            >
              <div className="h-4 bg-[#1e2128] rounded w-20 mb-3" />
              <div className="h-6 bg-[#1e2128] rounded w-3/4 mb-2" />
              <div className="h-4 bg-[#1e2128] rounded w-full mb-1" />
              <div className="h-4 bg-[#1e2128] rounded w-2/3" />
            </div>
          ))}
        </div>
      ) : (
        <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-3 gap-4">
          {displayEntries?.map((entry) => {
            const categoryStyle = getCategoryStyle(entry.category)

            return (
              <div
                key={entry.entry_id}
                onClick={() => openEntry(entry)}
                className="bg-[#16181d] rounded-lg border border-[#2a2f38] p-5 cursor-pointer hover:border-[#2a3ded] hover:bg-[#1e2128] transition-all group"
              >
                {/* Category Badge */}
                <div className="flex items-center justify-between mb-3">
                  <span
                    className={`inline-flex items-center gap-1.5 px-2.5 py-1 rounded-full text-xs font-medium border ${categoryStyle.bg} ${categoryStyle.text} ${categoryStyle.border}`}
                  >
                    {formatCategoryLabel(entry.category)}
                  </span>
                  <ChevronRight className="w-4 h-4 text-[#6b7280] opacity-0 group-hover:opacity-100 transition-opacity" />
                </div>

                {/* Title */}
                <h3 className="text-lg font-semibold text-white mb-2 line-clamp-2">
                  {entry.title}
                </h3>

                {/* Preview */}
                <p className="text-sm text-[#9ca3af] line-clamp-3 mb-4">
                  {entry.content.slice(0, 150)}
                  {entry.content.length > 150 ? '...' : ''}
                </p>

                {/* Tags */}
                {entry.tags && entry.tags.length > 0 && (
                  <div className="flex flex-wrap gap-1.5 mb-4">
                    {entry.tags.slice(0, 3).map((tag) => (
                      <span
                        key={tag}
                        className="inline-flex items-center gap-1 px-2 py-0.5 bg-[#0d0f12] rounded text-xs text-[#6b7280]"
                      >
                        <Tag className="w-3 h-3" />
                        {tag}
                      </span>
                    ))}
                    {entry.tags.length > 3 && (
                      <span className="text-xs text-[#6b7280]">
                        +{entry.tags.length - 3}
                      </span>
                    )}
                  </div>
                )}

                {/* Footer */}
                <div className="flex items-center justify-between text-xs text-[#6b7280] pt-3 border-t border-[#2a2f38]">
                  <div className="flex items-center gap-1">
                    <User className="w-3 h-3" />
                    {entry.author || 'System'}
                  </div>
                  <div className="flex items-center gap-1">
                    <Clock className="w-3 h-3" />
                    {format(parseISO(entry.updated_at), 'MMM d, yyyy')}
                  </div>
                </div>
              </div>
            )
          })}
        </div>
      )}

      {/* Empty State */}
      {displayEntries?.length === 0 && !isLoading && (
        <div className="text-center py-16 text-[#6b7280]">
          <BookOpen className="w-12 h-12 mx-auto mb-4 opacity-50" />
          <p className="text-lg font-medium text-white mb-1">No entries found</p>
          <p className="text-sm">
            {searchQuery
              ? 'Try adjusting your search terms'
              : 'Entries will appear when research is added to the wiki'}
          </p>
        </div>
      )}

      {/* Entry Modal */}
      {isModalOpen && selectedEntry && (
        <div
          className="fixed inset-0 bg-black/70 backdrop-blur-sm flex items-center justify-center p-4 z-50"
          onClick={closeModal}
        >
          <div
            className="bg-[#16181d] rounded-xl border border-[#2a2f38] max-w-3xl w-full max-h-[90vh] overflow-hidden"
            onClick={(e) => e.stopPropagation()}
          >
            {/* Modal Header */}
            <div className="px-6 py-4 border-b border-[#2a2f38] flex items-center justify-between">
              <div className="flex items-center gap-3">
                <span
                  className={`inline-flex items-center gap-1.5 px-2.5 py-1 rounded-full text-xs font-medium border ${
                    getCategoryStyle(selectedEntry.category).bg
                  } ${getCategoryStyle(selectedEntry.category).text} ${
                    getCategoryStyle(selectedEntry.category).border
                  }`}
                >
                  {formatCategoryLabel(selectedEntry.category)}
                </span>
                <span className="text-xs text-[#6b7280]">
                  ID: {selectedEntry.entry_id}
                </span>
              </div>
              <button
                onClick={closeModal}
                className="p-2 hover:bg-[#2a2f38] rounded-lg transition-colors"
              >
                <X className="w-5 h-5 text-[#6b7280]" />
              </button>
            </div>

            {/* Modal Content */}
            <div className="p-6 overflow-y-auto max-h-[calc(90vh-140px)]">
              <h2 className="text-2xl font-bold text-white mb-4">
                {selectedEntry.title}
              </h2>

              {/* Metadata */}
              <div className="flex flex-wrap items-center gap-4 text-sm text-[#6b7280] mb-6">
                <div className="flex items-center gap-1">
                  <User className="w-4 h-4" />
                  {selectedEntry.author || 'System'}
                </div>
                <div className="flex items-center gap-1">
                  <Calendar className="w-4 h-4" />
                  Created: {format(parseISO(selectedEntry.created_at), 'MMM d, yyyy')}
                </div>
                <div className="flex items-center gap-1">
                  <Edit3 className="w-4 h-4" />
                  Updated: {format(parseISO(selectedEntry.updated_at), 'MMM d, yyyy')}
                </div>
              </div>

              {/* Content */}
              <div className="prose prose-invert max-w-none">
                <div className="text-[#9ca3af] whitespace-pre-wrap leading-relaxed">
                  {selectedEntry.content}
                </div>
              </div>

              {/* Tags */}
              {selectedEntry.tags && selectedEntry.tags.length > 0 && (
                <div className="mt-6 pt-6 border-t border-[#2a2f38]">
                  <div className="text-xs text-[#6b7280] mb-2 uppercase tracking-wider">
                    Tags
                  </div>
                  <div className="flex flex-wrap gap-2">
                    {selectedEntry.tags.map((tag) => (
                      <span
                        key={tag}
                        className="inline-flex items-center gap-1.5 px-3 py-1.5 bg-[#0d0f12] rounded-lg text-sm text-[#9ca3af]"
                      >
                        <Tag className="w-3 h-3" />
                        {tag}
                      </span>
                    ))}
                  </div>
                </div>
              )}
            </div>

            {/* Modal Footer */}
            <div className="px-6 py-4 border-t border-[#2a2f38] flex items-center justify-between">
              <span className="text-xs text-[#6b7280]">
                Entry ID: {selectedEntry.entry_id}
              </span>
              <button
                onClick={closeModal}
                className="px-4 py-2 bg-[#2a3ded] hover:bg-[#3a4dff] rounded-lg text-sm font-medium text-white transition-colors"
              >
                Close
              </button>
            </div>
          </div>
        </div>
      )}
    </div>
  )
}
