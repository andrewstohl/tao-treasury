interface EquityCurveChartProps {
  data: number[]
  color?: string
}

export function EquityCurveChart({ data, color = '#10b981' }: EquityCurveChartProps) {
  if (data.length === 0) return null

  const width = 100
  const height = 60
  const padding = 4

  const min = Math.min(...data)
  const max = Math.max(...data)
  const range = max - min || 1

  const points = data.map((value, index) => {
    const x = padding + (index / (data.length - 1)) * (width - 2 * padding)
    const y = height - padding - ((value - min) / range) * (height - 2 * padding)
    return `${x},${y}`
  }).join(' ')

  const areaPath = `${points} ${padding + width - 2 * padding},${height} ${padding},${height}`

  return (
    <svg viewBox={`0 0 ${width} ${height}`} className="w-full h-full" preserveAspectRatio="none">
      <defs>
        <linearGradient id={`gradient-${color.replace('#', '')}`} x1="0%" y1="0%" x2="0%" y2="100%">
          <stop offset="0%" stopColor={color} stopOpacity="0.3" />
          <stop offset="100%" stopColor={color} stopOpacity="0.05" />
        </linearGradient>
      </defs>
      <polygon
        points={areaPath}
        fill={`url(#gradient-${color.replace('#', '')})`}
      />
      <polyline
        points={points}
        fill="none"
        stroke={color}
        strokeWidth="0.8"
        strokeLinecap="round"
        strokeLinejoin="round"
      />
    </svg>
  )
}

interface PnlDistributionChartProps {
  distribution: number[]
}

export function PnlDistributionChart({ distribution }: PnlDistributionChartProps) {
  if (distribution.length === 0) return null

  const width = 100
  const height = 60
  const padding = 6
  const barGap = 2

  const max = Math.max(...distribution)
  const barWidth = (width - 2 * padding - (distribution.length - 1) * barGap) / distribution.length

  return (
    <svg viewBox={`0 0 ${width} ${height}`} className="w-full h-full">
      <line x1={padding} y1={height - padding} x2={width - padding} y2={height - padding} stroke="#374151" strokeWidth="0.5" />
      {distribution.map((value, index) => {
        const barHeight = (value / max) * (height - 2 * padding - 4)
        const x = padding + index * (barWidth + barGap)
        const y = height - padding - barHeight
        const color = index < distribution.length / 2 ? '#10b981' : '#ef4444'
        return (
          <rect
            key={index}
            x={x}
            y={y}
            width={barWidth}
            height={barHeight}
            fill={color}
            opacity={0.8}
            rx="1"
          />
        )
      })}
    </svg>
  )
}

interface WinLossDonutProps {
  wins: number
  losses: number
}

export function WinLossDonut({ wins, losses }: WinLossDonutProps) {
  const total = wins + losses
  if (total === 0) return null

  const width = 80
  const height = 80
  const radius = 30
  const centerX = width / 2
  const centerY = height / 2
  const strokeWidth = 10

  const circumference = 2 * Math.PI * radius
  const winRatio = wins / total
  const winOffset = circumference * winRatio

  return (
    <svg viewBox={`0 0 ${width} ${height}`} className="w-full h-full">
      <circle
        cx={centerX}
        cy={centerY}
        r={radius}
        fill="none"
        stroke="#374151"
        strokeWidth={strokeWidth}
      />
      <circle
        cx={centerX}
        cy={centerY}
        r={radius}
        fill="none"
        stroke="#10b981"
        strokeWidth={strokeWidth}
        strokeDasharray={`${winOffset} ${circumference - winOffset}`}
        strokeDashoffset={-circumference * 0.25}
        strokeLinecap="round"
      />
      <circle
        cx={centerX}
        cy={centerY}
        r={radius}
        fill="none"
        stroke="#ef4444"
        strokeWidth={strokeWidth}
        strokeDasharray={`${circumference - winOffset} ${winOffset}`}
        strokeDashoffset={winOffset - circumference * 0.25}
        strokeLinecap="round"
      />
      <text x={centerX} y={centerY - 4} textAnchor="middle" fill="#9ca3af" fontSize="8">W/L</text>
      <text x={centerX} y={centerY + 10} textAnchor="middle" fill="#fff" fontSize="10" fontWeight="bold">{wins}-{losses}</text>
    </svg>
  )
}

interface SignalStrengthBarProps {
  strength: number
}

export function SignalStrengthBar({ strength }: SignalStrengthBarProps) {
  const percentage = Math.max(0, Math.min(1, strength)) * 100

  return (
    <div className="w-full">
      <div className="flex justify-between text-xs text-[#6b7280] mb-1">
        <span>Weak</span>
        <span>Strong</span>
      </div>
      <div className="h-2 bg-[#374151] rounded-full overflow-hidden">
        <div
          className="h-full rounded-full transition-all duration-500"
          style={{
            width: `${percentage}%`,
            background: `linear-gradient(90deg, #ef4444 0%, #f59e0b 50%, #10b981 100%)`
          }}
        />
      </div>
      <div className="flex justify-end mt-1">
        <span className="text-xs font-medium text-white">{(strength * 100).toFixed(0)}%</span>
      </div>
    </div>
  )
}
