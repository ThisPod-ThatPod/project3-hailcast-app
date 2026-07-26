import { useEffect, useState } from 'react'
import { nycHourLabel } from '../lib/time'

// PodForecastChart와 같은 base — /api 접두어는 경로에 둔다(7/23 「나」안, DashboardPage 참고).
const API_BASE = import.meta.env.VITE_API_BASE_URL ?? ''
const POLL_INTERVAL_MS = 60000 // predict가 4시간 주기로만 갱신하므로 짧게 돌 필요 없음

type PredictionItem = {
  target_time: string
  temperature: number | null
  humidity: number | null
  is_raining: boolean | null
}

type WeatherPoint = {
  hour: string
  temperature: number | null
  humidity: number | null
  isRaining: boolean | null
}

export default function WeatherStrip() {
  const [points, setPoints] = useState<WeatherPoint[]>([])

  useEffect(() => {
    const load = () => {
      fetch(`${API_BASE}/api/prediction/latest`)
        .then((res) => (res.ok ? res.json() : Promise.reject(new Error(`HTTP ${res.status}`))))
        .then((doc: { predictions: PredictionItem[] }) => {
          setPoints(
            (doc.predictions ?? []).map((p) => ({
              hour: nycHourLabel(new Date(p.target_time)),
              temperature: p.temperature,
              humidity: p.humidity,
              isRaining: p.is_raining,
            })),
          )
        })
        .catch(() => {
          // predict 미연결/예측 없음 — 빈 스트립으로 표시됨. 연동되면 자동으로 채워짐.
        })
    }
    load()
    const timer = setInterval(load, POLL_INTERVAL_MS)
    return () => clearInterval(timer)
  }, [])

  if (points.length === 0) return null

  return (
    <div className="mb-2 flex gap-2 overflow-x-auto pb-1">
      {points.map((p, i) => (
        <div
          key={i}
          className="flex min-w-[60px] flex-col items-center gap-0.5 rounded-md border border-gray-200 bg-gray-50 px-2 py-1 text-xs"
        >
          <span className="font-medium text-gray-600">{p.hour}</span>
          <span>{p.isRaining ? '🌧️' : '☀️'}</span>
          <span className="text-gray-700">{p.temperature != null ? `${p.temperature.toFixed(0)}°` : '—'}</span>
          <span className="text-gray-400">{p.humidity != null ? `${p.humidity.toFixed(0)}%` : '—'}</span>
        </div>
      ))}
    </div>
  )
}
