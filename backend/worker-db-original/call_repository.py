# [격리] 원래 인프라 아키텍처 다이어그램("워커 Pod: 큐 소비 → RDS 기록")이 요구하는
# RDS 기반 구현. 지금은 안 쓰인다 — 실제로 도는 건 worker/services/worker_service.py의
# FileStore 버전(C, 2026-07-13). RDS가 실제로 준비되고 필요해지면 이 폴더 내용을
# worker/repositories/call_repository.py 등 원래 자리로 되돌리고 dependencies.py만
# Database 기반으로 바꾸면 된다 — 로직 자체는 최신 CallRequest 스키마(B1)에 맞춰 고쳐둠.
#
# Worker용 Call Repository — 콜 저장/상태 갱신 (쓰기 담당)
from sqlalchemy import select
from sqlalchemy.exc import SQLAlchemyError

from common.db.base_repository import BaseRepository
from common.db.entities import Call
from common.models.call import CallMessage


class CallRepository(BaseRepository):
    def get_by_call_id(self, call_id: str) -> Call | None:
        try:
            stmt = select(Call).where(Call.call_id == call_id)
            return self._session.execute(stmt).scalar_one_or_none()
        except SQLAlchemyError as exc:
            raise self._wrap("select_call", exc) from exc

    def insert_from_message(self, message: CallMessage, status: str, receive_count: int) -> Call:
        """SQS 메시지를 Call 레코드로 저장한다 (commit은 Service의 session_scope가 수행)."""
        req = message.data
        call = Call(
            call_id=message.request_id,
            user_id=req.user_id,
            pickup=req.pickup,
            destination=req.destination,
            source=req.source,
            requested_at=req.requested_at or message.timestamp,
            status=status,
            message_version=message.version,
            enqueued_at=message.timestamp,
            receive_count=receive_count,
        )
        try:
            self._session.add(call)
            self._session.flush()
            return call
        except SQLAlchemyError as exc:
            raise self._wrap("insert_call", exc) from exc
