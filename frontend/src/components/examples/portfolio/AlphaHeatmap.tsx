import { useQuery } from '@tanstack/react-query'
import ExampleWrapper from '../ExampleWrapper'
import { fetchFromProxy } from '../../../services/examplesApi'

const RAO = 1e9

function valueToColor(value: number, max: number): string {
  if (value === 0) return '#1f2937'
  const ratio = Math.log10(value + 1) / Math.log10(max + 1)
  const r = Math.round(6 + ratio * 200)
  const g = Math.round(182 - ratio * 100)
  const b = Math.round(212 - ratio * 150)
  return `rgb(${r}, ${g}, ${b})`
}

export default function AlphaHeatmap() {
  const { data: sharesData, isLoading: loadingShares, error } = useQuery({
    queryKey: ['examples', 'alpha-shares'],
    queryFn: () => fetchFromProxy('/api/dtao/hotkey_alpha_shares/latest/v1', { limit: 500 }),
    staleTime: 5 * 60 * 1000,
  })

  const { data: subnetData, isLoading: loadingSubs } = useQuery({
    queryKey: ['examples', 'subnets-latest'],
    queryFn: () => fetchFromProxy('/api/subnet/latest/v1', { limit: 100 }),
    staleTime: 5 * 60 * 1000,
  })

  const isLoading = loadingShares || loadingSubs

  const shares = sharesData?.data || []
  const subnets = (subnetData?.data || []).map((s: any) => s.netuid).sort((a: number, b: number) => a - b)

  // hotkey is an object {ss58, hex} — use ss58 truncated as key
  const hotkeySet = new Map<string, Record<number, number>>()
  let maxVal = 0

  for (const item of shares) {
    const hkSs58 = item.hotkey?.ss58 || item.hotkey || ''
    const hk = hkSs58.slice(0, 8) + '...'
    const netuid = item.netuid
    // alpha field is in RAO
    const alpha = parseFloat(item.alpha || item.shares || '0') / RAO
    if (alpha <= 0) continue
    if (!hotkeySet.has(hk)) hotkeySet.set(hk, {})
    hotkeySet.get(hk)![netuid] = (hotkeySet.get(hk)![netuid] || 0) + alpha
    if (alpha > maxVal) maxVal = alpha
  }

  const hotkeys = Array.from(hotkeySet.entries())
    .map(([hk, vals]) => ({
      hk,
      vals,
      total: Object.values(vals).reduce((a, b) => a + b, 0),
    }))
    .sort((a, b) => b.total - a.total)
    .slice(0, 20)

  const displaySubnets = subnets.length > 0 ? subnets.slice(0, 30) : Array.from(new Set(shares.map((s: any) => s.netuid))).sort()

  return (
    <ExampleWrapper
      title="Alpha Heatmap"
      description="Heatmap of alpha holdings across validators and subnets. Brighter = more alpha."
      sourceNotebook="alpha heatmaps.ipynb"
      isLoading={isLoading}
      error={error as Error}
    >
      {hotkeys.length === 0 ? (
        <p className="text-gray-500 text-sm">No alpha share data available.</p>
      ) : (
        <div className="overflow-x-auto">
          <table className="text-xs">
            <thead>
              <tr>
                <th className="px-2 py-1 text-left text-gray-500 sticky left-0 bg-gray-800">Hotkey</th>
                {displaySubnets.map((sn: number) => (
                  <th key={sn} className="px-1 py-1 text-center text-gray-500 min-w-[32px]">
                    {sn}
                  </th>
                ))}
              </tr>
            </thead>
            <tbody>
              {hotkeys.map(({ hk, vals }) => (
                <tr key={hk}>
                  <td className="px-2 py-0.5 font-mono text-gray-400 sticky left-0 bg-gray-800">{hk}</td>
                  {displaySubnets.map((sn: number) => {
                    const val = vals[sn] || 0
                    return (
                      <td
                        key={sn}
                        className="px-1 py-0.5 text-center"
                        style={{ backgroundColor: valueToColor(val, maxVal) }}
                        title={`SN${sn}: ${val.toFixed(2)} α`}
                      >
                        {val > 0 ? '' : ''}
                      </td>
                    )
                  })}
                </tr>
              ))}
            </tbody>
          </table>
          <div className="flex items-center gap-2 mt-3 text-xs text-gray-500">
            <span>Low</span>
            <div className="flex">
              {[0, 0.2, 0.4, 0.6, 0.8, 1].map((r) => (
                <div
                  key={r}
                  className="w-6 h-3"
                  style={{ backgroundColor: valueToColor(Math.pow(10, r * Math.log10(maxVal + 1)) - 1, maxVal) }}
                />
              ))}
            </div>
            <span>High</span>
          </div>
        </div>
      )}
    </ExampleWrapper>
  )
}
