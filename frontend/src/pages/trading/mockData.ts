export interface TaoPrice {
  current: number
  change24h: number
  change24hPct: number
}

export interface Portfolio {
  spotTao: number
  shortTao: number
  netExposure: number
  hyperliquidBalance: number
  unrealizedPnl: number
  gapToClose: number
  dailyVar: number
}

export interface Trade {
  id: number
  type: 'entry' | 'exit'
  entryExit: 'Entry' | 'Exit'
  date: string
  signal: 'LONG' | 'SHORT'
  price: number
  sizeTao: number
  sizeUsd: number
  pnlUsd: number
  pnlPct: number
  favorableExcursion: number
  favorablePct: number
  adverseExcursion: number
  adversePct: number
  cumulative: number
}

export interface Position {
  size: number
  side: 'long' | 'short' | 'flat'
  entry: number
  current: number
  pnl: number
  kelly: number
  maxSize2x: number
  liqPrice2x: number
  liqPrice3x: number
  liqPrice5x: number
}

export interface SystemMetrics {
  totalPnl: number
  maxDD: number
  trades: number
  winRate: number
  profitFactor: number
  sharpe: number
}

export interface WinLossStats {
  wins: number
  losses: number
}

export interface TradingSystem {
  name: string
  params: string
  currentSignal: 'LONG' | 'SHORT' | 'FLAT'
  signalAgeBars: number
  signalAgeDays: number
  strength: number
  upperBand: number
  lowerBand: number
  metrics: SystemMetrics
  equityCurve: number[]
  position: Position
  trades: Trade[]
  pnlDistribution: number[]
  winLossStats: WinLossStats
}

export interface CapitalAllocation {
  shortProfitSplit: {
    dca: number
    margin: number
  }
  recoveryProgress: number
}

export const MOCK_TAO_PRICE: TaoPrice = {
  current: 189.80,
  change24h: -2.35,
  change24hPct: -1.22
}

export const MOCK_PORTFOLIO: Portfolio = {
  spotTao: 511,
  shortTao: 100,
  netExposure: 411,
  hyperliquidBalance: 20000,
  unrealizedPnl: -15114,
  gapToClose: 15114,
  dailyVar: 7404
}

const generateEquityCurve = (): number[] => {
  const points: number[] = [0]
  let value = 0
  for (let i = 1; i < 40; i++) {
    value += (Math.random() - 0.35) * 5000
    value = Math.max(0, value)
    points.push(value)
  }
  points[points.length - 1] = 114800
  return points
}

const generateTrades = (): Trade[] => [
  { id: 1, type: 'entry', entryExit: 'Entry', date: '2024-01-15', signal: 'LONG', price: 182.50, sizeTao: 50, sizeUsd: 9125, pnlUsd: 0, pnlPct: 0, favorableExcursion: 185.20, favorablePct: 1.48, adverseExcursion: 180.80, adversePct: -0.93, cumulative: 0 },
  { id: 2, type: 'exit', entryExit: 'Exit', date: '2024-01-18', signal: 'LONG', price: 188.30, sizeTao: 50, sizeUsd: 9415, pnlUsd: 290, pnlPct: 3.18, favorableExcursion: 189.50, favorablePct: 3.84, adverseExcursion: 181.20, adversePct: -0.71, cumulative: 290 },
  { id: 3, type: 'entry', entryExit: 'Entry', date: '2024-01-22', signal: 'SHORT', price: 195.40, sizeTao: 75, sizeUsd: 14655, pnlUsd: 0, pnlPct: 0, favorableExcursion: 192.10, favorablePct: 1.69, adverseExcursion: 198.80, adversePct: -1.74, cumulative: 290 },
  { id: 4, type: 'exit', entryExit: 'Exit', date: '2024-01-25', signal: 'SHORT', price: 191.20, sizeTao: 75, sizeUsd: 14340, pnlUsd: 315, pnlPct: 2.15, favorableExcursion: 190.50, favorablePct: 2.53, adverseExcursion: 197.60, adversePct: -1.13, cumulative: 605 },
  { id: 5, type: 'entry', entryExit: 'Entry', date: '2024-02-01', signal: 'LONG', price: 185.60, sizeTao: 60, sizeUsd: 11136, pnlUsd: 0, pnlPct: 0, favorableExcursion: 192.40, favorablePct: 3.66, adverseExcursion: 183.20, adversePct: -1.29, cumulative: 605 },
  { id: 6, type: 'exit', entryExit: 'Exit', date: '2024-02-05', signal: 'LONG', price: 191.80, sizeTao: 60, sizeUsd: 11508, pnlUsd: 372, pnlPct: 3.34, favorableExcursion: 193.20, favorablePct: 4.09, adverseExcursion: 184.50, adversePct: -0.59, cumulative: 977 },
  { id: 7, type: 'entry', entryExit: 'Entry', date: '2024-02-10', signal: 'SHORT', price: 193.00, sizeTao: 100, sizeUsd: 19300, pnlUsd: 0, pnlPct: 0, favorableExcursion: 189.80, favorablePct: 1.66, adverseExcursion: 196.50, adversePct: -1.81, cumulative: 977 },
  { id: 8, type: 'entry', entryExit: 'Entry', date: '2024-02-14', signal: 'SHORT', price: 189.80, sizeTao: 100, sizeUsd: 18980, pnlUsd: 320, pnlPct: 1.66, favorableExcursion: 188.50, favorablePct: 2.33, adverseExcursion: 194.20, adversePct: -1.14, cumulative: 1297 },
]

