# Worker DI 조립 — FastAPI가 없는 프로세스이므로 수동 팩토리로 동일 원칙 적용
from functools import lru_cache

from common.aws.client_factory import AwsClientFactory
from common.aws.s3_adapter import S3Adapter
from common.aws.sqs_adapter import SqsAdapter
from common.core.store import FileStore

from config import get_settings
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
def get_s3_adapter() -> S3Adapter:
    settings = get_settings()
    return S3Adapter(get_aws_factory(), bucket=settings.s3_bucket, auto_create=settings.s3_auto_create_bucket)


@lru_cache
def get_file_store() -> FileStore:
    settings = get_settings()
    s3_adapter = get_s3_adapter() if settings.json_store_backend == "s3" else None
    return FileStore(settings.json_store_backend, settings.json_store_local_dir, s3_adapter)


def build_worker_service() -> WorkerService:
    return WorkerService(sqs=get_sqs_adapter(), store=get_file_store(), settings=get_settings())
