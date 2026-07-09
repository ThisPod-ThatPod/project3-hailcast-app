# DI Provider — Service/Adapter/Repository는 여기서만 조립한다 (직접 생성 금지)
from functools import lru_cache
from typing import Iterator

from fastapi import Depends
from sqlalchemy.orm import Session

from common.aws.client_factory import AwsClientFactory
from common.aws.sqs_adapter import SqsAdapter
from common.db.database import Database

from config import get_settings
from repositories.call_repository import CallRepository
from services.call_service import CallQueryService, CallService


@lru_cache
def get_aws_factory() -> AwsClientFactory:
    settings = get_settings()
    return AwsClientFactory(settings.aws_region, settings.aws_endpoint_url)


@lru_cache
def get_sqs_adapter() -> SqsAdapter:
    settings = get_settings()
    return SqsAdapter(
        get_aws_factory(),
        queue_name=settings.sqs_queue_name,
        queue_url=settings.sqs_queue_url,
        auto_create=settings.sqs_auto_create_queue,
    )


@lru_cache
def get_database() -> Database:
    return Database(get_settings().database_url)


def get_db_session() -> Iterator[Session]:
    session = get_database().session()
    try:
        yield session
    finally:
        session.close()


def get_call_service(
    sqs: SqsAdapter = Depends(get_sqs_adapter),
) -> CallService:
    return CallService(sqs)


def get_call_query_service(
    session: Session = Depends(get_db_session),
) -> CallQueryService:
    return CallQueryService(CallRepository(session))
