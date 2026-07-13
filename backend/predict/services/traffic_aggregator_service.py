# TrafficAggregatorService — A1: call-api 각 파드가 10초마다 자기 몫의 콜 수를
# traffic/instances/<pod>.json에 써두면, 여기서 그 파일들을 모아 합산한다. 로컬
# 디스크가 아니라 FileStore(S3 백엔드면 진짜 공유됨)를 거치기 때문에 call-api가
# 여러 파드로 스케일아웃돼도 프론트가 보는 숫자가 하나로 합쳐진다.
from datetime import datetime, timezone

from common.core.constants import TRAFFIC_HISTORY_KEY, TRAFFIC_INSTANCE_PREFIX
from common.core.logger import get_logger
from common.core.store import FileStore

logger = get_logger("traffic_aggregator")

# 이보다 오래 갱신 안 된 인스턴스 파일은 죽은 파드로 보고 집계에서 뺀다 (하트비트 주기의 3배 여유).
_STALE_AFTER_SECONDS = 30.0
_HISTORY_MAX_POINTS = 3 * 60 * 6  # 10초 버킷 기준 3시간치


class TrafficAggregatorService:
    def __init__(self, store: FileStore, traffic_json_key: str):
        self._store = store
        self._traffic_json_key = traffic_json_key

    def aggregate(self) -> int:
        """10초 버킷 하나를 집계·저장한다. 반환값=이번 버킷의 총 콜 수."""
        now = datetime.now(timezone.utc)
        total = self._sum_active_instances(now)
        history = self._append_history(now, total)
        hourly = self._trailing_hour_sum(history, now)

        self._store.write_json(
            self._traffic_json_key,
            {
                "hourly_requests": hourly,
                "current_bucket_requests": total,
                "updated_at": now.isoformat(),
            },
        )
        logger.info(
            f"traffic aggregated (bucket={total}, hourly~={hourly:.0f})",
            extra={"event": "traffic_aggregated", "detail": {"bucket": total, "hourly": hourly}},
        )
        return total

    def _sum_active_instances(self, now: datetime) -> int:
        total = 0
        for key in self._store.list_keys(TRAFFIC_INSTANCE_PREFIX):
            body = self._store.read_json(key)
            if not body:
                continue
            try:
                updated_at = datetime.fromisoformat(body["updated_at"])
            except (KeyError, ValueError):
                logger.warning(
                    f"malformed traffic instance file, skipped: {key}",
                    extra={"event": "traffic_instance_invalid", "detail": {"key": key}},
                )
                continue
            if (now - updated_at).total_seconds() > _STALE_AFTER_SECONDS:
                continue  # 죽은 파드로 추정 — 마지막 값이 계속 잡히는 것 방지
            total += int(body.get("count", 0))
        return total

    def _append_history(self, now: datetime, count: int) -> list[dict]:
        history = self._store.read_json(TRAFFIC_HISTORY_KEY) or []
        history.append({"timestamp": now.isoformat(), "requests": count})
        history = history[-_HISTORY_MAX_POINTS:]
        self._store.write_json(TRAFFIC_HISTORY_KEY, history)
        return history

    def _trailing_hour_sum(self, history: list[dict], now: datetime) -> float:
        cutoff = now.timestamp() - 3600
        return float(
            sum(
                point["requests"]
                for point in history
                if datetime.fromisoformat(point["timestamp"]).timestamp() >= cutoff
            )
        )
