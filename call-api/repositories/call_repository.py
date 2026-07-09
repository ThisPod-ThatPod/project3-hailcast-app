# Call API용 Repository — 상태 조회 전용 (쓰기는 Worker가 담당)
from sqlalchemy import select
from sqlalchemy.exc import SQLAlchemyError

from common.db.base_repository import BaseRepository
from common.db.entities import Call


class CallRepository(BaseRepository):
    def get_by_call_id(self, call_id: str) -> Call | None:
        try:
            stmt = select(Call).where(Call.call_id == call_id)
            return self._session.execute(stmt).scalar_one_or_none()
        except SQLAlchemyError as exc:
            raise self._wrap("select_call", exc) from exc
