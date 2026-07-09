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
            pickup_lat=req.pickup.lat,
            pickup_lon=req.pickup.lon,
            dest_lat=req.destination.lat,
            dest_lon=req.destination.lon,
            zone_id=req.zone_id,
            passenger_count=req.passenger_count,
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
