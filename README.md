# project3-hailcast-app

hailcast 앱·AI 소스 · 담당: 그룹 B (이창원·양재혁)

AI 기반 **예측형 택시 호출 플랫폼 Backend** — 수요를 미리 예측해 트래픽이 오기 전에 Worker Pod를 늘린다(Predictive Scaling).

```
Simulator → Call API → SQS → Worker → RDS
                                   ↘ Weather(Open-Meteo) ↘
                          Forecast Scheduler → LightGBM → prediction.json(S3)
                                   → Scaling Scheduler → KEDA minReplicaCount Patch → Pod Scaling
                                   → Dashboard API (통합 조회)
```

## 프로젝트 구조 (폴더 = 파드 단위)

```
backend/
  common/           공통 패키지 (모든 이미지에 COPY) — core(logger·settings·exceptions·scheduler·metrics),
                    aws(sqs/s3 adapter), db(entities·session), models(DTO)
  call-api/   :8000 콜 접수(빠름) — Router→Service→SQS Adapter, 즉시 202
  worker/           SQS Long Polling 소비 → RDS 저장 (KEDA 스케일 대상)
  simulator/  :8001 Traffic Engine — start/stop/increase/decrease/reset, TPS 즉시 반영
  weather-cron:8002 Open-Meteo 수집 Scheduler + 조회 API (CronJob 모드: --once)
  predict/    :8003 Forecast·Scaling 스케줄러 + Prediction/Scaling/Dashboard/Health API
frontend/           React/Vite 대시보드·시뮬레이터 UI
ml/                 오프라인 학습(LightGBM→S3) + 학습·서빙 공유 피처(features.py)
k8s/                배포 계약 예시 manifest (실 배포는 인프라 레포)
```

각 서비스 내부는 **Router → Service → Repository → DB** 레이어, AWS/K8s 접근은 **Adapter**로만.

## 원칙

빌드→ECR push→EKS pull. AI는 LightGBM까지. 설정은 전부 환경변수. print() 금지(공통 JSON Logger).

## 실행 방법 (로컬)

```bash
docker compose up --build          # postgres + localstack + 전 서비스
docker compose run --rm ml-train   # LightGBM 학습 → S3 (최초 1회, --bootstrap 합성 데이터)

# 데모: Simulator 버튼 → 전체 플로우
curl -X POST localhost:8001/api/simulator/increase   # TPS +5
curl -X POST localhost:8001/api/simulator/start
curl localhost:8003/api/dashboard/summary            # 전체 상태 한 번에
```

## API 목록

경로 규칙(7/23 팀 결정 · 「나」안): **외부에 노출되는 API 는 전부 `/api` 아래**에 있다.
ALB 가 `/api/*` 를 백엔드로, 나머지 `/*` 를 frontend 로 보낸다. 접두어는 각 서비스
Entry Point(`app.include_router(..., prefix="/api")`)에서 붙는다.
**Probe·모니터링 경로(`/healthz` `/health` `/ready` `/live` `/metrics`)는 루트에 남는다** —
k8s Probe 와 ALB healthcheck-path 가 이 경로를 직접 보기 때문이다.

| 서비스 | Endpoint | 설명 |
|---|---|---|
| call-api | `POST /api/call` | 콜 접수 → SQS → 즉시 202 (request_id) |
| | `GET /api/call/{id}` | 처리 상태 조회 |
| | `GET /api/calls/recent` | 최근 콜 목록 (RDS 테이블 뷰어) |
| simulator | `POST /api/simulator/start·stop·increase·decrease·reset` | Traffic 제어 |
| | `GET /api/simulator/status` | TPS·통계 (Frontend 폴링) |
| weather-cron | `GET /weather/latest·history·status` | 날씨 조회 (ALB 미노출 · 접두어 없음) |
| predict | `GET /api/prediction/latest·history·status` | 예측 조회 |
| | `GET /api/scaling/status·history·current` | 스케일링 조회 |
| | `GET /api/dashboard/summary·traffic·prediction·weather·scaling·worker` | 통합 Dashboard |
| | `GET /health` `/ready` `/live` `/metrics` | 상태·Probe·Prometheus (루트 유지) |
| 공통 | `GET /healthz` | 서비스별 기본 헬스체크 (루트 유지) |

## Scheduler (공통 베이스: backend/common/core/scheduler.py — 실패해도 다음 주기 정상 대기)

