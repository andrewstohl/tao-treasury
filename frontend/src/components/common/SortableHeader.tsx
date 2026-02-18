import { ChevronUp, ChevronDown, ChevronsUpDown } from 'lucide-react'

export type SortDirection = 'asc' | 'desc' | null

interface SortableHeaderProps<K extends string> {
  label: string
  sortKey: K
  currentSortKey: K | null
  currentDirection: SortDirection
  onSort: (key: K) => void
  align?: 'left' | 'center' | 'right'
}

export default function SortableHeader<K extends string>({
  label,
  sortKey,
  currentSortKey,
  currentDirection,
  onSort,
  align = 'left',
}: SortableHeaderProps<K>) {
  const isActive = currentSortKey === sortKey

  return (
    <th
      className={`px-4 py-3 text-xs font-medium text-white uppercase tracking-wider cursor-pointer hover:bg-[#1a2d42]/50 select-none ${
        align === 'right' ? 'text-right' : align === 'center' ? 'text-center' : 'text-left'
      }`}
      onClick={() => onSort(sortKey)}
    >
      <div className={`flex items-center gap-1 ${align === 'right' ? 'justify-end' : align === 'center' ? 'justify-center' : ''}`}>
        <span>{label}</span>
        <span className="text-[#5a7a94]">
          {isActive ? (
            currentDirection === 'asc' ? (
              <ChevronUp className="w-3 h-3" />
            ) : (
              <ChevronDown className="w-3 h-3" />
            )
          ) : (
            <ChevronsUpDown className="w-3 h-3 opacity-50" />
          )}
        </span>
      </div>
    </th>
  )
}

/** Shared sort-toggle logic for use with useState. */
export function useSortToggle<K extends string>(
  sortKey: K | null,
  sortDirection: SortDirection,
  setSortKey: (key: K | null) => void,
  setSortDirection: (dir: SortDirection) => void
) {
  return (key: K) => {
    if (sortKey === key) {
      if (sortDirection === 'desc') {
        setSortDirection('asc')
      } else if (sortDirection === 'asc') {
        setSortKey(null)
        setSortDirection(null)
      }
    } else {
      setSortKey(key)
      setSortDirection('desc')
    }
  }
}
