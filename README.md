# project3-hailcast-app

hailcast 앱·AI 소스 · 담당: 그룹 B (이창원·양재혁)

AI 기반 **예측형 택시 호출 플랫폼 Backend** — 수요를 미리 예측해 트래픽이 오기 전에 Worker Pod를 늘리고(예측 선제),
실측 유입이 예측을 넘으면 곧바로 한 칸 더 올린다(반응형 보정). 두 신호가 **KEDA `minReplicaCount` 하나**로 합쳐진다.

```
Simulator(k6) ─▶ Call API ─▶ SQS ─▶ Worker ─▶ RDS
     │                │                          
     │                └─(파드별 유입 shard)─▶ FileStore(traffic.json) ─┐
     │                                                                 ▼
Weather(Open-Meteo, 4h) ─▶ FileStore(weather CSV) ─▶ Forecast Scheduler(4h) ─▶ LightGBM
                                                            │                     │
                                                            ▼                     ▼
                                              FileStore(predictions latest.json/csv)
                                                            │
                                          Scaling Scheduler(60s): 예측 baseline + 반응형 워터마크
                                                            │
                                          KEDA minReplicaCount Patch ─▶ Worker Pod Scaling
                                                            │
                                              Dashboard API ─▶ Frontend(React/Vite)
```

## 프로젝트 구조 (backend 폴더 = 파드 단위)

```
backend/
  common/            공통 패키지 (모든 이미지에 COPY) — core(logger·settings·exceptions·scheduler·
                     metrics·store·constants·cors), aws(sqs/s3/dynamodb adapter), db(entities·repository·
                     session), models(DTO)
  call-api/    :8000 콜 접수(빠름) — Router→Service→SQS Adapter, 즉시 202 + 파드별 유입 집계(A1) flush
  worker/            SQS Long Polling 소비 → RDS 저장 (KEDA 스케일 대상)
  simulator/   :8001 Traffic Engine — start/stop/increase/decrease/reset/burst, k6로 실부하 생성
  weather-cron :8002 Open-Meteo 수집 Scheduler + 조회 API (CronJob 모드: fetch.py --once)
  predict/     :8003 Forecast·Scaling·Backup·Traffic·Accuracy-check 스케줄러 + Prediction/Scaling/Dashboard/Health API
  frontend-contract/ 프론트↔백 응답 계약 문서
frontend/            React/Vite 대시보드·시뮬레이터 UI (nginx 서빙)
ml/                  오프라인 학습(LightGBM→S3) + 재학습 CronJob 엔트리(retrain_trigger.py, 오답노트 이어학습) +
                     전처리·배치예측 + 학습·서빙 공유 피처(features.py)
k8s/                 배포 계약 예시 manifest (실 배포는 인프라 레포 · GitOps)
scripts/ · Makefile  로컬 docker compose 관리 + ECR build/push (자세히: scripts/README.md)
.github/workflows/   CI — 변경 서비스만 빌드 → ECR push → manifests 이미지 태그 자동 갱신
```

각 서비스 내부는 **Router → Service → Repository → DB** 레이어, AWS/K8s 접근은 **Adapter**로만.
DB를 두지 않는 JSON/CSV 상태(예측·트래픽·시뮬레이터 상태)는 **FileStore**(로컬 파일 또는 S3, `JSON_STORE_BACKEND`)로 파드 간 공유한다.

## 원칙

빌드→ECR push→EKS pull. AI는 LightGBM까지. 설정은 전부 환경변수(매직넘버 금지). print() 금지(공통 JSON Logger).
Secret은 코드에 하드코딩하지 않는다 — 운영은 IRSA + K8s Secret(ESO). 배포는 GitOps(ArgoCD)가 공식 경로다.

## 실행 방법 (로컬)

`make` 진입점을 쓴다(AWS 자격증명 불필요 · postgres + LocalStack + 서비스 5종 자동 기동).

