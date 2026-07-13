# CallService — 콜 접수 Business Logic (Router에는 로직을 두지 않는다)
import uuid
from datetime import datetime, timezone

from common.aws.sqs_adapter import SqsAdapter
from common.core.constants import CALL_RECORD_PREFIX, CallStatus
from common.core.logger import get_logger
from common.core.metrics import QUEUE_PUBLISH_TOTAL, REQUEST_TOTAL, metrics
from common.core.store import FileStore
from common.models.call import CallMessage, CallRequest, CallResponse, CallStatusResponse

from services.traffic_counter import TrafficCounter

logger = get_logger("call_service")


class CallService:
    def __init__(self, sqs_adapter: SqsAdapter, traffic_counter: TrafficCounter):
        self._sqs = sqs_adapter
        self._traffic_counter = traffic_counter

    def accept_call(self, request: CallRequest) -> CallResponse:
        """Request 접수 → Queue Message 생성 → SQS 발행 → 즉시 응답 생성."""
        metrics.increment(REQUEST_TOTAL)
        now = datetime.now(timezone.utc)
        request_id = str(uuid.uuid4())

        if request.requested_at is None:
            request = request.model_copy(update={"requested_at": now})

        message = CallMessage(request_id=request_id, timestamp=now, data=request)
        message_id = self._sqs.send_message(message.to_body())
        metrics.increment(QUEUE_PUBLISH_TOTAL)
        self._traffic_counter.record()  # A1 — 트래픽 집계용 카운트

        logger.info(
            "call queued",
            extra={
                "event": "queue_publish",
                "request_id": request_id,
                "detail": {"message_id": message_id, "source": request.source},
            },
        )
        return CallResponse(
            accepted=True,
            request_id=request_id,
            created_at=now,
            status=CallStatus.QUEUED,
        )


class CallQueryService:
    """콜 처리 상태 조회 (읽기 전용). worker(C)가 FileStore에 쓴 calls/<id>.json을 읽는다."""

    def __init__(self, store: FileStore):
        self._store = store

    def get_status(self, request_id: str) -> CallStatusResponse | None:
        body = self._store.read_json(f"{CALL_RECORD_PREFIX}{request_id}.json")
        if body is None:
            return None
        return CallStatusResponse(
            request_id=body["call_id"],
            status=body["status"],
            requested_at=body.get("requested_at"),
            processed_at=body.get("processed_at"),
        )
