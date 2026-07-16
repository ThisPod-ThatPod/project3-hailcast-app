# Simulator DI 조립 — State/Runner/Service 싱글턴을 provider로 주입 (Global Variable 직접 접근 금지)
from functools import lru_cache

from common.aws.client_factory import AwsClientFactory
from common.aws.s3_adapter import S3Adapter
from common.aws.sqs_adapter import SqsAdapter
from common.core.store import FileStore

from config import get_settings
from schedulers.status_scheduler import StatusScheduler
from services.k6_runner import K6Runner
from services.simulator_service import SimulatorService
from services.sqs_inject_service import SqsInjectService
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


# --- SQS 직접 유입 (C3) — call-api와 같은 큐를 바라보는 어댑터를 simulator에도 조립 ---
@lru_cache  # 싱글턴: 프로세스당 1개만 만들어 재사용 (boto3 커넥션 재활용)
def get_sqs_adapter() -> SqsAdapter:
    settings = get_settings()
    return SqsAdapter(
        get_aws_client_factory(),
        queue_name=settings.sqs_queue_name,       # 기본 hailcast-dev-call-queue (공통 설정)
        queue_url=settings.sqs_queue_url,         # URL을 직접 주면 GetQueueUrl 조회 생략
        auto_create=settings.sqs_auto_create_queue,  # LocalStack 전용 — 운영은 IaC가 큐 소유
    )


@lru_cache
def get_sqs_inject_service() -> SqsInjectService:
    # 라우터가 Depends()로 받아가는 진입점 — 어댑터를 꽂아 서비스 완성
    return SqsInjectService(get_sqs_adapter())


@lru_cache
def get_status_scheduler() -> StatusScheduler:
    settings = get_settings()
    return StatusScheduler(get_state(), get_file_store(), settings.status_write_interval_seconds)
