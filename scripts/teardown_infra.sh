#!/bin/bash
# =============================================================
# 파일위치 : project3-hailcast-app/scripts/teardown_infra.sh
# 역할    : scripts/deploy_infra.sh(= make deploy-all)로 실인프라(EKS)에 올린
#           우리 파트(B팀) 리소스를 전부 지운다. 로컬 청소(teardown_app.sh)와 달리
#           실제 클러스터를 건드리는 원격/파괴적 작업이라 기본은 미리보기만 한다.
# 실행    : bash scripts/teardown_infra.sh          (미리보기만)
#           CONFIRM=yes bash scripts/teardown_infra.sh   (실제 삭제)
#           make teardown-infra   /  CONFIRM=yes make teardown-infra
# 지우는 것: hailcast 네임스페이스 전체(그 안의 Deployment/Service/Secret/ConfigMap/
#           ServiceAccount/RBAC/KEDA 리소스가 전부 딸려서 삭제됨) +
#           네임스페이스 밖에 있는 predict의 ClusterRole/ClusterRoleBinding(노드 조회용) 2개.
# 안 지우는 것: ECR 이미지(스토리지 비용 미미, 팀 공용이라 임의 삭제 안 함),
#           EKS/RDS/SQS/S3/DynamoDB/IRSA(전부 인프라팀 terraform 소관, 우리 권한 밖).
# =============================================================
set -u

source "$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)/_lib.sh"

CONFIRM="${CONFIRM:-}"
NAMESPACE="hailcast"
CLUSTER_NAME="${CLUSTER_NAME:-hailcast-dev-eks}"

echo ""
echo "============================================="
echo "  hailcast app — 실인프라(EKS) 배포분 정리"
echo "============================================="
echo ""

# ⭐ 계정 가드 — 엉뚱한 계정/클러스터를 지우는 사고 방지
guard_project_account
aws eks update-kubeconfig --name "$CLUSTER_NAME" --region "$AWS_REGION" &>/dev/null \
    || warning "kubeconfig 갱신 실패 — 이미 맞는 컨텍스트일 수도 있음, 계속 진행"

# ── ① 대상 미리보기 (항상 보여줌) ──────────────────────────
if kubectl get namespace "$NAMESPACE" &>/dev/null; then
    info "네임스페이스 '${NAMESPACE}' 안의 리소스:"
    kubectl get all,secret,configmap,serviceaccount,scaledobject,triggerauthentication,externalsecret \
        -n "$NAMESPACE" 2>/dev/null
else
    warning "네임스페이스 '${NAMESPACE}' 없음 — 이미 지워졌거나 아직 배포 안 됨"
fi

echo ""
info "네임스페이스 밖 클러스터 범위 리소스(predict 노드 조회용):"
kubectl get clusterrole hailcast-node-reader 2>/dev/null || echo "  hailcast-node-reader 없음"
kubectl get clusterrolebinding hailcast-predict-node-reader 2>/dev/null || echo "  hailcast-predict-node-reader 없음"

if [ "$CONFIRM" != "yes" ]; then
    echo ""
    warning "(미실행 — 미리보기만. 실제 삭제는 CONFIRM=yes bash scripts/teardown_infra.sh)"
    exit 0
fi

# ── ② 실제 삭제 ─────────────────────────────────────────────
echo ""
info "네임스페이스 '${NAMESPACE}' 삭제 중 (안의 모든 리소스가 함께 삭제됨)..."
kubectl delete namespace "$NAMESPACE" --ignore-not-found --timeout=120s \
    || warning "네임스페이스 삭제가 시간 안에 안 끝났을 수 있음 — 'kubectl get namespace ${NAMESPACE}'로 나중에 확인(Terminating 상태로 오래 걸릴 수 있음, finalizer 걸린 리소스 있으면 수동 확인 필요)"

info "클러스터 범위 RBAC 삭제 중..."
kubectl delete clusterrolebinding hailcast-predict-node-reader --ignore-not-found
kubectl delete clusterrole hailcast-node-reader --ignore-not-found

echo ""
success "완료 — hailcast 네임스페이스 + 관련 클러스터 RBAC 전부 삭제됨."
echo "  ECR 이미지는 그대로 남아있습니다(용량 미미, 임의 삭제 안 함) — 필요하면 직접:"
echo "    aws ecr batch-delete-image --repository-name hailcast-dev-<서비스> --image-ids imageTag=<태그>"
echo "  다시 올리려면: make deploy-all"
