import { useEffect, useState } from 'react'
import PodForecastChart from '../components/PodForecastChart'
import TrafficHistoryChart from '../components/TrafficHistoryChart'

// 백엔드 연동 지점 — predict/simulator/call-api가 서로 다른 서비스(포트)라 base URL을 따로 둔다.
// 앞에 통합 게이트웨이가 생기기 전까지의 임시 구성.
const API_BASE = import.meta.env.VITE_API_BASE_URL ?? ''
const SIMULATOR_BASE = import.meta.env.VITE_SIMULATOR_BASE_URL ?? 'http://localhost:8001'
const CALL_API_BASE = import.meta.env.VITE_CALL_API_BASE_URL ?? 'http://localhost:8000'

// backend/common/models/dashboard.py::DashboardStats와 동일 모양.
// 노드 수는 백엔드에 데이터 소스가 없어(C8, 보류) 항상 null로 온다.
type DashboardStats = { pods: number | null; traffic: number; nodes: number | null }

const SLIDES = [
  {
    label: '트래픽 추이 그래프',
    content: <TrafficHistoryChart />,
  },
  {
    label: '시간대별 예측 파드 수 vs 실제 파드 수',
    content: <PodForecastChart />,
  },
]

function StatTile({ label, value }: { label: string; value: number | null }) {
  return (
    <div className="flex-1 rounded-lg border border-gray-200 bg-white p-4 text-center shadow-sm">
      <div className="text-sm text-gray-500">{label}</div>
      <div className="mt-1 text-2xl font-semibold">{value ?? '—'}</div>
    </div>
  )
}

function GraphCarousel() {
  const [slide, setSlide] = useState(0)
  const goPrev = () => setSlide((slide - 1 + SLIDES.length) % SLIDES.length)
  const goNext = () => setSlide((slide + 1) % SLIDES.length)

  return (
    <div>
      <div className="mb-2 text-center text-sm text-gray-500">{SLIDES[slide].label}</div>
      <div className="relative flex items-center gap-2">
        <button
          type="button"
          onClick={goPrev}
          aria-label="이전 그래프"
          className="shrink-0 rounded-full border border-gray-300 bg-white p-2 text-gray-500 hover:bg-gray-50"
        >
          ‹
        </button>

        <div className="h-72 flex-1 rounded-lg border border-gray-200 bg-white p-2">
          {SLIDES[slide].content}
        </div>

        <button
          type="button"
          onClick={goNext}
          aria-label="다음 그래프"
          className="shrink-0 rounded-full border border-gray-300 bg-white p-2 text-gray-500 hover:bg-gray-50"
        >
          ›
        </button>
      </div>
    </div>
  )
}

const STATS_POLL_INTERVAL_MS = 10000 // 상단 통계는 최소 10초마다 반드시 재동기화한다

export default function DashboardPage() {
  const [stats, setStats] = useState<DashboardStats>({ pods: null, traffic: 0, nodes: null })

  useEffect(() => {
    let cancelled = false

    const load = () => {
      fetch(`${API_BASE}/dashboard/summary`)
        .then((res) => (res.ok ? res.json() : Promise.reject(new Error(`HTTP ${res.status}`))))
        .then((data: Partial<DashboardStats>) => {
          if (cancelled) return
          setStats({ pods: data.pods ?? null, traffic: data.traffic ?? 0, nodes: data.nodes ?? null })
        })
        .catch(() => {
          // 백엔드 미연결 상태 — 콘솔에 요청 실패가 보이는 게 정상. 연동되면 자동으로 채워짐.
        })
    }

    load()
    const timer = setInterval(load, STATS_POLL_INTERVAL_MS)
    return () => {
      cancelled = true
      clearInterval(timer)
    }
  }, [])

  const increaseTraffic = () =>
    fetch(`${SIMULATOR_BASE}/simulator/increase`, { method: 'POST' }).catch(() => {})
  const decreaseTraffic = () =>
    fetch(`${SIMULATOR_BASE}/simulator/decrease`, { method: 'POST' }).catch(() => {})
  // "SQS 메시지 유입" — simulator의 지속 TPS 제어와 별개로, call-api에 콜 1건을 바로 보내
  // SQS에 1회성으로 메시지를 넣어보는 버튼 (대응하는 simulator 전용 엔드포인트는 없음).
  const injectSqs = () =>
    fetch(`${CALL_API_BASE}/call`, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({
        user_id: 'dashboard-manual-inject',
        pickup: '강남역',
        destination: '홍대입구역',
        source: 'api',
      }),
    }).catch(() => {})
  const reset = () => fetch(`${SIMULATOR_BASE}/simulator/reset`, { method: 'POST' }).catch(() => {})

  return (
    <div className="mx-auto flex max-w-4xl flex-col gap-6">
      <h1 className="text-xl font-semibold">대시보드 / 시뮬레이터</h1>

      <div className="flex gap-4">
        <StatTile label="파드 수" value={stats.pods} />
        <StatTile label="트래픽" value={stats.traffic} />
        <StatTile label="노드 수" value={stats.nodes} />
      </div>

      <GraphCarousel />

      <div className="flex gap-3">
        <button
          type="button"
          onClick={increaseTraffic}
          className="flex-1 rounded-md bg-purple-600 px-4 py-2 text-sm font-medium text-white hover:bg-purple-700"
        >
          트래픽 증가
        </button>
        <button
          type="button"
          onClick={decreaseTraffic}
          className="flex-1 rounded-md bg-purple-100 px-4 py-2 text-sm font-medium text-purple-700 hover:bg-purple-200"
        >
          트래픽 감소
        </button>
        <button
          type="button"
          onClick={injectSqs}
          className="flex-1 rounded-md bg-gray-800 px-4 py-2 text-sm font-medium text-white hover:bg-gray-900"
        >
          SQS 메시지 유입
        </button>
        <button
          type="button"
          onClick={reset}
          className="flex-1 rounded-md border border-gray-300 px-4 py-2 text-sm font-medium text-gray-600 hover:bg-gray-50"
        >
          리셋
        </button>
      </div>
    </div>
  )
}
