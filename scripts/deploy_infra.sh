#!/bin/bash
# =============================================================
# 파일위치 : project3-hailcast-app/scripts/deploy_infra.sh
# 역할    : docs/2026-07-20-app-deploy-guide.md 전체를 한 번에 실행
#           (계정 가드 → kubeconfig → build+push → AWS 값 조회(직접 API) →
#            k8s 매니페스트 렌더링 → apply → 파드 기동 대기)
# 실행    : bash scripts/deploy_infra.sh   /  make deploy-all
# 전제    : 인프라 terraform apply 완료(EKS·RDS·SQS·S3·DynamoDB·IRSA 10종·ECR 6종),
#           aws/kubectl/docker 준비됨(ops 레포 make setup), .env에 PROJECT_ACCOUNT_ID
# 재실행  : 멱등하다 — kubectl apply는 몇 번을 다시 돌려도 안전(선언적 적용).
#           중간에 실패하면 원인 고치고 그냥 다시 실행하면 된다.
# 참고    : 2026-07-20 시점 ArgoCD/ESO/KEDA는 아직 클러스터에 미설치(배포팀 목/금 예정) —
#           ESO 없으면 STEP 3.5가 RDS Secret을 직접 만들어 대체한다. ESO 설치되면
#           배포팀 ExternalSecret(creationPolicy Owner)이 이 Secret을 그대로 이어받는다.
# =============================================================
set -euo pipefail

source "$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)/_lib.sh"

CLUSTER_NAME="${CLUSTER_NAME:-hailcast-dev-eks}"
NAMESPACE="hailcast"

# ── STEP -1 : 필수 도구 확인 (없으면 설치 시도) ─────────────
for tool in jq envsubst; do
    command -v "$tool" &>/dev/null || {
        warning "$tool 없음 → 설치 시도"
        sudo dnf install -y jq gettext -q || error "$tool 설치 실패 — 수동 설치 필요"
    }
done

echo ""
echo "============================================="
echo "  hailcast app — 실인프라 배포 (전체 자동)"
echo "============================================="
echo ""

# ── STEP 0 : 계정 가드 + kubeconfig ─────────────────────────
info "STEP 0/5 : 계정 확인 + kubeconfig 갱신..."
guard_project_account
aws eks update-kubeconfig --name "$CLUSTER_NAME" --region "$AWS_REGION" \
    || error "kubeconfig 갱신 실패 — EKS 클러스터(${CLUSTER_NAME})가 아직 없나요? infra apply 먼저 완료해야 합니다."
kubectl get nodes &>/dev/null \
    || error "클러스터 접속 실패 — 'kubectl get nodes'를 직접 돌려서 원인을 확인하세요."
success "클러스터 접속 OK ($(kubectl get nodes --no-headers | wc -l)개 노드)"

# ── STEP 1 : 이미지 build → ECR push ────────────────────────
info "STEP 1/5 : docker build → ECR push..."
bash "$APP_ROOT/scripts/build_push.sh"
GIT_SHA="$(git -C "$APP_ROOT" rev-parse --short HEAD)"
success "이미지 태그: ${GIT_SHA}"

# ── STEP 2 : AWS 값 가져오기 (terraform output 대신 직접 API 호출) ──
# ⚠️ 2026-07-20: 일반 dev IAM 사용자는 tfstate 버킷에 명시적 deny가 걸려있어
# terraform output/init 자체가 안 됨(RDS 비번이 tfstate 평문에 있어서 의도된 보호).
# 같은 값을 얻을 수 있는 직접 API 호출로 대체 — CI 전용 role(gha-tf-*)만 tfstate를 본다.
info "STEP 2/5 : AWS 리소스 값 조회 중 (직접 API 호출)..."

export MODEL_BUCKET_NAME; MODEL_BUCKET_NAME="$(aws s3api list-buckets \
    --query "Buckets[?starts_with(Name,'hailcast-dev-model')].Name | [0]" --output text --region "$AWS_REGION" 2>/dev/null || true)"
export SQS_QUEUE_URL; SQS_QUEUE_URL="$(aws sqs get-queue-url --queue-name hailcast-dev-call-queue \
    --query QueueUrl --output text --region "$AWS_REGION" 2>/dev/null || true)"
export RDS_HOST; RDS_HOST="$(aws ssm get-parameter --name /hailcast/dev/rds/endpoint \
    --query Parameter.Value --output text --region "$AWS_REGION" 2>/dev/null || true)"
