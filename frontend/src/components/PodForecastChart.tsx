import { useEffect, useMemo, useState } from 'react'
import {
  Bar,
  BarChart,
  CartesianGrid,
  Legend,
  ReferenceLine,
  ResponsiveContainer,
  Tooltip,
  XAxis,
  YAxis,
} from 'recharts'

const HOURS_HISTORY = 24 // 슬라이드로 거슬러 볼 수 있는 과거 시간 범위
const HOURS_FORECAST = 5 // predict가 한 번에 내다보는 미래 시간 (predict/config.py prediction_horizon_steps와 일치)
const WINDOW_SIZE = 11 // 그래프에 한 번에 보이는 시간 폭 (기본값: 현재 기준 ±5시간)

// 백엔드 연동 지점. 요청/응답 형식은 frontend/BACKEND_INTEGRATION.md 참고.
// predict는 30분마다 계속 예측을 갱신한다(고정 동기화 시각 없음) — 과거/현재/미래 경계는 "정시" 하나뿐.
const API_BASE = import.meta.env.VITE_API_BASE_URL ?? ''

// 현재 "시" 정각으로 앵커를 고정한다 (분 단위가 섞이면 시간축 막대와 어긋남).
const currentHour = new Date()
currentHour.setMinutes(0, 0, 0)

type PodPoint = {
  offset: number
  label: string
  timestamp: string
  예측파드수?: number
  실제파드수?: number
}

// 시간축 뼈대만 미리 만들어두고, 값은 useEffect의 fetch가 채운다(TIME_SKELETON 참고 offset/timestamp로 매칭).
const TIME_SKELETON: PodPoint[] = Array.from({ length: HOURS_HISTORY + HOURS_FORECAST + 1 }, (_, i) => {
  const offset = i - HOURS_HISTORY
  const date = new Date(currentHour.getTime() + offset * 3600_000)
  return { offset, label: `${date.getHours()}시`, timestamp: date.toISOString() }
})

const WINDOW_START_MIN = -HOURS_HISTORY
const WINDOW_START_MAX = HOURS_FORECAST - WINDOW_SIZE + 1 // 기본값: 현재 기준 -5h ~ +5h

export default function PodForecastChart() {
  const [windowStart, setWindowStart] = useState(WINDOW_START_MAX)
  const [series, setSeries] = useState<PodPoint[]>(TIME_SKELETON)

  useEffect(() => {
    fetch(`${API_BASE}/dashboard/pod-forecast?hours_history=${HOURS_HISTORY}&hours_forecast=${HOURS_FORECAST}`)
      .then((res) => res.json())
      .then((data: { timestamp: string; predicted?: number; actual?: number }[]) => {
        const byTime = new Map(data.map((d) => [d.timestamp, d]))
        setSeries(
          TIME_SKELETON.map((point) => {
            const match = byTime.get(point.timestamp)
            return { ...point, 예측파드수: match?.predicted, 실제파드수: match?.actual }
          }),
        )
      })
      .catch(() => {
        // 백엔드 미연결 상태 — 빈 그래프로 표시됨. 연동되면 자동으로 채워짐.
      })
  }, [])

  const visible = useMemo(
    () => series.filter((d) => d.offset >= windowStart && d.offset < windowStart + WINDOW_SIZE),
    [series, windowStart],
  )
  const nowPoint = visible.find((d) => d.offset === 0)

  return (
    <div className="flex h-full flex-col gap-2">
      <div className="min-h-0 flex-1">
        <ResponsiveContainer width="100%" height="100%">
          <BarChart data={visible}>
            <CartesianGrid strokeDasharray="3 3" stroke="#e5e7eb" />
            <XAxis dataKey="label" tick={{ fontSize: 12 }} />
            <YAxis allowDecimals={false} tick={{ fontSize: 12 }} />
            <Tooltip />
            <Legend />
            {nowPoint && (
              <ReferenceLine
                x={nowPoint.label}
                stroke="#6b7280"
                strokeDasharray="4 4"
                label={{ value: '현재', position: 'insideTopLeft', fontSize: 11, fill: '#6b7280' }}
              />
            )}
            <Bar dataKey="예측파드수" fill="#a855f7" isAnimationActive={false} />
            <Bar dataKey="실제파드수" fill="#f97316" isAnimationActive={false} />
          </BarChart>
        </ResponsiveContainer>
      </div>

      <div className="flex items-center gap-2 px-1">
        <span className="text-xs text-gray-400">{WINDOW_START_MIN}h</span>
        <input
          type="range"
          min={WINDOW_START_MIN}
          max={WINDOW_START_MAX}
          value={windowStart}
          onChange={(e) => setWindowStart(Number(e.target.value))}
          className="flex-1 accent-purple-500"
        />
        <span className="text-xs text-gray-400">+{HOURS_FORECAST}h</span>
      </div>
    </div>
  )
}
