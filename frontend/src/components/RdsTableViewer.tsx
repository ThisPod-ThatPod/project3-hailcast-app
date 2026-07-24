import { useEffect, useState } from 'react'

const CALL_API_BASE = import.meta.env.VITE_CALL_API_BASE_URL ?? 'http://localhost:8000'
const POLL_INTERVAL_MS = 5000
const LIMIT = 20

type CallRecord = {
  call_id: string
  status: string
  requested_at: string
  processed_at: string | null
  receive_count: number
}

function formatTime(iso: string | null): string {
  if (!iso) return '-'
  return new Date(iso).toLocaleTimeString('ko-KR', { hour12: false })
}

export default function RdsTableViewer() {
  const [rows, setRows] = useState<CallRecord[]>([])

  useEffect(() => {
    const load = () => {
      fetch(`${CALL_API_BASE}/api/calls/recent?limit=${LIMIT}`)
        .then((res) => (res.ok ? res.json() : Promise.reject(new Error(`HTTP ${res.status}`))))
        .then((data: CallRecord[]) => setRows(data))
        .catch(() => {
          // 백엔드 미연결 상태 — 빈 테이블로 표시됨. 연동되면 자동으로 채워짐.
        })
    }

    load()
    const timer = setInterval(load, POLL_INTERVAL_MS)
    return () => clearInterval(timer)
  }, [])

  return (
    <div className="flex h-full flex-col">
      <div className="mb-2 text-center text-sm text-gray-500">RDS 테이블 뷰어 (calls, 최근 {LIMIT}건)</div>
      <div className="flex-1 overflow-auto rounded-lg border border-gray-200">
        <table className="w-full text-left text-sm">
          <thead className="sticky top-0 bg-gray-50 text-gray-500">
            <tr>
              <th className="px-3 py-2 font-medium">call_id</th>
              <th className="px-3 py-2 font-medium">status</th>
              <th className="px-3 py-2 font-medium">requested_at</th>
              <th className="px-3 py-2 font-medium">processed_at</th>
              <th className="px-3 py-2 font-medium">receive_count</th>
            </tr>
          </thead>
          <tbody>
            {rows.length === 0 ? (
              <tr>
                <td colSpan={5} className="px-3 py-6 text-center text-gray-400">
                  데이터 없음
                </td>
              </tr>
            ) : (
              rows.map((row) => (
                <tr key={row.call_id} className="border-t border-gray-100">
                  <td className="px-3 py-1.5 font-mono text-xs text-gray-600">{row.call_id.slice(0, 8)}</td>
                  <td className="px-3 py-1.5">{row.status}</td>
                  <td className="px-3 py-1.5">{formatTime(row.requested_at)}</td>
                  <td className="px-3 py-1.5">{formatTime(row.processed_at)}</td>
                  <td className="px-3 py-1.5">{row.receive_count}</td>
                </tr>
              ))
            )}
          </tbody>
        </table>
      </div>
    </div>
  )
}
