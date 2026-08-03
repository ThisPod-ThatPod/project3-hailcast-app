# Call Repository — worker(쓰기)와 call-api(읽기)가 함께 쓰는 공유 위치.
# common/db/ 밑에 두는 이유: 서비스별 디렉토리(worker/, call-api/)는 서로 import할 수
# 없어서, 두 서비스가 같이 참조해야 하는 이 리포지토리는 이미 공유되는 common 패키지
# 안에 둬야 한다(Call 엔티티도 이미 common/db/entities.py에 있음).
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

    def get_recent(self, limit: int) -> list[Call]:
        """RDS 테이블 뷰어용 — 최근 접수된 콜 최대 limit개 (최신순)."""
        try:
            stmt = select(Call).order_by(Call.requested_at.desc()).limit(limit)
            return list(self._session.execute(stmt).scalars())
        except SQLAlchemyError as exc:
            raise self._wrap("select_recent_calls", exc) from exc

    def insert_from_message(self, message: CallMessage, status: str, receive_count: int) -> Call:
        """SQS 메시지를 Call 레코드로 저장한다 (commit은 Service의 session_scope가 수행)."""
        req = message.data
        call = Call(
            call_id=message.request_id,
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
