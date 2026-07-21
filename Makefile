# =============================================================
# 넣을 위치 : project3-hailcast-app/Makefile
# 소유      : 그룹 B (재혁·창원)
# 역할      : ops 의 make -C 위임을 받는 진입점(build-push/teardown)
#             + 로컬 docker compose 테스트 환경(dev-*) 관리.
# 사용      : 이 레포에서  make help   /  ops 에서  make app-build-push
# =============================================================

REGION   ?= ap-northeast-2
SERVICES ?= call-api predict worker weather-cron simulator frontend

.PHONY: help dev-up dev-down dev-clean dev-rebuild dev-logs dev-ps dev-train \
        build-push deploy-all teardown teardown-infra

help: ## 명령 목록
	@echo ""
	@echo "====================================================="
	@echo "   이 Pod 저 Pod · hailcast — app 명령어"
	@echo "====================================================="
	@echo ""
	@echo "  [ 로컬 테스트 (docker compose · AWS 자격증명 불필요) ]"
	@echo "  make dev-up          전체 빌드 + 기동 (postgres·localstack 포함)"
	@echo "  make dev-down        중지 (볼륨 유지)"
	@echo "  make dev-clean       중지 + 볼륨 삭제 (DB 초기화 · y/N 확인)"
	@echo "  make dev-rebuild     다시 빌드해 교체 (SVC=call-api 처럼 지정 가능)"
	@echo "  make dev-logs        로그 팔로우 (SVC=... 지정 가능)"
	@echo "  make dev-ps          컨테이너 상태"
	@echo "  make dev-train       오프라인 학습 1회 (ml-train)"
	@echo ""
	@echo "  [ 운영 (AWS · 계정 가드 선행) ]"
	@echo "  make build-push      docker build → ECR push (TAG=... 지정 가능)"
	@echo "  make deploy-all      실인프라 배포 전체 자동화 (kubeconfig→build-push→"
	@echo "                       AWS 값 조회→k8s apply→기동 대기, 재실행해도 안전)"
	@echo ""
	@echo "  [ 정리 ]"
	@echo "  make teardown        로컬 도커 이미지·볼륨·캐시 정리 (CONFIRM=yes 시 실제 삭제)"
	@echo "  make teardown-infra  실인프라(EKS) 배포분 전부 삭제 — hailcast 네임스페이스 +"
	@echo "                       클러스터 RBAC (CONFIRM=yes 시 실제 삭제, 기본은 미리보기)"
	@echo ""

# ── 로컬 테스트 환경 (scripts/dev_local.sh) ────────────────
# SVC 변수로 특정 서비스만 지정:  make dev-logs SVC=call-api
dev-up:      ; @bash scripts/dev_local.sh up
dev-down:    ; @bash scripts/dev_local.sh down
dev-clean:   ; @bash scripts/dev_local.sh clean
dev-rebuild: ; @bash scripts/dev_local.sh rebuild $(SVC)
dev-logs:    ; @bash scripts/dev_local.sh logs $(SVC)
dev-ps:      ; @bash scripts/dev_local.sh ps
dev-train:   ; @bash scripts/dev_local.sh train

# ── 운영 : build → ECR push (scripts/build_push.sh) ────────
# 계정 가드·ECR 로그인·리포지토리 존재 확인은 스크립트 안에서 한다.
build-push: ## docker build → ECR push
	@SERVICES="$(SERVICES)" AWS_REGION="$(REGION)" bash scripts/build_push.sh

# ── 운영 : 실인프라 배포 전체 자동화 (scripts/deploy_infra.sh) ──
# docs/2026-07-20-app-deploy-guide.md 의 0~4단계를 한 번에 실행한다.
deploy-all: ## 실인프라 배포(kubeconfig→build-push→apply→기동 대기) 한 번에
	@AWS_REGION="$(REGION)" bash scripts/deploy_infra.sh

# 로컬 도커 이미지·볼륨·캐시 정리 (다음 apply 를 깨끗하게)
teardown:   ## 로컬 도커 자원 정리 (scripts/teardown_app.sh)
	@bash scripts/teardown_app.sh

# ── 정리 : 실인프라(EKS) 배포분 삭제 (scripts/teardown_infra.sh) ──
# 기본은 미리보기만. 실제 삭제는 CONFIRM=yes.
teardown-infra: ## 실인프라 배포분 삭제 — hailcast 네임스페이스 + 클러스터 RBAC
	@CONFIRM="$(CONFIRM)" AWS_REGION="$(REGION)" bash scripts/teardown_infra.sh