```bash
make dev-up                        # 전체 빌드 + 기동 (docker compose)
make dev-train                     # LightGBM 학습 → FileStore (최초 1회, --bootstrap 합성 데이터)
make dev-logs SVC=predict          # 특정 서비스 로그 팔로우
make dev-down                      # 중지 (DB 볼륨 유지) / make dev-clean 은 볼륨까지 삭제

# 데모: Simulator 버튼 → 전체 플로우
curl -X POST localhost:8001/api/simulator/increase   # TPS +TRAFFIC_STEP(기본 500)
curl -X POST localhost:8001/api/simulator/start      # k6 실부하 시작
curl -X POST 'localhost:8001/api/simulator/burst?count=10000'  # 큐 순간 적체 → 반응형 스케일 트리거
curl localhost:8003/api/dashboard/summary            # 전체 상태 한 번에
```

`make dev-up` 뒤 로컬 엔드포인트: call-api `:8000` · simulator `:8001` · weather-cron `:8002` · predict `:8003`.
전체 명령·설계 원칙은 [scripts/README.md](scripts/README.md).

## 배포 (CI/CD)

**이미지 build→ECR push 는 GitHub Actions([.github/workflows/build.yml](.github/workflows/build.yml))가 담당한다.**
`dev`/`main` push 시 **변경된 서비스만** 감지해 빌드하고(SHA + latest 태그), OIDC(AssumeRole)로 ECR에 올린 뒤
manifests 레포의 **실제로 빌드된 서비스** 이미지 태그만 갱신한다 → ArgoCD가 EKS에 반영(GitOps).
`make build-push`/`make deploy-all` 은 **로컬 수동·디버깅용**이며 운영 배포의 공식 경로가 아니다(계정 가드 선행).
재학습(`ml/retrain_trigger.py`)은 predict 이미지를 그대로 재사용하는 별도 K8s CronJob(`predict-retraining`,
매일 03:00 KST, `retraining-sa` 전용 IRSA)으로 배포된다 — predict 배포와 이미지 태그가 항상 같이 갱신된다.

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
| simulator | `POST /api/simulator/start·stop·increase·decrease·reset` | k6 Traffic 제어 (TPS 즉시 반영) |
| | `POST /api/simulator/burst?count=N` | N건 순간 발사 → 큐 적체로 반응형 스케일 확실 트리거 |
| | `GET /api/simulator/status` | TPS·통계 (Frontend 폴링) |
| weather-cron | `GET /weather/status` | 최근 수집 상태·last_error (ALB 미노출 · 접두어 없음) |
| predict | `GET /api/prediction/latest` `/api/prediction/status` | 예측 조회 |
| | `GET /api/scaling/status` `/api/scaling/current` | 스케일링 상태·현재 결정 |
| | `GET /api/dashboard/summary` `/api/dashboard/traffic-history` `/api/dashboard/pod-forecast` | 통합 Dashboard |
| | `GET /health` `/ready` `/live` `/metrics` | 상태·Probe·Prometheus (루트 유지) |
| 공통 | `GET /healthz` | 서비스별 기본 헬스체크 (루트 유지) |

## Scheduler (공통 베이스: backend/common/core/scheduler.py — 실패해도 다음 주기 정상 대기)

| Scheduler | 파드 | 주기 (env·기본) | 역할 |
|---|---|---|---|
| weather_scheduler | weather-cron | `WEATHER_INTERVAL_SECONDS`=4h | Open-Meteo → FileStore(weather CSV) |
| forecast_scheduler | predict | `PREDICTION_INTERVAL_SECONDS`=4h (+3분 정렬) | 모델+날씨+콜이력 → predictions latest.json/csv |
| scaling_scheduler | predict | `SCALING_INTERVAL_SECONDS`=60s | 예측 baseline + 반응형 워터마크 → KEDA Patch |
| traffic_scheduler | predict | `TRAFFIC_AGGREGATE_INTERVAL_SECONDS`=2s | call-api 파드별 shard 합산(A1) → traffic.json |
| backup_scheduler | predict | `BACKUP_INTERVAL_SECONDS`=1h | 정시 버킷 파드 이력 스냅샷 (예측-실제 그래프용) |
| accuracy_check_scheduler | predict | `ACCURACY_CHECK_INTERVAL_SECONDS`=1h (매시 :59분 정렬) | 예측 vs 실측 대조 → 오답노트(DynamoDB) 기록. 재학습 파이프라인 입력(아래 참고) |
| traffic_flush_scheduler | call-api | `TRAFFIC_FLUSH_INTERVAL_SECONDS`=2s | 이 파드 유입 카운트를 FileStore shard로 flush |
| status_scheduler | simulator | `STATUS_WRITE_INTERVAL_SECONDS`=2s | 시뮬레이터 상태를 FileStore(status.json)로 기록 |

