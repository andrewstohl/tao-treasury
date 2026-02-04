import axios from 'axios'

const API_URL = import.meta.env.VITE_API_URL || 'http://localhost:8050'

const client = axios.create({
  baseURL: API_URL,
  headers: { 'Content-Type': 'application/json' },
})

export async function fetchFromProxy(
  endpoint: string,
  params: Record<string, string | number> = {},
): Promise<any> {
  const { data } = await client.get('/api/v1/examples/proxy', {
    params: { endpoint, ...params },
  })
  return data
}

export async function getWalletAddress(): Promise<string> {
  const { data } = await client.get('/api/v1/examples/wallet')
  return data.wallet_address
}
