# SQLAlchemy engine/session 관리 — Repository는 여기서 만든 Session만 사용한다.
from contextlib import contextmanager

from sqlalchemy import create_engine
from sqlalchemy.orm import Session, sessionmaker

from common.core.logger import get_logger
from common.db.entities import Base

logger = get_logger("db")


class Database:
    def __init__(self, database_url: str):
        # pool_pre_ping: RDS 유휴 연결 끊김 대비
        self._engine = create_engine(database_url, pool_pre_ping=True)
        self._session_factory = sessionmaker(
            bind=self._engine, autoflush=False, expire_on_commit=False
        )

    def init_schema(self) -> None:
        """개발/1차 배포용 create_all (idempotent). 운영 전환 시 마이그레이션 도구로 대체."""
        Base.metadata.create_all(self._engine)
        logger.info("schema ensured", extra={"event": "db_schema_ensured"})

    def session(self) -> Session:
        return self._session_factory()

    @contextmanager
    def session_scope(self):
        """commit/rollback/close를 보장하는 트랜잭션 범위."""
        session = self._session_factory()
        try:
            yield session
            session.commit()
        except Exception:
            session.rollback()
            raise
        finally:
            session.close()