forecast는 weather-cron과 같은 4시간 주기지만 **3분 늦춰 정렬**(00:03/04:03/…)한다 — 날씨가 그 주기 :00에 먼저 갱신돼야 최신 입력을 쓴다.

## Prediction (Forecast Pipeline)

S3 latest 모델 로드(버전 캐시, 재학습 자동 반영) → 뉴욕 날씨(FileStore CSV)+최근 콜이력 →
`ml/features.py` 공유 피처(train-serve skew 방지) → LightGBM → **뉴욕 날씨 기반 글로벌 수요 × 4시간(1시간 버킷)** 예측 →
FileStore `predictions/latest.json`(+ latest.csv + 이력). `predicted_taxi_demand`가 Scaling 기준값이다.

## Predictive Scaling (2계층 · 결과는 KEDA `minReplicaCount` 하나로 합류)

Prediction Reader(Schema·신선도 검증) → **Scaling Decision Engine** →
KEDA Adapter가 ScaledObject **`minReplicaCount`만** Patch (Deployment 직접 수정 금지). Scale Up 즉시 /
Down은 `SCALING_COOLDOWN_SECONDS`(기본 300s) 유예. 예측 없음·비정상·`PREDICTION_MAX_AGE_SECONDS`(4h) 초과 시 스킵.

- **① 예측 baseline** — 예측 수요 ÷ `SCALING_DEMAND_PER_POD`(파드 1개 감당량, 기본 500) + `SCALING_BUFFER_PODS`(n+1 여유).
  `SCALING_MIN_REPLICAS`~`SCALING_MAX_REPLICAS`(1~10)로 clamp.
- **② 반응형 보정** — A1 트래픽 집계(traffic.json)로 실측 유입/현재 용량 비율을 보고,
  `SCALING_WATERMARK_HIGH`(0.8) 이상이면 +`SCALING_REACTIVE_STEP`, `SCALING_WATERMARK_LOW`(0.4) 이하로 내려가야 해제.
  트래픽 집계가 아직 없으면 이 레이어는 자동 비활성(예측 baseline만 사용).

로컬은 `KEDA_ENABLED=false`(dry-run InMemory Adapter). 큐 길이 기반 KEDA SQS 트리거(즉시 반응)와
predict의 `minReplicaCount` Patch(예측 선제)가 **같은 ScaledObject에서 함께** 동작한다.

## 재학습 파이프라인 (오답노트 → 이어학습)

예측이 크게 틀린 사례(실측이 예측을 초과)를 자동으로 모아뒀다가, 일정량 쌓이면 원본 데이터 없이
기존 모델에 그 사례만 추가로 학습시킨다. 원본 학습 CSV(`ml/data/`)는 `.gitignore` 대상이라 어떤
배포 이미지에도 없어서(로컬 전용), from-scratch 재학습은 배포 환경에서 애초에 불가능 — 그래서
"이미 학습된 모델 + 오답노트만으로 이어서 학습"하는 방식을 쓴다.

1. **오답노트 기록** — `accuracy_check_scheduler`(매시 :59분)가 그 시간의 예측(`predicted_demand`)과
   실측(`actual_demand`, traffic.json 기준)을 대조. **실측이 예측을 초과하고** 오차비율이
   `PREDICTION_ACCURACY_ERROR_RATIO_THRESHOLD`(기본 0.3) 이상이면 DynamoDB(`hailcast-dev-prediction-log`)에
   학습 데이터와 동일한 스키마(날짜·요일·온도·습도·강수유무·승객수)로 기록. 과대예측(비용 손해일 뿐 서비스
   위험 아님)은 기록 대상이 아니다.
