import { LineChart, Line, YAxis } from 'recharts'
import type { SparklinePoint } from '../../../types'

interface SparklineCellProps {
  data: SparklinePoint[] | null | undefined
}

export default function SparklineCell({ data }: SparklineCellProps) {
  if (!data || data.length === 0) {
    return <span className="text-[#4a6a80]">--</span>
  }

  const trend = data[data.length - 1].price >= data[0].price
  const color = trend ? '#4ade80' : '#f87171' // green-400 / red-400

  // Compute Y domain with padding so small price movements fill the chart height
  const prices = data.map(d => d.price)
  const min = Math.min(...prices)
  const max = Math.max(...prices)
  const range = max - min
  // Add 10% padding, or if range is near-zero, create artificial range around midpoint
  const padding = range > 0 ? range * 0.1 : min * 0.01 || 0.0001
  const yDomain: [number, number] = [min - padding, max + padding]

  return (
    <div className="flex items-center justify-center">
      <LineChart width={240} height={48} data={data} margin={{ top: 2, right: 2, bottom: 2, left: 2 }}>
        <YAxis domain={yDomain} hide />
        <Line
          type="monotone"
          dataKey="price"
          stroke={color}
          strokeWidth={2}
          dot={false}
          isAnimationActive={false}
        />
      </LineChart>
    </div>
  )
}
