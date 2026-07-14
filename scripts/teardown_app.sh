#!/bin/bash
# =============================================================
# 넣을 위치 : project3-hailcast-app/scripts/teardown_app.sh
# 소유      : 그룹 B (재혁·창원)
# 역할      : '각자 로컬'의 도커 이미지·볼륨·빌드캐시 정리. (다음 apply 를 깨끗한 상태로)
#             클라우드 삭제가 아니라 로컬 청소라, ops teardown 의 '맨 마지막' 단계.
# 호출      : ops 의 teardown.sh 가 3번째(마지막)에 부른다. 실패해도 클라우드엔 무영향.
# 커스터마이징: ★ 지울 이미지/볼륨 대상. 전체 prune 은 '다른 프로젝트'까지 날리니 라벨/이름 필터 권장.
# 안전      : CONFIRM=yes 일 때만 실제 삭제(ops --yes 시 자동 주입). 기본은 '대상 미리보기'.
# =============================================================
set -u
CONFIRM="${CONFIRM:-}"
FILTER="${FILTER:-hailcast}"            # ★ 우리 프로젝트 이미지 식별자(이름/라벨)

echo "[app] 로컬 도커 자원 정리 (필터: $FILTER)"

# ── ① 대상 미리보기 (항상 보여줌) ──────────────────────────
echo "[app] 삭제 대상 이미지:"
docker images --filter=reference="*${FILTER}*" 2>/dev/null || true
echo "[app] 프로젝트 볼륨(있다면):"
docker volume ls 2>/dev/null | grep -i "$FILTER" || echo "  (해당 볼륨 없음)"

if [ "$CONFIRM" != "yes" ]; then
    echo "[app] (미실행 — 미리보기만. 실제 삭제는 CONFIRM=yes 또는 ops --yes)"
    exit 0
fi

# ── ② 실제 삭제 (라벨/이름 필터로 우리 것만) ★ ─────────────
# 이름 필터 이미지 삭제
docker images --filter=reference="*${FILTER}*" -q | sort -u | xargs -r docker rmi -f
# 라벨을 심어 빌드했다면 라벨 기준이 더 안전:
# docker image prune -af --filter "label=project=hailcast"
# 프로젝트 볼륨:
docker volume ls -q | grep -i "$FILTER" | xargs -r docker volume rm
# 빌드 캐시(전체 — 로컬 재빌드만 느려질 뿐 안전):
docker builder prune -af

echo "[app] 완료 — 로컬이 깨끗해졌습니다. 다음 apply/build 는 새로 받습니다."
echo "  ※ 전체 초기화가 필요하면(주의): docker system prune -af --volumes"