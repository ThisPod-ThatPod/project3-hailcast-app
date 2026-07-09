# Worker DI 조립 — FastAPI가 없는 프로세스이므로 수동 팩토리로 동일 원칙 적용
from functools import lru_cache

from common.aws.client_factory import AwsClientFactory
from common.aws.sqs_adapter import SqsAdapter
from common.db.database import Database

from config import get_settings
from services.state_manager import StateManager
from services.worker_service import WorkerService


@lru_cache
def get_database() -> Database:
    return Database(get_settings().database_url)


@lru_cache
def get_sqs_adapter() -> SqsAdapter:
    settings = get_settings()
    factory = AwsClientFactory(settings.aws_region, settings.aws_endpoint_url)
    return SqsAdapter(
        factory,
        queue_name=settings.sqs_queue_name,
        queue_url=settings.sqs_queue_url,
        auto_create=settings.sqs_auto_create_queue,
    )


def build_worker_service() -> WorkerService:
    return WorkerService(
        sqs=get_sqs_adapter(),
        database=get_database(),
        state_manager=StateManager(),
        settings=get_settings(),
    )
