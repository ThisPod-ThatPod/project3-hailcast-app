# CallService — 콜 접수 Business Logic (Router에는 로직을 두지 않는다)
import uuid
from datetime import datetime, timezone

from common.aws.sqs_adapter import SqsAdapter
from common.core.constants import CallStatus
from common.core.logger import get_logger
from common.core.metrics import QUEUE_PUBLISH_TOTAL, REQUEST_TOTAL, metrics
from common.models.call import CallMessage, CallRequest, CallResponse, CallStatusResponse

from repositories.call_repository import CallRepository

logger = get_logger("call_service")


class CallService:
    def __init__(self, sqs_adapter: SqsAdapter):
        self._sqs = sqs_adapter

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

        logger.info(
            "call queued",
            extra={
                "event": "queue_publish",
                "request_id": request_id,
                "detail": {"message_id": message_id, "zone_id": request.zone_id},
            },
        )
        return CallResponse(
            accepted=True,
            request_id=request_id,
            created_at=now,
            status=CallStatus.QUEUED,
        )


class CallQueryService:
    """콜 처리 상태 조회 (읽기 전용)."""

    def __init__(self, repository: CallRepository):
        self._repository = repository

    def get_status(self, request_id: str) -> CallStatusResponse | None:
        call = self._repository.get_by_call_id(request_id)
        if call is None:
            return None
        return CallStatusResponse(
            request_id=call.call_id,
            status=call.status,
            requested_at=call.requested_at,
            processed_at=call.processed_at,
        )