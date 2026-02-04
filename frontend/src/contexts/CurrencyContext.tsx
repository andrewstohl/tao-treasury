import { createContext, useContext, useState, ReactNode } from 'react'

export type Currency = 'tao' | 'usd'

interface CurrencyContextType {
  currency: Currency
  toggleCurrency: () => void
  setCurrency: (c: Currency) => void
}

const CurrencyContext = createContext<CurrencyContextType>({
  currency: 'tao',
  toggleCurrency: () => {},
  setCurrency: () => {},
})

export function CurrencyProvider({ children }: { children: ReactNode }) {
  const [currency, setCurrency] = useState<Currency>('tao')

  const toggleCurrency = () =>
    setCurrency((prev) => (prev === 'tao' ? 'usd' : 'tao'))

  return (
    <CurrencyContext.Provider value={{ currency, toggleCurrency, setCurrency }}>
      {children}
    </CurrencyContext.Provider>
  )
}

export function useCurrency() {
  return useContext(CurrencyContext)
}
