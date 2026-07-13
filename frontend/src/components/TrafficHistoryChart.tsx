import { useEffect, useState } from 'react'
import {
  CartesianGrid,
  Line,
  LineChart,
  ResponsiveContainer,
  Tooltip,
  XAxis,
  YAxis,
} from 'recharts'

// 백엔드 연동 지점 — predict가 call-api 각 파드의 10초 단위 shard(FileStore)를 모아
// 집계한 값이라, k6든 시뮬레이터든 트래픽 출처·call-api 파드 수와 무관하게 합산되어 나온다.
const API_BASE = import.meta.env.VITE_API_BASE_URL ?? ''

const WINDOW_MINUTES = 10   // 최근 몇 분을 보여줄지
const BUCKET_SECONDS = 10   // 버킷 크기 (k6 부하 테스트처럼 짧은 구간을 촘촘히 보기 위함)
const POLL_INTERVAL_MS = 5000   // 실시간처럼 보이도록 주기적으로 다시 불러온다

type TrafficPoint = { timestamp: string; requests: number }
type ChartPoint = { label: string; requests: number }

function formatLabel(timestamp: string): string {
  const date = new Date(timestamp)
  return date.toLocaleTimeString('ko-KR', { hour12: false, minute: '2-digit', second: '2-digit' })
}

export default function TrafficHistoryChart() {
  const [series, setSeries] = useState<ChartPoint[]>([])

  useEffect(() => {
    let cancelled = false

    const load = () => {
      fetch(
        `${API_BASE}/dashboard/traffic-history?minutes=${WINDOW_MINUTES}&bucket_seconds=${BUCKET_SECONDS}`,
      )
        .then((res) => (res.ok ? res.json() : Promise.reject(new Error(`HTTP ${res.status}`))))
        .then((data: TrafficPoint[]) => {
          if (cancelled) return
          setSeries(data.map((d) => ({ label: formatLabel(d.timestamp), requests: d.requests })))
        })
        .catch(() => {
          // 백엔드 미연결 상태 — 빈 그래프로 표시됨. 연동되면 자동으로 채워짐.
        })
    }

    load()
    const timer = setInterval(load, POLL_INTERVAL_MS)
    return () => {
      cancelled = true
      clearInterval(timer)
    }
  }, [])

  return (
    <ResponsiveContainer width="100%" height="100%">
      <LineChart data={series}>
        <CartesianGrid strokeDasharray="3 3" stroke="#e5e7eb" />
        <XAxis dataKey="label" tick={{ fontSize: 11 }} interval="preserveStartEnd" />
        <YAxis allowDecimals={false} tick={{ fontSize: 12 }} />
        <Tooltip />
        <Line
          type="monotone"
          dataKey="requests"
          name="요청 수"
          stroke="#a855f7"
          strokeWidth={2}
          dot={false}
          isAnimationActive={false}
        />
      </LineChart>
    </ResponsiveContainer>
  )
}