export RDS_MASTER_SECRET_ARN; RDS_MASTER_SECRET_ARN="$(aws secretsmanager list-secrets \
    --filters Key=name,Values=rds --query "SecretList[0].ARN" --output text --region "$AWS_REGION" 2>/dev/null || true)"

IRSA_ROLE_PREFIX="hailcast-dev-irsa"
export PREDICT_IRSA_ROLE_ARN; PREDICT_IRSA_ROLE_ARN="$(aws iam get-role --role-name "${IRSA_ROLE_PREFIX}-predict" --query Role.Arn --output text 2>/dev/null || true)"
export CALL_API_IRSA_ROLE_ARN; CALL_API_IRSA_ROLE_ARN="$(aws iam get-role --role-name "${IRSA_ROLE_PREFIX}-call-api" --query Role.Arn --output text 2>/dev/null || true)"
export WORKER_IRSA_ROLE_ARN; WORKER_IRSA_ROLE_ARN="$(aws iam get-role --role-name "${IRSA_ROLE_PREFIX}-worker" --query Role.Arn --output text 2>/dev/null || true)"
export WEATHER_CRON_IRSA_ROLE_ARN; WEATHER_CRON_IRSA_ROLE_ARN="$(aws iam get-role --role-name "${IRSA_ROLE_PREFIX}-weather-cron" --query Role.Arn --output text 2>/dev/null || true)"
export SIMULATOR_IRSA_ROLE_ARN; SIMULATOR_IRSA_ROLE_ARN="$(aws iam get-role --role-name "${IRSA_ROLE_PREFIX}-simulator" --query Role.Arn --output text 2>/dev/null || true)"

MISSING=""
for v in MODEL_BUCKET_NAME SQS_QUEUE_URL RDS_HOST RDS_MASTER_SECRET_ARN \
         PREDICT_IRSA_ROLE_ARN CALL_API_IRSA_ROLE_ARN WORKER_IRSA_ROLE_ARN \
         WEATHER_CRON_IRSA_ROLE_ARN SIMULATOR_IRSA_ROLE_ARN; do
    [ -n "${!v:-}" ] && [ "${!v}" != "None" ] || MISSING="${MISSING} ${v}"
done
[ -z "$MISSING" ] || error "AWS 리소스 값이 비어있습니다:${MISSING} — infra apply가 끝났는지, 자격증명 권한을 확인하세요."
success "AWS 리소스 값 전부 확인됨 (MODEL_BUCKET_NAME=${MODEL_BUCKET_NAME})"

