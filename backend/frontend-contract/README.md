# frontend-contract/

백엔드 재설계 전, 프론트엔드가 실제로 의존하는 백엔드 API 표면을 원본 서비스에서
임시로 격리해뒀던 곳. **재설계가 모두 끝나서 전부 원본 서비스에 다시 연결되고
지워졌다** — 아래는 이력 기록용.

## 복원 완료 (여기서 지움, 원본 서비스에 다시 연결됨)

| 엔드포인트 | 원래 있던 곳 | 복원한 재설계 항목 |
|---|---|---|
| `GET /dashboard/traffic-history`, `GET /dashboard/pod-forecast` | predict/routers/dashboard_router.py | H (DB → FileStore) |
| `POST /call`, `GET /call/{id}` | call-api/routers/call_router.py | B (스키마 단순화 + DB 제거) |
| `POST /simulator/start·stop·increase·decrease·reset`, `GET /simulator/status` | simulator/routers/simulator_router.py | D2 (계약 그대로 유지 확정) |

## 프론트가 부르지만 백엔드에 대응 구현이 없던 경로 (스텁, 최신 상태)

- `GET /api/dashboard/stats` → `GET /dashboard/summary`로 구현됨(H) — `{pods, traffic,
  nodes}`, 노드 수는 여전히 데이터 소스 없음(C8, 보류)
- `POST /api/simulator/traffic/increase` → `POST /simulator/increase`
- `POST /api/simulator/traffic/decrease` → `POST /simulator/decrease`
- `POST /api/simulator/sqs-inject` → 대응 없음, 가장 가까운 건 call-api의 `POST /call`
- `POST /api/simulator/reset` → `POST /simulator/reset`
- `POST /api/call` → `POST /call`로 스키마까지 정확히 일치하게 정리됨(B1) —
  `{ user_id, pickup: string, destination: string, requested_at?, source }`

프론트(`DashboardPage.tsx`/`ServicePage.tsx`)가 여전히 옛 스텁 경로를 호출하고
있다면, 위 표의 실제 경로로 바꿔주는 작업은 이번 백엔드 재설계 범위 밖이라 별도로
남아있다.
