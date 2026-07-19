# DI Provider — Service/Adapter는 여기서만 조립한다 (직접 생성 금지)
from functools import lru_cache

from fastapi import Depends

from common.aws.client_factory import AwsClientFactory
from common.aws.s3_adapter import S3Adapter
from common.aws.sqs_adapter import SqsAdapter
from common.core.store import FileStore
from common.db.database import Database

from config import get_settings
from schedulers.traffic_flush_scheduler import TrafficFlushScheduler
from services.call_service import CallQueryService, CallService
from services.traffic_counter import TrafficCounter


@lru_cache
def get_aws_factory() -> AwsClientFactory:
    settings = get_settings()
    # D3: TPS 200을 실제로 받아내려면 boto3 기본 커넥션 풀(10)로는 부족하다.
    return AwsClientFactory(settings.aws_region, settings.aws_endpoint_url, settings.aws_max_pool_connections)


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


@lru_cache
def get_database() -> Database:
    settings = get_settings()
    return Database(settings.database_url)


@lru_cache
def get_traffic_counter() -> TrafficCounter:
    return TrafficCounter(get_file_store())


@lru_cache
def get_traffic_flush_scheduler() -> TrafficFlushScheduler:
    settings = get_settings()
    return TrafficFlushScheduler(get_traffic_counter(), settings.traffic_flush_interval_seconds)


def get_call_service(
    sqs: SqsAdapter = Depends(get_sqs_adapter),
) -> CallService:
    return CallService(sqs, get_traffic_counter())


def get_call_query_service() -> CallQueryService:
    return CallQueryService(get_database())
