import { useQuery } from '@tanstack/react-query'
import ExampleWrapper from '../ExampleWrapper'
import { fetchFromProxy } from '../../../services/examplesApi'

export default function ParentHotkeyReturns() {
  const { data: validatorData, isLoading: loadingVals, error } = useQuery({
    queryKey: ['examples', 'validators-latest'],
    queryFn: () => fetchFromProxy('/api/dtao/validator/latest/v1', { limit: 200 }),
    staleTime: 5 * 60 * 1000,
  })

  const { data: subnetData, isLoading: loadingSubs } = useQuery({
    queryKey: ['examples', 'subnets-latest'],
    queryFn: () => fetchFromProxy('/api/subnet/latest/v1', { limit: 100 }),
    staleTime: 5 * 60 * 1000,
  })

  const isLoading = loadingVals || loadingSubs

  // Build subnet emission map
  const subnetEmissions: Record<number, number> = {}
  for (const sn of (subnetData?.data || [])) {
    subnetEmissions[sn.netuid] = parseFloat(sn.emission || sn.daily_emission || '0')
  }

  // Aggregate validator data
  const validators = (validatorData?.data || [])
  const validatorMap: Record<string, {
    name: string
    hotkey: string
    totalStake: number
    subnets: number
    take: number
    estimatedReturn: number
  }> = {}

  for (const v of validators) {
    const hk = v.hotkey || ''
    if (!validatorMap[hk]) {
      validatorMap[hk] = {
        name: v.name || v.validator_name || hk.slice(0, 10) + '...',
        hotkey: hk,
        totalStake: 0,
        subnets: 0,
        take: parseFloat(v.take || v.delegate_take || '0'),
        estimatedReturn: 0,
      }
    }
    const stake = parseFloat(v.total_stake || v.stake || '0')
    validatorMap[hk].totalStake += stake
    validatorMap[hk].subnets += 1

    // Estimate: nominator share = (1 - take) × emission proportion
    const netuid = v.netuid
    const emission = subnetEmissions[netuid] || 0
    const valEmission = emission * (stake > 0 ? 1 : 0) * 0.41 // rough validator share
    const nomReturn = valEmission * (1 - validatorMap[hk].take)
    validatorMap[hk].estimatedReturn += nomReturn
  }

  const rows = Object.values(validatorMap)
    .filter((v) => v.totalStake > 0)
    .sort((a, b) => b.estimatedReturn - a.estimatedReturn)
    .slice(0, 50)

  return (
    <ExampleWrapper
      title="Parent Hotkey Returns"
      description="Estimated nominator returns for top validators based on emissions and take rates."
      sourceNotebook="estimate_parent_hotkey_returns.ipynb"
      isLoading={isLoading}
      error={error as Error}
    >
      {rows.length === 0 ? (
        <p className="text-[#5a7a94] text-sm">No validator data available.</p>
      ) : (
        <div className="overflow-x-auto max-h-[500px] overflow-y-auto">
          <table className="w-full text-xs">
            <thead className="sticky top-0 bg-[#121f2d]">
              <tr className="border-b border-[#1e3a5f]">
                <th className="text-left py-1.5 px-2 text-[#5a7a94]">#</th>
                <th className="text-left py-1.5 px-2 text-[#5a7a94]">Validator</th>
                <th className="text-right py-1.5 px-2 text-[#5a7a94]">Stake (τ)</th>
                <th className="text-right py-1.5 px-2 text-[#5a7a94]">Subnets</th>
                <th className="text-right py-1.5 px-2 text-[#5a7a94]">Take %</th>
                <th className="text-right py-1.5 px-2 text-[#5a7a94]">Est. Daily Return (τ)</th>
              </tr>
            </thead>
            <tbody>
              {rows.map((v, i) => (
                <tr key={v.hotkey} className="border-b border-[#132436] hover:bg-[#1a2d42]/30">
                  <td className="py-1 px-2 text-[#243a52]">{i + 1}</td>
                  <td className="py-1 px-2 text-[#8faabe]">{v.name}</td>
                  <td className="py-1 px-2 text-right tabular-nums text-[#8faabe]">
                    {v.totalStake.toFixed(2)}
                  </td>
                  <td className="py-1 px-2 text-right text-[#6f87a0]">{v.subnets}</td>
                  <td className="py-1 px-2 text-right tabular-nums text-[#6f87a0]">
                    {(v.take * 100).toFixed(1)}%
                  </td>
                  <td className="py-1 px-2 text-right tabular-nums text-green-400">
                    {v.estimatedReturn.toFixed(6)}
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      )}
    </ExampleWrapper>
  )
}
