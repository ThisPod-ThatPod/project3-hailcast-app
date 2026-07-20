#!/bin/bash
# =============================================================
# 파일위치 : project3-hailcast-app/scripts/build_push.sh
# 이 Pod 저 Pod · hailcast — docker build → ECR push
# 역할    : 서비스 이미지를 빌드해 프로젝트 계정 ECR 에 올린다.
#           ECR 리포지토리 이름 = hailcast-dev-<서비스> (네이밍규약서 §5-2)
#           리포지토리 '생성'은 infra(Terraform) 소관 — 여기선 없으면 만들지 않고 중단한다.
# 실행    : bash scripts/build_push.sh [서비스...]     (생략 시 전체)
#           make build-push   /  ops 에서  make app-build-push
# 태그    : TAG 환경변수 (기본값: git 짧은 커밋 해시) 만 push — latest 금지(네이밍규약서 §8-1)
#           예) TAG=v0.3.0 bash scripts/build_push.sh call-api
#
# ⭐ 계정 가드 선행 — ECR push 는 '운영 이미지를 바꾸는' 경로다.
#    엉뚱한 계정에 앉은 채로 돌면 남의 레지스트리에 올리거나 로그인부터 죽는다.
#    ops 가 infra-apply 앞에 guard-account 를 세우는 것과 같은 논리.
# =============================================================
set -euo pipefail

# ── 공용 상수·계정 가드 (AWS_REGION · NAME_PREFIX · PROJECT_ACCOUNT_ID) ──
# shellcheck source=scripts/_lib.sh
source "$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)/_lib.sh"

# ── 전제 확인 ──────────────────────────────────────────────
command -v aws    &>/dev/null || error "AWS CLI 미설치 → ops 레포에서 make setup"
command -v docker &>/dev/null || error "docker 미설치 → ops 레포에서 make setup"
docker info &>/dev/null       || error "docker 데몬에 접근 불가 → sudo systemctl start docker 또는 newgrp docker"

# ── ⭐ 계정 가드 : push 전에 '어느 계정인지' 먼저 대조한다 ──
guard_project_account

ECR_REGISTRY="${PROJECT_ACCOUNT_ID}.dkr.ecr.${AWS_REGION}.amazonaws.com"

# ── 대상 서비스 : 인자 > SERVICES 환경변수 > 기본 전체 ─────
if [ $# -gt 0 ]; then
    SERVICES="$*"
else
    SERVICES="${SERVICES:-$DEFAULT_SERVICES}"
fi

# ── 태그 : TAG 환경변수 > git 짧은 해시 > 날짜 ─────────────
# latest 를 쓰면 '어느 코드가 떠 있는지' 를 클러스터에서 역추적할 수 없다 (네이밍규약서 §8-1, latest 금지).
# 커밋 해시 태그만 올려 이미지 ↔ 코드를 1:1 로 잇는다.
if [ -z "${TAG:-}" ]; then
    if TAG="$(git -C "$APP_ROOT" rev-parse --short HEAD 2>/dev/null)"; then
        # 커밋 안 된 변경이 섞여 들어가면 해시가 코드를 대변하지 못한다 → 경고만 (막지는 않음)
        if [ -n "$(git -C "$APP_ROOT" status --porcelain 2>/dev/null)" ]; then
            warning "커밋 안 된 변경이 있습니다 — 태그(${TAG})가 실제 이미지 내용과 다를 수 있습니다."
        fi
    else
        TAG="$(date +%Y%m%d-%H%M%S)"
        warning "git 저장소가 아님 → 날짜 태그(${TAG}) 사용"
    fi
fi

echo ""
echo "============================================="
echo "  hailcast app — build & push (ECR)"
echo "  레지스트리 : ${ECR_REGISTRY}"
echo "  대상       : ${SERVICES}"
echo "  태그       : ${TAG}"
echo "============================================="
echo ""

# ── ECR 로그인 (격리된 DOCKER_CONFIG 를 쓰고 있어도 그대로 동작) ──
info "ECR 로그인..."
aws ecr get-login-password --region "$AWS_REGION" \
    | docker login --username AWS --password-stdin "$ECR_REGISTRY" \
    || error "ECR 로그인 실패 → 자격증명·권한(ecr:GetAuthorizationToken) 확인"

# ── 서비스별 build → push ──────────────────────────────────
PUSHED=()
for svc in $SERVICES; do
    dockerfile="backend/${svc}/Dockerfile"
    repo="${NAME_PREFIX}-${svc}"                 # 규약서 §5-2
    image="${ECR_REGISTRY}/${repo}"

    echo ""
    info "───────── [${svc}] ${repo}:${TAG} ─────────"

    [ -f "$APP_ROOT/$dockerfile" ] || error "${dockerfile} 없음 → 서비스명 오타이거나 아직 Dockerfile 미작성 (frontend 는 서빙방식 확정 후)"

    # 리포지토리는 infra(Terraform)가 만든다. 여기서 몰래 만들면(create-repository)
    # 규약서 밖 리소스가 생기고 terraform destroy 로도 안 지워진다 → 없으면 중단이 맞다.
    aws ecr describe-repositories --repository-names "$repo" --region "$AWS_REGION" &>/dev/null \
        || error "ECR 리포지토리 '${repo}' 없음 → infra 소관(규약서 §5-2). ops 에서 make infra-apply 가 먼저다."

    # compose 와 같은 빌드 문맥: context = 레포 루트, -f 로 Dockerfile 지정
    # (backend/common 등 공용 모듈을 COPY 하려면 루트 문맥이어야 한다)
    docker build -f "$APP_ROOT/$dockerfile" \
        -t "${image}:${TAG}" \
        "$APP_ROOT" \
        || error "[${svc}] build 실패"

    docker push "${image}:${TAG}"    || error "[${svc}] push 실패 (${TAG})"

    success "[${svc}] 완료 → ${image}:${TAG}"
    PUSHED+=("$svc")
done

echo ""
echo "============================================="
success "전체 완료 : ${#PUSHED[@]}개 서비스 push (태그 ${TAG})"
echo "  다음 단계 : manifests 레포의 이미지 태그를 ${TAG} 로 갱신 → ops 에서 make deploy"
echo "============================================="