export const MOCK_HEDGE_SYSTEM: TradingSystem = {
  name: 'Hedge System',
  params: 'EMA(5,21) Normal 4H',
  currentSignal: 'LONG',
  signalAgeBars: 41,
  signalAgeDays: 6,
  strength: 0.78,
  upperBand: 181.67,
  lowerBand: 148.23,
  metrics: {
    totalPnl: 114800,
    maxDD: 14.7,
    trades: 110,
    winRate: 60,
    profitFactor: 1.85,
    sharpe: 2.18
  },
  equityCurve: generateEquityCurve(),
  position: {
    size: 100,
    side: 'short',
    entry: 193,
    current: 189.80,
    pnl: 320,
    kelly: 9,
    maxSize2x: 211,
    liqPrice2x: 280,
    liqPrice3x: 251,
    liqPrice5x: 228
  },
  trades: generateTrades(),
  pnlDistribution: [12, 18, 22, 16, 14, 10, 5, 3],
  winLossStats: { wins: 66, losses: 44 }
}

const generateSwingEquityCurve = (): number[] => {
  const points: number[] = [0]
  let value = 0
  for (let i = 1; i < 35; i++) {
    value += (Math.random() - 0.38) * 6000
    value = Math.max(0, value)
    points.push(value)
  }
  points[points.length - 1] = 87500
  return points
}

export const MOCK_SWING_SYSTEM: TradingSystem = {
  name: 'Swing System',
  params: 'EMA(8,13) Normal 4H',
  currentSignal: 'SHORT',
  signalAgeBars: 18,
  signalAgeDays: 3,
  strength: 0.65,
  upperBand: 195.40,
  lowerBand: 172.30,
  metrics: {
    totalPnl: 87500,
    maxDD: 18.2,
    trades: 82,
    winRate: 57.3,
    profitFactor: 1.68,
    sharpe: 1.94
  },
  equityCurve: generateSwingEquityCurve(),
  position: {
    size: 0,
    side: 'flat',
    entry: 0,
    current: 189.80,
    pnl: 0,
    kelly: 7,
    maxSize2x: 165,
    liqPrice2x: 285,
    liqPrice3x: 255,
    liqPrice5x: 230
  },
  trades: generateTrades().slice(0, 6).map((t, i) => ({ ...t, id: i + 1, pnlUsd: t.pnlUsd * 0.8, cumulative: t.cumulative * 0.8 })),
  pnlDistribution: [10, 15, 20, 18, 12, 10, 8, 7],
  winLossStats: { wins: 47, losses: 35 }
}

export const CAPITAL_ALLOCATION: CapitalAllocation = {
  shortProfitSplit: {
    dca: 70,
    margin: 30
  },
  recoveryProgress: 0.02
}
