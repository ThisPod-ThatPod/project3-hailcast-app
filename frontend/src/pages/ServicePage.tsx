import { useEffect, useRef, useState } from 'react'

// 백엔드 연동 지점 — call-api. backend/common/models/call.py::CallRequest와 같은 모양
// (pickup/destination은 좌표가 아니라 표시용 텍스트, B1 — 모델이 위치를 안 쓰기 때문).
const CALL_API_BASE = import.meta.env.VITE_CALL_API_BASE_URL ?? 'http://localhost:8000'

type CallUiStatus = 'idle' | 'queued' | 'processing' | 'done' | 'failed' | 'error'

const STATUS_LABEL: Record<CallUiStatus, string> = {
  idle: '',
  queued: '호출 접수됨 · 처리 대기 중',
  processing: '기사 배정 처리 중',
  done: '호출 완료',
  failed: '호출 처리 실패',
  error: '요청 실패 (백엔드 연결을 확인하세요)',
}

const POLL_INTERVAL_MS = 1500
const MAX_POLL_ATTEMPTS = 20 // worker 처리 지연 대비 최대 약 30초 폴링 후 중단

export default function ServicePage() {
  const [destination, setDestination] = useState('')
  const [status, setStatus] = useState<CallUiStatus>('idle')
  const pollTimerRef = useRef<number | null>(null)

  useEffect(() => {
    return () => {
      if (pollTimerRef.current !== null) window.clearInterval(pollTimerRef.current)
    }
  }, [])

  const stopPolling = () => {
    if (pollTimerRef.current !== null) {
      window.clearInterval(pollTimerRef.current)
      pollTimerRef.current = null
    }
  }

  const pollStatus = (requestId: string) => {
    let attempts = 0
    pollTimerRef.current = window.setInterval(async () => {
      attempts += 1
      try {
        const res = await fetch(`${CALL_API_BASE}/call/${requestId}`)
        if (res.ok) {
          const body = await res.json()
          if (body.status === 'DONE') {
            setStatus('done')
            stopPolling()
          } else if (body.status === 'FAILED') {
            setStatus('failed')
            stopPolling()
          } else if (body.status === 'PROCESSING') {
            setStatus('processing')
          }
        }
        // 404 = worker가 아직 안 집음(QUEUED는 별도 기록 안 함, call_router.py 참고) → queued 유지, 계속 폴링
      } catch {
        // 네트워크 실패는 무시하고 다음 폴링에서 재시도
      }
      if (attempts >= MAX_POLL_ATTEMPTS) stopPolling()
    }, POLL_INTERVAL_MS)
  }

  const handleCall = async () => {
    stopPolling()
    setStatus('queued')
    try {
      const res = await fetch(`${CALL_API_BASE}/call`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({
          user_id: 'service-page-user',
          pickup: '현재위치',
          destination,
          source: 'api',
        }),
      })
      if (!res.ok) {
        setStatus('error')
        return
      }
      const body = await res.json()
      pollStatus(body.request_id)
    } catch {
      setStatus('error')
    }
  }

  const isBusy = status === 'queued' || status === 'processing'

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
        disabled={isBusy}
        className="rounded-md bg-purple-600 px-4 py-3 text-sm font-medium text-white hover:bg-purple-700 disabled:cursor-not-allowed disabled:opacity-60"
      >
        호출하기
      </button>

      {status !== 'idle' && (
        <div
          className={`rounded-md px-4 py-3 text-sm ${
            status === 'done'
              ? 'bg-green-50 text-green-700'
              : status === 'failed' || status === 'error'
                ? 'bg-red-50 text-red-700'
                : 'bg-purple-50 text-purple-700'
          }`}
        >
          {STATUS_LABEL[status]}
        </div>
      )}
    </div>
  )
}