# ── STEP 3 : 매니페스트 렌더링 + apply ──────────────────────
info "STEP 3/5 : k8s 매니페스트 렌더링..."
RENDER_DIR="$(mktemp -d)"
trap 'rm -rf "$RENDER_DIR"' EXIT
for f in "$APP_ROOT"/k8s/*.yaml; do
    envsubst < "$f" > "$RENDER_DIR/$(basename "$f")"
done
sed -i \
    -e "s#<GITHUB_SHA>#${GIT_SHA}#g" \
    -e "s#<ECR>#${PROJECT_ACCOUNT_ID}.dkr.ecr.${AWS_REGION}.amazonaws.com#g" \
    -e "s#<SQS_QUEUE_URL>#${SQS_QUEUE_URL}#g" \
    "$RENDER_DIR"/*.yaml

if grep -lE '\$\{[A-Z_]+\}' "$RENDER_DIR"/*.yaml 2>/dev/null; then
    error "위 파일에 안 채워진 \${...} 자리가 남아있습니다 — apply 중단(렌더링 실패)"
fi
success "렌더링 완료 (${RENDER_DIR})"

info "STEP 4/5 : kubectl apply (의존성 순서대로)..."
kubectl apply -f "$RENDER_DIR/00-namespace.yaml"
kubectl apply -f "$RENDER_DIR/01-serviceaccounts.yaml"
kubectl apply -f "$RENDER_DIR/02-configmap.yaml"

if kubectl get crd externalsecrets.external-secrets.io &>/dev/null; then
    kubectl apply -f "$RENDER_DIR/02b-externalsecret.yaml" \
        || warning "ExternalSecret apply 실패 — 배포팀 확인 필요. 계속 진행합니다."

    info "ExternalSecret 동기화 대기 중 (최대 30초)..."
    status=""
    for _ in $(seq 1 30); do
        status="$(kubectl get externalsecret hailcast-rds-secret -n "$NAMESPACE" \
            -o jsonpath='{.status.conditions[0].status}' 2>/dev/null || true)"
        [ "$status" = "True" ] && break
        sleep 1
    done
    [ "$status" = "True" ] && success "ExternalSecret 동기화 완료" \
        || warning "ExternalSecret이 아직 SecretSynced 상태가 아닙니다 — 'kubectl get externalsecret -n ${NAMESPACE}'로 나중에 확인하세요."
else
    warning "ExternalSecret CRD 없음 — ESO 미설치. RDS Secret을 직접 만듭니다."
fi

# ── STEP 3.5 : ESO가 아직 hailcast-rds-secret 을 못 채웠으면 직접 만들어본다 ──
# (ESO 설치 후엔 creationPolicy: Owner인 ExternalSecret이 이 Secret을 그대로 이어받아 관리한다.)
# ⚠️ 2026-07-20: dev IAM 그룹(hailcast-devs)에 secretsmanager:GetSecretValue가 명시적으로
# deny 돼있음(tfstate와 같은 보호 — RDS 마스터 비번은 dev 계정이 못 읽게 의도된 것으로 보임).
# 이 경우 여기서 스크립트를 죽이지 않고 경고만 남기고 계속 진행한다 — DB 필요 없는 서비스
# (weather-cron/simulator)는 정상 기동하고, DB 필요한 서비스(call-api/worker/predict)는
# ESO 설치 전까지 CrashLoopBackOff가 나는 게 정상(예상된 상태)이다.
if ! kubectl get secret hailcast-rds-secret -n "$NAMESPACE" &>/dev/null; then
    info "hailcast-rds-secret 없음 → RDS 마스터 자격증명으로 임시 생성 시도..."
    if RDS_MASTER_JSON="$(aws secretsmanager get-secret-value \
        --secret-id "$RDS_MASTER_SECRET_ARN" --region "$AWS_REGION" \
        --query SecretString --output text 2>&1)"; then
        RDS_MASTER_USER="$(echo "$RDS_MASTER_JSON" | jq -r .username)"
        RDS_MASTER_PASS="$(echo "$RDS_MASTER_JSON" | jq -r .password)"
        kubectl create secret generic hailcast-rds-secret -n "$NAMESPACE" \
            --from-literal=DB_HOST="$RDS_HOST" \
            --from-literal=DB_USER="$RDS_MASTER_USER" \
            --from-literal=DB_PASSWORD="$RDS_MASTER_PASS" \
            --dry-run=client -o yaml | kubectl apply -f -
        success "임시 hailcast-rds-secret 생성 완료 (ESO 설치되면 자동으로 교체됨)"
    else
        warning "RDS 마스터 시크릿 조회 실패(dev 계정은 GetSecretValue가 막혀있을 수 있음) — hailcast-rds-secret 없이 계속 진행합니다. call-api/worker/predict는 ESO 설치 전까지 DB 연결 실패로 재시작을 반복하는 게 정상입니다."
    fi
fi

kubectl apply -f "$RENDER_DIR/predict-rbac.yaml"
# predict/call-api(더 이전) + worker/simulator/frontend/weather-cron(2026-07-27 확인)까지
# 전부 배포팀 ArgoCD(apps/*)가 소유 — 여기서 안 올림(중복 실행/되돌림 방지).
# 2026-07-27: kubectl get application -n argocd로 6개 서비스 전부 Synced인 것 확인 후
# 같은 이름(hailcast-worker/hailcast-simulator/hailcast-frontend/hailcast-weather-cron)의
# 리소스를 이 스크립트가 계속 apply하고 있던 것 뒤늦게 발견 — predict/call-api 때와
# 동일한 되돌림 위험이라 전부 제거. 남는 건 predict-rbac(ClusterRole)·KEDA 리소스뿐이다.
kubectl apply -f "$RENDER_DIR/keda-triggerauthentication.yaml" \
    || warning "TriggerAuthentication apply 실패 — KEDA operator가 아직 설치 안 됐을 수 있음(배포팀 확인)."
kubectl apply -f "$RENDER_DIR/worker-scaledobject.yaml" \
    || warning "ScaledObject apply 실패 — KEDA CRD가 아직 없을 수 있음."
success "apply 완료"

# ── STEP 5 : 파드 기동 대기 + 결과 표시 ─────────────────────
info "STEP 5/5 : 파드 기동 대기 (최대 3분)..."
kubectl wait --for=condition=Ready pod --all -n "$NAMESPACE" --timeout=180s \
    || warning "일부 파드가 3분 안에 Ready 상태가 안 됐습니다 — 아래 목록에서 확인하세요."

echo ""
kubectl get pods -n "$NAMESPACE" -o wide
echo ""
success "배포 완료. 다음은 docs/2026-07-20-infra-deployment-test-checklist.md 로 스모크 테스트 진행하세요."