2. **재학습 트리거** — `ml/retrain_trigger.py`가 학습 미사용(`학습여부=0`) 건수를 확인, `MIN_RECORDS_FOR_TRAINING`(20)건
   이상이면 이어학습 진행. K8s CronJob(`predict-retraining`, 매일 03:00 KST, `retraining-sa` 전용 IRSA —
   predict-sa와 분리, `backoffLimit: 0`)로 배포된다. 수동 실행 시 `--yes`(비대화형 확인 스킵) 필수,
   `--force`는 임계값 미만이어도 강행(파이프라인 검증용, 과적합 위험 있음).
3. **이어학습** — LightGBM `init_model`로 S3 기존 모델 위에 소수의 트리(`CONTINUED_N_ESTIMATORS`=30)만 추가.
   소량 배치 특성상 `min_data_in_leaf`도 원본(20)보다 낮춘 `CONTINUED_MIN_DATA_IN_LEAF`(8)를 이어학습 전용으로 씀
   — 그대로 물려받으면 스플릿 자체가 불가능해서 트리가 하나도 안 늘어나는 조용한 실패가 났던 이력이 있다.
4. **결과 검증** — 이어학습 전후 트리 수를 비교해서 늘지 않았으면 `RuntimeError`로 Job을 실패시킨다.
   "fit() 성공"이 "실제로 학습됨"을 보장하지 않는다는 걸 라이브 검증으로 확인했기 때문 — `backoffLimit: 0` +
   `KubeJobFailed` 경보(인프라)로 실패가 조용히 묻히지 않게 한다.
5. **재사용 방지** — 학습에 쓴 레코드는 삭제하지 않고 `학습여부`만 0→1로 마킹(UpdateItem, 감사·재현용 보존).
   MAE/RMSE는 S3 `metadata.json`에 함께 업로드(Grafana 관측용, in-sample 지표 — 일반화 성능이 아니라 회차 간 추세용).

## Simulator

실서비스와 동일한 `CallRequest` 모델로 현실적인 트래픽을 **k6**로 생성한다(좌표·zone_id 없는 단일 페이로드, B1).
TPS 변경(`TRAFFIC_STEP` 단위)은 즉시 반영, `MIN_TPS`=0(정지)~`MAX_TPS`=600. `burst`는 큐를 순간적으로
채워 반응형 스케일링을 확실히 트리거하기 위한 버튼(기본 10000건). 상태는 FileStore(status.json)로 대시보드와 공유.

## Dashboard

`GET /api/dashboard/summary` 하나로 traffic(Simulator 상태)·prediction·weather·scaling·worker(큐 적체/처리량/지연)·
node(K8s 노드 수)·health 전체 반환. 부분 장애 시 해당 위젯만 `available:false`.
`traffic-history`(유입 추이)·`pod-forecast`(예측 vs 실제 파드 수) 그래프용 시계열도 별도 제공.

## 환경 변수 (주요 — 전체는 backend/common/core/settings.py + 서비스별 config.py)

