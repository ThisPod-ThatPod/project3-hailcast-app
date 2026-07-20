#!/bin/bash
# =============================================================
# 넣을 위치 : project3-hailcast-app/scripts/build_push.sh
# 소유      : 그룹 B (재혁·창원)
# 역할      : 서비스별 docker build → ECR push (커밋 SHA 태그, 네이밍규약서 §8 — latest 금지)
# 호출      : `make build-push` (이 레포) / `make app-build-push` (ops 위임)
# 전제      : ECR 로그인 완료(build_push.sh가 직접 로그인도 시도함), AWS 자격증명 유효
# 사용      : SERVICES="call-api predict" bash scripts/build_push.sh   (기본값은 Makefile SERVICES)
# =============================================================
set -euo pipefail

REGION="${REGION:-ap-northeast-2}"
SERVICES="${SERVICES:-call-api predict worker weather-cron simulator}"
GIT_SHA="$(git rev-parse --short=7 HEAD)"

ACCOUNT_ID="$(aws sts get-caller-identity --query Account --output text)"
REGISTRY="${ACCOUNT_ID}.dkr.ecr.${REGION}.amazonaws.com"

echo "[build_push] registry=$REGISTRY tag=$GIT_SHA services=$SERVICES"

aws ecr get-login-password --region "$REGION" | docker login --username AWS --password-stdin "$REGISTRY"

# build context는 레포 루트여야 한다 — 각 Dockerfile이 backend/common(+predict는 ml/)을 COPY한다.
cd "$(git rev-parse --show-toplevel)"

for svc in $SERVICES; do
  image="${REGISTRY}/hailcast-dev-${svc}"
  echo "[build_push] === ${svc} ==="
  docker build -f "backend/${svc}/Dockerfile" -t "${image}:${GIT_SHA}" .
  docker push "${image}:${GIT_SHA}"
  echo "[build_push] pushed ${image}:${GIT_SHA}"
done

echo "[build_push] 완료. 매니페스트의 <GITHUB_SHA> 자리에 ${GIT_SHA}를 넣으세요:"
echo "  sed -i \"s#<GITHUB_SHA>#${GIT_SHA}#g\" k8s/*.yaml   # (적용 전 사본에서)"
