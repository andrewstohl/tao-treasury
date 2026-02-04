import { ReactNode } from 'react'

interface ExampleWrapperProps {
  title: string
  description: string
  sourceNotebook: string
  isLoading: boolean
  error?: Error | null
  children: ReactNode
}

export default function ExampleWrapper({
  title,
  description,
  sourceNotebook,
  isLoading,
  error,
  children,
}: ExampleWrapperProps) {
  return (
    <div className="space-y-4">
      <div>
        <h2 className="text-xl font-bold">{title}</h2>
        <p className="text-sm text-gray-400 mt-1">{description}</p>
        <p className="text-xs text-gray-600 mt-0.5">
          Source: <span className="font-mono">{sourceNotebook}</span>
        </p>
      </div>
      {isLoading ? (
        <div className="bg-gray-800 rounded-lg border border-gray-700 p-6 animate-pulse h-96" />
      ) : error ? (
        <div className="bg-gray-800 rounded-lg border border-gray-700 p-6">
          <div className="text-sm text-red-400">Error: {error.message}</div>
        </div>
      ) : (
        <div className="bg-gray-800 rounded-lg border border-gray-700 p-6">
          {children}
        </div>
      )}
    </div>
  )
}
