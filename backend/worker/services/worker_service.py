# WorkerService — SQS 소비 Business Logic
# 흐름: Polling → Deserialize → Validation → RDS Save → ACK(delete)
# 오류 시 메시지를 삭제하지 않아 Visibility Timeout 후 재수신(재시도)된다. (향후 DLQ 연계)
import time
from datetime import datetime, timezone

from pydantic import ValidationError

from common.aws.sqs_adapter import SqsAdapter
from common.core.constants import CallStatus
from common.core.exceptions import AwsError, DatabaseError
from common.core.logger import get_logger
from common.core.metrics import (
    QUEUE_LATENCY_SECONDS,
    WORKER_FAILED_TOTAL,
    WORKER_PROCESSED_TOTAL,
    metrics,
)
from common.db.call_repository import CallRepository
from common.db.database import Database
from common.models.call import CallMessage

from config import WorkerSettings
from services.state_manager import StateManager

logger = get_logger("worker_service")


class WorkerService:
    def __init__(
        self,
        sqs: SqsAdapter,
        database: Database,
        state_manager: StateManager,
        settings: WorkerSettings,
    ):
        self._sqs = sqs
        self._db = database
        self._state = state_manager
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
            except AwsError as exc:
                # 큐 접근 자체가 실패하면 잠시 대기 후 재시도 (루프는 죽지 않는다)
                logger.error(
                    f"queue polling failed: {exc.message}",
                    extra={"event": "poll_error"},
                )
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

        # 2) Business Logic + DB Save
        try:
            with self._db.session_scope() as session:
                repository = CallRepository(session)
                existing = repository.get_by_call_id(message.request_id)
                if existing is not None:
                    # 재수신(visibility timeout 만료 등) — 멱등 처리
                    existing.receive_count = receive_count
                    if existing.status != CallStatus.DONE:
                        self._state.mark_done(existing)
                    logger.info(
                        "duplicate delivery, already saved",
                        extra={"event": "worker_duplicate", "request_id": message.request_id},
                    )
                else:
                    call = repository.insert_from_message(
                        message, status=CallStatus.PROCESSING, receive_count=receive_count
                    )
                    self._state.mark_done(call)
                    logger.info(
                        "call saved",
                        extra={
                            "event": "worker_save",
                            "request_id": message.request_id,
                            "status": str(CallStatus.DONE),
                        },
                    )
        except DatabaseError as exc:
            # 일시적 장애 가능성 — 메시지를 삭제하지 않고 재시도에 맡긴다
            metrics.increment(WORKER_FAILED_TOTAL)
            logger.error(
                f"db save failed, message kept for retry: {exc.message}",
                extra={"event": "worker_fail", "request_id": message.request_id},
            )
            return False

        # 3) ACK — 저장이 커밋된 뒤에만 삭제
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