| Scheduler | 파드 | 주기 (env) | 역할 |
|---|---|---|---|
| weather_scheduler | weather-cron | `WEATHER_INTERVAL_SECONDS`=600 | Open-Meteo → RDS (Upsert) |
| forecast_scheduler | predict | `PREDICTION_INTERVAL_SECONDS`=1800 | 모델+날씨+콜이력 → prediction.json(S3)+DB |
| scaling_scheduler | predict | `SCALING_INTERVAL_SECONDS`=60 | prediction.json → KEDA Patch |
| traffic_scheduler | simulator | tick 0.2s | TPS 기반 Call API 발사 |
| backup_scheduler | predict | (Stub) | 백업 예약분 |

## Prediction (Forecast Pipeline)

S3 latest 모델 로드(버전 캐시, 재학습 자동 반영) → 구역별 최신 날씨+최근 콜(1h/3h/24h) →
`ml/features.py` 공유 피처 17개(train-serve skew 방지) → LightGBM → 9구역×3시간창 예측 →
S3 `predictions/latest.json`. `predicted_taxi_demand`가 Scaling 기준값.

## Predictive Scaling

Prediction Reader(S3, Schema 검증) → **Decision Engine**(`SCALING_RULES="20:1,50:2,100:3,300:5,500:10"`)
→ KEDA Adapter가 ScaledObject **minReplicaCount만** Patch (Deployment 직접 수정 금지).
Scale Up 즉시 / Down은 `SCALING_COOLDOWN_SECONDS` 유예. 예측 없음·비정상·만료 시 스킵.
로컬은 `KEDA_ENABLED=false`(dry-run InMemory Adapter).

## Simulator

실서비스와 동일한 `CallRequest` 모델로 서울 9개 구역 가중치 기반 현실적 트래픽 생성.
TPS 변경은 Generator 재생성 없이 즉시 반영, Call API 장애에도 Generator 생존.

## Dashboard

`GET /api/dashboard/summary` 하나로 traffic(Simulator 프록시)·prediction·weather·scaling·worker(큐 적체/처리량/지연)·health 전체 반환. 부분 장애 시 해당 위젯만 `available:false`.

## 환경 변수 (주요 — 전체는 backend/common/core/settings.py + 서비스별 config.py)

| 그룹 | 변수 |
|---|---|
| AWS | `AWS_REGION` `AWS_ENDPOINT_URL`(LocalStack) `S3_BUCKET` |
| Queue | `SQS_QUEUE_NAME` `SQS_QUEUE_URL` `SQS_BATCH_SIZE` `SQS_LONG_POLL_SECONDS` `SQS_VISIBILITY_TIMEOUT` `SQS_RETRY_COUNT` |
| DB | `DB_HOST/PORT/NAME/USER/PASSWORD` 또는 `DB_URL` |
| Weather | `WEATHER_API_URL` `WEATHER_INTERVAL_SECONDS` `WEATHER_RETRY_COUNT` `WEATHER_LOCATIONS` |
| Prediction | `PREDICTION_INTERVAL_SECONDS` `PREDICTION_WINDOW_MINUTES` `PREDICTION_HORIZON_STEPS` `MODEL_S3_PREFIX` `PREDICTION_S3_PREFIX` `FORECAST_RETRY_COUNT` |
| Scaling | `SCALING_INTERVAL_SECONDS` `SCALING_COOLDOWN_SECONDS` `SCALING_RULES` `SCALING_MIN/MAX_REPLICAS` `PREDICTION_MAX_AGE_SECONDS` `KEDA_ENABLED` `KEDA_NAMESPACE` `KEDA_SCALEDOBJECT_NAME` |
| Traffic | `CALL_API_URL` `TRAFFIC_STEP` `MIN_TPS` `MAX_TPS` `GENERATOR_TICK_SECONDS` |
| 기타 | `LOG_LEVEL` `SIMULATOR_URL` (dashboard 프록시) |

Secret은 코드에 하드코딩하지 않는다 — 로컬 compose의 `test`/`hailcast`는 LocalStack/로컬 DB 전용 더미값, 운영은 IRSA + K8s Secret.

## Troubleshooting

| 증상 | 확인 |
|---|---|
| `/ready` 503 | `docker compose run --rm ml-train` 실행했는지 (model check) · DB/LocalStack healthy 여부 |
| 예측이 안 생김 | `GET /api/prediction/status`의 `last_error` · S3 `models/latest/` 존재 여부 |
| 콜이 DB에 안 쌓임 | worker 로그 `worker_fail` · `GET /api/dashboard/worker`의 queue_backlog |
| Scaling 안 됨 | `GET /api/scaling/status` — prediction 나이(`PREDICTION_MAX_AGE_SECONDS` 초과?) · cooldown 잔여 |
| 날씨 수집 실패 | `GET /weather/status`의 `last_error` (Open-Meteo 재시도 3회 후 다음 주기 재시도) |
| 큐가 계속 쌓임 | worker 프로세스 수 부족 — KEDA(운영) 또는 `docker compose up -d --scale worker=3`(로컬) |
