import { useState } from 'react'

// 백엔드 연동 지점. 요청/응답 형식은 frontend/BACKEND_INTEGRATION.md 참고.
const API_BASE = import.meta.env.VITE_API_BASE_URL ?? ''

export default function ServicePage() {
  const [destination, setDestination] = useState('')

  const handleCall = () => {
    fetch(`${API_BASE}/api/call`, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ pickup: 'current_location', destination }),
    }).catch(() => {
      // 백엔드 미연결 상태 — 콘솔에 요청 실패가 보이는 게 정상.
    })
  }

  return (
    <div className="mx-auto flex max-w-md flex-col gap-4">
      <h1 className="text-xl font-semibold">서비스</h1>

      <div className="flex h-64 items-center justify-center rounded-lg border border-gray-300 bg-white text-gray-400">
        지도 (자리표시자)
      </div>

      <div className="rounded-lg border border-gray-200 bg-white">
        <div className="border-b border-gray-200 px-4 py-3 text-sm text-gray-600">
          출발: 현재위치
        </div>
        <input
          type="text"
          value={destination}
          onChange={(e) => setDestination(e.target.value)}
          placeholder="도착지 입력"
          className="w-full px-4 py-3 text-sm outline-none"
        />
      </div>

      <button
        type="button"
        onClick={handleCall}
        className="rounded-md bg-purple-600 px-4 py-3 text-sm font-medium text-white hover:bg-purple-700"
      >
        호출하기
      </button>
    </div>
  )
}
