import { useState } from 'react'
import DashboardPage from './pages/DashboardPage'
import ServicePage from './pages/ServicePage'

type Page = 'dashboard' | 'service'

const NAV_ITEMS: { key: Page; label: string }[] = [
  { key: 'service', label: '서비스' },
  { key: 'dashboard', label: '대시보드/시뮬레이터' },
]

function App() {
  const [page, setPage] = useState<Page>('dashboard')

  return (
    <div className="flex min-h-screen bg-gray-50 text-gray-900">
      <aside className="w-56 shrink-0 border-r border-gray-200 bg-white p-4">
        <nav className="flex flex-col gap-2">
          {NAV_ITEMS.map((item) => (
            <button
              key={item.key}
              type="button"
              onClick={() => setPage(item.key)}
              className={`rounded-md border px-4 py-3 text-left text-sm font-medium transition-colors ${
                page === item.key
                  ? 'border-purple-400 bg-purple-50 text-purple-700'
                  : 'border-gray-200 text-gray-600 hover:bg-gray-50'
              }`}
            >
              {item.label}
            </button>
          ))}
        </nav>
      </aside>

      <main className="flex-1 p-6">
        {page === 'dashboard' ? <DashboardPage /> : <ServicePage />}
      </main>
    </div>
  )
}

export default App
