# =============================================================
# 넣을 위치 : project3-hailcast-app/Makefile
# 소유      : 그룹 B (재혁·창원)
# 역할      : ops 의 make -C 위임을 받는 진입점(build-push/teardown).
# 사용      : 이 레포에서  make build-push   /  ops 에서  make app-build-push
# =============================================================

# ★ 커스터마이징: ECR 레지스트리·태그·서비스 목록은 Phase 4 에서 채운다.
REGION   ?= ap-northeast-2
SERVICES ?= call-api predict worker weather-cron simulator   # frontend 는 서빙방식 확정 후

.PHONY: help build-push teardown
help:       ## 명령 목록
	@echo "  make build-push | teardown"

build-push: ## docker build → ECR push (Phase 4에서 구현)
	@echo "TODO(Phase 4): 각 서비스 docker build → ECR push"
	@echo "  대상: $(SERVICES) / region: $(REGION)"
	# 예) bash scripts/build_push.sh $(SERVICES)

# 로컬 도커 이미지·볼륨·캐시 정리 (다음 apply 를 깨끗하게)
teardown:   ## 로컬 도커 자원 정리 (scripts/teardown_app.sh)
	@chmod +x scripts/teardown_app.sh && bash scripts/teardown_app.sh