| 그룹 | 변수 |
|---|---|
| AWS/Store | `AWS_REGION` `AWS_ENDPOINT_URL`(LocalStack) `S3_BUCKET` `JSON_STORE_BACKEND`(local\|s3) `JSON_STORE_LOCAL_DIR` |
| Queue | `SQS_QUEUE_NAME` `SQS_QUEUE_URL` `SQS_BATCH_SIZE` `SQS_LONG_POLL_SECONDS` `SQS_VISIBILITY_TIMEOUT` `SQS_RETRY_COUNT` |
| DB (RDS) | `DB_HOST/PORT/NAME/USER/PASSWORD` |
| Weather | `WEATHER_API_URL` `WEATHER_INTERVAL_SECONDS` `WEATHER_FORECAST_HOURS` `WEATHER_RETRY_COUNT` |
| Prediction | `PREDICTION_INTERVAL_SECONDS` `PREDICTION_ALIGN_OFFSET_SECONDS` `PREDICTION_WINDOW_MINUTES` `PREDICTION_HORIZON_HOURS` `MODEL_S3_PREFIX` `PREDICTION_S3_PREFIX` `FORECAST_RETRY_COUNT` |
| Scaling (예측) | `SCALING_INTERVAL_SECONDS` `SCALING_COOLDOWN_SECONDS` `SCALING_DEMAND_PER_POD` `SCALING_BUFFER_PODS` `SCALING_MIN/MAX_REPLICAS` `PREDICTION_MAX_AGE_SECONDS` |
| Scaling (반응형/KEDA) | `TRAFFIC_AGGREGATE_INTERVAL_SECONDS` `SCALING_WATERMARK_HIGH/LOW` `SCALING_REACTIVE_STEP` `KEDA_ENABLED` `KEDA_NAMESPACE` `KEDA_SCALEDOBJECT_NAME` `WORKER_DEPLOYMENT_NAME` |
| Traffic(sim)/call-api | `CALL_API_URL` `TRAFFIC_STEP` `MIN_TPS` `MAX_TPS` `BURST_DEFAULT_COUNT` `TRAFFIC_FLUSH_INTERVAL_SECONDS` |
| Dashboard | `K8S_NODES_ENABLED` `K8S_NODES_STUB_COUNT` `HEALTH_QUEUE_BACKLOG_WARNING` `BACKUP_INTERVAL_SECONDS` |
| 오답노트/재학습 | `PREDICTION_ACCURACY_LOG_ENABLED` `PREDICTION_ACCURACY_TABLE_NAME` `PREDICTION_ACCURACY_ERROR_RATIO_THRESHOLD` `ACCURACY_CHECK_INTERVAL_SECONDS` `ML_S3_UPLOAD_ENABLED`(명시적으로 켜야 재학습 결과가 S3에 반영됨) |
| 기타 | `LOG_LEVEL` `CORS_ALLOW_ORIGINS` |

Secret은 코드에 하드코딩하지 않는다 — 로컬 compose의 `test`/`hailcast`는 LocalStack/로컬 DB 전용 더미값, 운영은 IRSA + K8s Secret(ESO).

## Troubleshooting

| 증상 | 확인 |
|---|---|
| `/ready` 503 | `make dev-train` 실행했는지 (model check) · DB/LocalStack healthy 여부 |
| 예측이 안 생김 | `GET /api/prediction/status`의 `last_error` · FileStore `models/latest/` 존재 여부 |
| 콜이 DB에 안 쌓임 | worker 로그 `worker_fail` · `GET /api/dashboard/summary`의 worker.queue_backlog |
| Scaling 안 됨 | `GET /api/scaling/status` — prediction 나이(`PREDICTION_MAX_AGE_SECONDS` 초과?) · cooldown 잔여 · `KEDA_ENABLED` |
| 반응형이 안 붙음 | traffic.json 집계 유무 — call-api flush(2s)와 predict 집계(2s) 둘 다 도는지 · 워터마크(0.8/0.4) 도달 여부 |
| 날씨 수집 실패 | `GET /weather/status`의 `last_error` (Open-Meteo 재시도 3회 후 다음 주기 재시도) |
| 큐가 계속 쌓임 | worker 수 부족 — KEDA(운영) 또는 `docker compose up -d --scale worker=3`(로컬) |
| 오답노트가 안 쌓임 | `PREDICTION_ACCURACY_LOG_ENABLED` 켜져 있는지 · 실측이 예측을 초과한 사례가 실제로 있었는지(과대예측은 기록 대상 아님) |
| 재학습 CronJob 실패 | `kubectl logs job/predict-retraining-*` — `RuntimeError`면 이어학습 트리 수가 안 늘어난 것(배치가 너무 작을 때 의도된 실패) |
