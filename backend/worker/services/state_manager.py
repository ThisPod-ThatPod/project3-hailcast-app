# State Manager — 콜 상태 전이 규칙을 한곳에서 관리 (DB가 상태의 원본)
from datetime import datetime, timezone

from common.core.constants import CallStatus
from common.core.logger import get_logger
from common.db.entities import Call

logger = get_logger("state_manager")

# 허용되는 상태 전이 (그 외 전이는 버그로 간주하고 로그만 남긴다)
_ALLOWED_TRANSITIONS: dict[str, set[str]] = {
    CallStatus.QUEUED: {CallStatus.PROCESSING, CallStatus.FAILED},
    CallStatus.PROCESSING: {CallStatus.DONE, CallStatus.FAILED},
    CallStatus.FAILED: {CallStatus.PROCESSING},  # 재처리 허용
    CallStatus.DONE: set(),
}


class StateManager:
    def transition(self, call: Call, new_status: CallStatus) -> None:
        current = call.status
        if new_status not in _ALLOWED_TRANSITIONS.get(current, set()):
            logger.warning(
                f"invalid state transition {current} -> {new_status}",
                extra={"event": "invalid_transition", "request_id": call.call_id},
            )
        call.status = new_status
        if new_status == CallStatus.DONE:
            call.processed_at = datetime.now(timezone.utc)

    def mark_done(self, call: Call) -> None:
        self.transition(call, CallStatus.DONE)

    def mark_failed(self, call: Call) -> None:
        self.transition(call, CallStatus.FAILED)
