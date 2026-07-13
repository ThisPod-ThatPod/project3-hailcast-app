# Repository 공통 베이스 — DB 예외를 DatabaseError로 래핑해 상위 Layer로 전달
from sqlalchemy.exc import SQLAlchemyError
from sqlalchemy.orm import Session

from common.core.exceptions import DatabaseError


class BaseRepository:
    def __init__(self, session: Session):
        self._session = session

    def _wrap(self, operation: str, exc: SQLAlchemyError) -> DatabaseError:
        return DatabaseError(
            f"database {operation} failed: {exc}",
            detail={"operation": operation},
        )
