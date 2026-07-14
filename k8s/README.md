# Kubernetes 배포 가이드 (참고용 예시 Manifest)

> 실제 Manifest·Terraform은 인프라 레포(그룹 A) 소관입니다.
> 이 디렉토리는 **앱이 기대하는 배포 계약**(이미지·포트·Probe·환경변수·RBAC)을 예시로 문서화합니다.

## 배포 단위 (폴더 = 파드)

| 서비스 | 형태 | 포트 | Probe |
|---|---|---|---|
| call-api | Deployment (+HPA/고정) | 8000 | `/healthz` |
| worker | Deployment (**KEDA 대상**) | - | 프로세스 생존 |
| simulator | Deployment (1 replica) | 8001 | `/healthz` |
| weather-cron | Deployment(수집+API) 또는 CronJob(`python fetch.py --once`) | 8002 | `/healthz` |
| predict | Deployment (1 replica — 스케줄러 중복 실행 방지) | 8003 | liveness `/live`, readiness `/ready` |

## 필수 구성

1. **ConfigMap**: 비밀 아닌 환경변수 (큐 이름, 주기, Scaling Rule 등 — [../README.md](../README.md) 환경변수 표 참고)
2. **Secret**: `DB_PASSWORD` (RDS), AWS 자격은 **IRSA**(ServiceAccount) 사용 — AWS 키를 Secret에 넣지 않는다
3. **worker ScaledObject**: [worker-scaledobject.yaml](worker-scaledobject.yaml) — SQS 큐 길이(반응) + predict의 minReplicaCount Patch(예측 선제)가 함께 동작
4. **predict RBAC**: [predict-rbac.yaml](predict-rbac.yaml) — ScaledObject get/patch 권한 + `KEDA_ENABLED=true`
5. **predict Probe**: [predict-deployment.yaml](predict-deployment.yaml) 참고 (liveness=/live, readiness=/ready)

## 배포 순서

```bash
# 1) 이미지 빌드·푸시 (CI: .github/workflows/build.yml, build context = 레포 루트)
docker build -f backend/predict/Dockerfile -t <ECR>/hailcast-dev-predict:<sha> .
# 2) 모델 1회 학습 업로드 (Job 또는 로컬)
python ml/train.py            # DB 데이터 충분 시 / --bootstrap: 합성 초기 모델
# 3) manifest 적용: configmap/secret → deployments → scaledobject → rbac
```
