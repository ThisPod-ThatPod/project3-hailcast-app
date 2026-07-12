import { useEffect, useState } from 'react'
import PodForecastChart from '../components/PodForecastChart'
import TrafficHistoryChart from '../components/TrafficHistoryChart'

// 백엔드 연동 지점. 요청/응답 형식은 frontend/BACKEND_INTEGRATION.md 참고.
const API_BASE = import.meta.env.VITE_API_BASE_URL ?? ''

type NodeUsage = { id: string; usage: number }
type DashboardStats = { pods: number; traffic: number; nodes: NodeUsage[] }

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

function StatTile({ label, value }: { label: string; value: number }) {
  return (
    <div className="flex-1 rounded-lg border border-gray-200 bg-white p-4 text-center shadow-sm">
      <div className="text-sm text-gray-500">{label}</div>
      <div className="mt-1 text-2xl font-semibold">{value}</div>
    </div>
  )
}

function NodeUsageBar({ index, usage }: { index: number; usage: number }) {
  return (
    <div className="rounded-md border border-gray-200 bg-white p-3">
      <div className="mb-1 flex justify-between text-sm text-gray-600">
        <span>노드{index + 1} 사용률</span>
        <span>{usage}%</span>
      </div>
      <div className="h-2 w-full rounded-full bg-gray-100">
        <div
          className="h-2 rounded-full bg-purple-500"
          style={{ width: `${usage}%` }}
        />
      </div>
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

export default function DashboardPage() {
  const [stats, setStats] = useState<DashboardStats>({ pods: 0, traffic: 0, nodes: [] })

  useEffect(() => {
    fetch(`${API_BASE}/api/dashboard/stats`)
      .then((res) => res.json())
      .then(setStats)
      .catch(() => {
        // 백엔드 미연결 상태 — 콘솔에 요청 실패가 보이는 게 정상. 연동되면 자동으로 채워짐.
      })
  }, [])

  const increaseTraffic = () =>
    fetch(`${API_BASE}/api/simulator/traffic/increase`, { method: 'POST' }).catch(() => {})
  const decreaseTraffic = () =>
    fetch(`${API_BASE}/api/simulator/traffic/decrease`, { method: 'POST' }).catch(() => {})
  const injectSqs = () => fetch(`${API_BASE}/api/simulator/sqs-inject`, { method: 'POST' }).catch(() => {})
  const reset = () => fetch(`${API_BASE}/api/simulator/reset`, { method: 'POST' }).catch(() => {})

  return (
    <div className="mx-auto flex max-w-4xl flex-col gap-6">
      <h1 className="text-xl font-semibold">대시보드 / 시뮬레이터</h1>

      <div className="flex gap-4">
        <StatTile label="파드 수" value={stats.pods} />
        <StatTile label="트래픽" value={stats.traffic} />
        <StatTile label="노드 수" value={stats.nodes.length} />
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

      <div className="flex flex-col gap-2">
        {stats.nodes.map((node, index) => (
          <NodeUsageBar key={node.id} index={index} usage={node.usage} />
        ))}
      </div>
    </div>
  )
}
