import { useEffect, useState } from 'react'
import PodForecastChart from '../components/PodForecastChart'
import TrafficHistoryChart from '../components/TrafficHistoryChart'
import RdsTableViewer from '../components/RdsTableViewer'

// 백엔드 연동 지점 — predict/simulator/call-api가 서로 다른 서비스(포트)라 base URL을 따로 둔다.
// 앞에 통합 게이트웨이가 생기기 전까지의 임시 구성.
const API_BASE = import.meta.env.VITE_API_BASE_URL ?? ''
const SIMULATOR_BASE = import.meta.env.VITE_SIMULATOR_BASE_URL ?? 'http://localhost:8001'
const CALL_API_BASE = import.meta.env.VITE_CALL_API_BASE_URL ?? 'http://localhost:8000'

// backend/common/models/dashboard.py::DashboardStats와 동일 모양.
// 노드 수는 백엔드에 데이터 소스가 없어(C8, 보류) 항상 null로 온다.
type DashboardStats = { pods: number | null; traffic: number; nodes: number | null }

function StatTile({ label, value }: { label: string; value: number | null }) {
  return (
    <div className="flex-1 rounded-lg border border-gray-200 bg-white p-4 text-center shadow-sm">
      <div className="text-sm text-gray-500">{label}</div>
      <div className="mt-1 text-2xl font-semibold">{value ?? '—'}</div>
    </div>
  )
}

const STATS_POLL_INTERVAL_MS = 10000 // 상단 통계는 최소 10초마다 반드시 재동기화한다

export default function DashboardPage() {
  const [stats, setStats] = useState<DashboardStats>({ pods: null, traffic: 0, nodes: null })
  // 트래픽 관련 버튼을 누를 때마다 값을 바꿔서 TrafficHistoryChart가 폴링 주기를 안 기다리고 즉시 재조회하게 한다.
  const [trafficRefreshSignal, setTrafficRefreshSignal] = useState(0)

  const loadStats = () => {
    fetch(`${API_BASE}/dashboard/summary`)
      .then((res) => (res.ok ? res.json() : Promise.reject(new Error(`HTTP ${res.status}`))))
      .then((data: Partial<DashboardStats>) => {
        setStats({ pods: data.pods ?? null, traffic: data.traffic ?? 0, nodes: data.nodes ?? null })
      })
      .catch(() => {
        // 백엔드 미연결 상태 — 콘솔에 요청 실패가 보이는 게 정상. 연동되면 자동으로 채워짐.
      })
  }

  useEffect(() => {
    loadStats()
    const timer = setInterval(loadStats, STATS_POLL_INTERVAL_MS)
    return () => clearInterval(timer)
  }, [])

  // 버튼 클릭 직후 다음 폴링을 기다리지 않고 바로 재조회 — 눈에 보이는 반응 지연을 줄인다.
  // 트래픽 파이프라인(call-api flush 2초 + predict 집계 2초, 최악 4초)은 배치라 진짜 즉시는
  // 아니라서, 클릭 즉시 1번 + 배치가 한 바퀴 돌 시점(4.5초 뒤) 1번 더 재조회한다.
  const refreshTraffic = () => {
    loadStats()
    setTrafficRefreshSignal((n) => n + 1)
    setTimeout(() => {
      loadStats()
      setTrafficRefreshSignal((n) => n + 1)
    }, 4500)
  }
  const increaseTraffic = () =>
    fetch(`${SIMULATOR_BASE}/simulator/increase`, { method: 'POST' }).then(refreshTraffic).catch(() => {})
  const decreaseTraffic = () =>
    fetch(`${SIMULATOR_BASE}/simulator/decrease`, { method: 'POST' }).then(refreshTraffic).catch(() => {})
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
    }).then(refreshTraffic).catch(() => {})
  const reset = () => fetch(`${SIMULATOR_BASE}/simulator/reset`, { method: 'POST' }).then(refreshTraffic).catch(() => {})

  return (
    <div className="mx-auto flex max-w-6xl flex-col gap-6">
      <h1 className="text-xl font-semibold">대시보드 / 시뮬레이터</h1>

      <div className="flex gap-4">
        <StatTile label="파드 수" value={stats.pods} />
        <StatTile label="트래픽" value={stats.traffic} />
        <StatTile label="노드 수" value={stats.nodes} />
      </div>

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

      <div className="flex gap-4">
        <div className="flex-1">
          <div className="mb-2 text-center text-sm text-gray-500">트래픽 증감 그래프</div>
          <div className="h-72 rounded-lg border border-gray-200 bg-white p-2">
            <TrafficHistoryChart refreshSignal={trafficRefreshSignal} />
          </div>
        </div>
        <div className="flex-1">
          <div className="mb-2 text-center text-sm text-gray-500">파드수 그래프</div>
          <div className="h-72 rounded-lg border border-gray-200 bg-white p-2">
            <PodForecastChart />
          </div>
        </div>
      </div>

      <div className="h-96">
        <RdsTableViewer />
      </div>
    </div>
  )
}
