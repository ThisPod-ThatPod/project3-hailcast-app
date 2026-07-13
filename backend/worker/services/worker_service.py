# WorkerService — SQS 소비 Business Logic
# 흐름: Polling → Deserialize → Validation → FileStore Save → ACK(delete)
# 오류 시 메시지를 삭제하지 않아 Visibility Timeout 후 재수신(재시도)된다. (향후 DLQ 연계)
#
# DB(RDS) 기반 버전은 backend/worker-db-original/에 격리돼 있다 — 인프라 다이어그램은
# RDS 기록을 요구하지만(J3와 충돌, project_hailcast_architecture_conflict.md 참고),
# 이번 재설계에서는 FileStore로 통일한다.
import time
from datetime import datetime, timezone

from pydantic import ValidationError

from common.aws.sqs_adapter import SqsAdapter
from common.core.constants import CALL_RECORD_PREFIX, CallStatus
from common.core.logger import get_logger
from common.core.metrics import (
    QUEUE_LATENCY_SECONDS,
    WORKER_FAILED_TOTAL,
    WORKER_PROCESSED_TOTAL,
    metrics,
)
from common.core.store import FileStore
from common.models.call import CallMessage

from config import WorkerSettings

logger = get_logger("worker_service")


class WorkerService:
    def __init__(self, sqs: SqsAdapter, store: FileStore, settings: WorkerSettings):
        self._sqs = sqs
        self._store = store
        self._settings = settings
        self._running = False

    # ---------- 폴링 루프 ----------
    def run_forever(self) -> None:
        self._running = True
        logger.info(
            "worker polling started",
            extra={"event": "worker_start", "queue": self._settings.sqs_queue_name},
        )
        while self._running:
            try:
                self.poll_once()
            except Exception as exc:
                # 큐 접근 자체가 실패하면 잠시 대기 후 재시도 (루프는 죽지 않는다)
                logger.error(f"queue polling failed: {exc}", extra={"event": "poll_error"})
                time.sleep(5)

    def stop(self) -> None:
        self._running = False

    def poll_once(self) -> int:
        """Long Polling 1회 수행. 처리한 메시지 수를 반환한다 (테스트 용이성)."""
        messages = self._sqs.receive_messages(
            max_messages=self._settings.sqs_batch_size,
            wait_seconds=self._settings.sqs_long_poll_seconds,
            visibility_timeout=self._settings.sqs_visibility_timeout,
        )
        if not messages:
            if self._settings.poll_idle_interval > 0:
                time.sleep(self._settings.poll_idle_interval)
            return 0
        processed = 0
        for msg in messages:
            if self._process_message(msg):
                processed += 1
        return processed

    # ---------- 메시지 단위 처리 ----------
    def _process_message(self, msg: dict) -> bool:
        receive_count = msg["receive_count"]
        logger.info(
            "message received",
            extra={
                "event": "worker_receive",
                "detail": {"message_id": msg["message_id"], "receive_count": receive_count},
            },
        )
        # 1) Deserialize + Validation — 실패하면 재시도해도 소용없는 poison message
        try:
            message = CallMessage.from_body(msg["body"])
        except ValidationError as exc:
            return self._handle_poison(msg, reason=f"invalid message body: {exc.errors()[:3]}")

        key = f"{CALL_RECORD_PREFIX}{message.request_id}.json"

        # 2) Business Logic + FileStore Save
        try:
            existing = self._store.read_json(key)
            if existing is not None:
                # 재수신(visibility timeout 만료 등) — 멱등 처리, 다시 쓰지 않는다
                logger.info(
                    "duplicate delivery, already saved",
                    extra={"event": "worker_duplicate", "request_id": message.request_id},
                )
            else:
                now = datetime.now(timezone.utc)
                req = message.data
                record = {
                    "call_id": message.request_id,
                    "user_id": req.user_id,
                    "pickup": req.pickup,
                    "destination": req.destination,
                    "source": req.source,
                    "requested_at": (req.requested_at or message.timestamp).isoformat(),
                    "status": str(CallStatus.DONE),
                    "message_version": message.version,
                    "enqueued_at": message.timestamp.isoformat(),
                    "processed_at": now.isoformat(),
                    "receive_count": receive_count,
                }
                self._store.write_json(key, record)
                logger.info(
                    "call saved",
                    extra={"event": "worker_save", "request_id": message.request_id, "status": str(CallStatus.DONE)},
                )
        except Exception as exc:
            # 일시적 장애 가능성 — 메시지를 삭제하지 않고 재시도에 맡긴다
            metrics.increment(WORKER_FAILED_TOTAL)
            logger.error(
                f"store save failed, message kept for retry: {exc}",
                extra={"event": "worker_fail", "request_id": message.request_id},
            )
            return False

        # 3) ACK — 저장이 끝난 뒤에만 삭제
        self._sqs.delete_message(msg["receipt_handle"])
        metrics.increment(WORKER_PROCESSED_TOTAL)
        latency = (datetime.now(timezone.utc) - message.timestamp).total_seconds()
        metrics.observe(QUEUE_LATENCY_SECONDS, latency)
        logger.info(
            "message acked",
            extra={
                "event": "worker_ack",
                "request_id": message.request_id,
                "latency_ms": round(latency * 1000, 1),
            },
        )
        return True

    def _handle_poison(self, msg: dict, reason: str) -> bool:
        """역직렬화 불가 메시지: 재시도 한도까지는 유지, 초과 시 삭제(향후 DLQ로 대체)."""
        metrics.increment(WORKER_FAILED_TOTAL)
        if msg["receive_count"] > self._settings.sqs_retry_count:
            logger.error(
                f"poison message dropped after {msg['receive_count']} receives "
                f"(DLQ 도입 시 이동 대상): {reason}",
                extra={"event": "worker_poison_drop", "detail": {"message_id": msg["message_id"]}},
            )
            self._sqs.delete_message(msg["receipt_handle"])
        else:
            logger.error(
                f"message validation failed, kept for retry: {reason}",
                extra={"event": "worker_fail", "detail": {"message_id": msg["message_id"]}},
            )
        return False
