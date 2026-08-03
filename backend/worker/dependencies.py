# Worker DI 조립 — FastAPI가 없는 프로세스이므로 수동 팩토리로 동일 원칙 적용
from functools import lru_cache

from common.aws.client_factory import AwsClientFactory
from common.aws.sqs_adapter import SqsAdapter
from common.db.database import Database

from config import get_settings
from services.state_manager import StateManager
from services.worker_service import WorkerService


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
    settings = get_settings()
    return Database(settings.database_url)


@lru_cache
def get_state_manager() -> StateManager:
    return StateManager()


def build_worker_service() -> WorkerService:
    return WorkerService(
        sqs=get_sqs_adapter(),
        database=get_database(),
        state_manager=get_state_manager(),
        settings=get_settings(),
    )
