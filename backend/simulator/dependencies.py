# Simulator DI 조립 — State/Runner/Service 싱글턴을 provider로 주입 (Global Variable 직접 접근 금지)
from functools import lru_cache

from common.aws.client_factory import AwsClientFactory
from common.aws.s3_adapter import S3Adapter
from common.core.store import FileStore

from config import get_settings
from schedulers.status_scheduler import StatusScheduler
from services.k6_runner import K6Runner
from services.simulator_service import SimulatorService
from services.traffic_state import SimulatorState


@lru_cache
def get_state() -> SimulatorState:
    settings = get_settings()
    return SimulatorState(min_tps=settings.min_tps, max_tps=settings.max_tps)


@lru_cache
def get_k6_runner() -> K6Runner:
    settings = get_settings()
    return K6Runner(settings.call_api_url, settings.k6_binary)


@lru_cache
def get_simulator_service() -> SimulatorService:
    return SimulatorService(get_state(), get_k6_runner(), get_settings())


@lru_cache
def get_aws_client_factory() -> AwsClientFactory:
    settings = get_settings()
    return AwsClientFactory(settings.aws_region, settings.aws_endpoint_url)


@lru_cache
def get_s3_adapter() -> S3Adapter:
    settings = get_settings()
    return S3Adapter(get_aws_client_factory(), bucket=settings.s3_bucket, auto_create=settings.s3_auto_create_bucket)


@lru_cache
def get_file_store() -> FileStore:
    settings = get_settings()
    s3_adapter = get_s3_adapter() if settings.json_store_backend == "s3" else None
    return FileStore(settings.json_store_backend, settings.json_store_local_dir, s3_adapter)


@lru_cache
def get_status_scheduler() -> StatusScheduler:
    settings = get_settings()
    return StatusScheduler(get_state(), get_file_store(), settings.status_write_interval_seconds)
