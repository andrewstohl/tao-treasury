interface EquityCurveChartProps {
  data: { date: string; value: number; in_root: boolean; num_holdings: number }[]
  initial: number
  comparison?: { date: string; value: number }[] | null
}

export default function EquityCurveChart({ data, initial, comparison }: EquityCurveChartProps) {
  if (data.length < 2) return null

  // Combine data for range calculation
  const allValues = [...data.map(d => d.value)]
  if (comparison) {
    allValues.push(...comparison.map(c => c.value))
  }

  const maxVal = Math.max(...allValues)
  const minVal = Math.min(...allValues)
  const range = maxVal - minVal || 1

  const width = 800
  const height = 200
  const padL = 50
  const padR = 10
  const padT = 10
  const padB = 25
  const chartW = width - padL - padR
  const chartH = height - padT - padB

  const points = data.map((d, i) => {
    const x = padL + (i / (data.length - 1)) * chartW
    const y = padT + chartH - ((d.value - minVal) / range) * chartH
    return { x, y, ...d }
  })

  const linePath = points.map((p, i) => `${i === 0 ? 'M' : 'L'}${p.x},${p.y}`).join(' ')

  // Fill area under curve
  const areaPath = linePath + ` L${points[points.length - 1].x},${padT + chartH} L${points[0].x},${padT + chartH} Z`

  // Comparison line (if provided)
  let compPoints: { x: number; y: number }[] = []
  let compPath = ''
  if (comparison && comparison.length > 0) {
    compPoints = comparison.map((d, i) => {
      const x = padL + (i / (comparison.length - 1)) * chartW
      const y = padT + chartH - ((d.value - minVal) / range) * chartH
      return { x, y }
    })
    compPath = compPoints.map((p, i) => `${i === 0 ? 'M' : 'L'}${p.x},${p.y}`).join(' ')
  }

  // Reference line at initial capital
  const refY = padT + chartH - ((initial - minVal) / range) * chartH

  // Y axis labels
  const yLabels = [minVal, initial, maxVal].map(v => ({
    val: v,
    y: padT + chartH - ((v - minVal) / range) * chartH,
    label: v.toFixed(0),
  }))

  // X axis labels (show ~5 dates)
  const step = Math.max(1, Math.floor(data.length / 5))
  const xLabels = data.filter((_, i) => i % step === 0 || i === data.length - 1).map((d) => ({
    x: padL + (data.indexOf(d) / (data.length - 1)) * chartW,
    label: d.date.slice(5), // MM-DD
  }))

  const finalReturn = data.length > 0 ? ((data[data.length - 1].value - initial) / initial) : 0
  const curveColor = finalReturn >= 0 ? '#4ade80' : '#f87171'
  const fillColor = finalReturn >= 0 ? 'rgba(74,222,128,0.1)' : 'rgba(248,113,113,0.1)'

  return (
    <svg viewBox={`0 0 ${width} ${height}`} className="w-full" style={{ maxHeight: 240 }}>
      {/* Grid lines */}
      {yLabels.map((yl, i) => (
        <g key={i}>
          <line x1={padL} y1={yl.y} x2={width - padR} y2={yl.y} stroke="#374151" strokeWidth={0.5} strokeDasharray={yl.val === initial ? '4,2' : '0'} />
          <text x={padL - 4} y={yl.y + 3} textAnchor="end" fill="#6b7280" fontSize={10}>{yl.label}</text>
        </g>
      ))}

      {/* X axis labels */}
      {xLabels.map((xl, i) => (
        <text key={i} x={xl.x} y={height - 4} textAnchor="middle" fill="#6b7280" fontSize={9}>{xl.label}</text>
      ))}

      {/* Reference line */}
      <line x1={padL} y1={refY} x2={width - padR} y2={refY} stroke="#6b7280" strokeWidth={1} strokeDasharray="4,2" />
      <text x={padL - 4} y={refY - 5} textAnchor="end" fill="#9ca3af" fontSize={9}>start</text>

      {/* Comparison line (if provided) */}
      {compPath && (
        <path d={compPath} fill="none" stroke="#9ca3af" strokeWidth={1.5} strokeDasharray="4,2" opacity={0.7} />
      )}

      {/* Area fill */}
      <path d={areaPath} fill={fillColor} />

      {/* Line */}
      <path d={linePath} fill="none" stroke={curveColor} strokeWidth={2} />

      {/* Root periods (gray dots) */}
      {points.filter(p => p.in_root).map((p, i) => (
        <circle key={i} cx={p.x} cy={p.y} r={3} fill="#6b7280" />
      ))}

      {/* Final value label */}
      {points.length > 0 && (
        <text
          x={points[points.length - 1].x}
          y={points[points.length - 1].y - 8}
          textAnchor="end"
          fill={curveColor}
          fontSize={11}
          fontWeight="bold"
        >
          {data[data.length - 1].value.toFixed(1)}
        </text>
      )}

      {/* Comparison final value */}
      {compPoints.length > 0 && comparison && (
        <text
          x={compPoints[compPoints.length - 1].x - 5}
          y={compPoints[compPoints.length - 1].y - 8}
          textAnchor="end"
          fill="#9ca3af"
          fontSize={10}
        >
          {comparison[comparison.length - 1].value.toFixed(1)}
        </text>
      )}

      {/* Legend */}
      {comparison && (
        <g>
          <line x1={width - 120} y1={15} x2={width - 100} y2={15} stroke={curveColor} strokeWidth={2} />
          <text x={width - 95} y={18} fill={curveColor} fontSize={9}>Strategy</text>
          <line x1={width - 120} y1={28} x2={width - 100} y2={28} stroke="#9ca3af" strokeWidth={1.5} strokeDasharray="4,2" />
          <text x={width - 95} y={31} fill="#9ca3af" fontSize={9}>Equal Weight</text>
        </g>
      )}
    </svg>
  )
}
