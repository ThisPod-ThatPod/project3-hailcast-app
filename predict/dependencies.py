# Predict DI 조립 — ModelLoader/S3/Service/Scheduler 싱글턴 provider
from functools import lru_cache
from typing import Iterator

from sqlalchemy.orm import Session

from common.aws.client_factory import AwsClientFactory
from common.aws.s3_adapter import S3Adapter
from common.aws.sqs_adapter import SqsAdapter
from common.db.database import Database

from adapters.inmemory_keda_adapter import InMemoryKedaAdapter
from adapters.keda_adapter import KedaAdapter
from adapters.kubernetes_keda_adapter import KubernetesKedaAdapter
from config import get_settings
from ml_runtime.model_loader import ModelLoader
from schedulers.forecast_scheduler import ForecastScheduler
from schedulers.scaling_scheduler import ScalingScheduler
from services.prediction_reader import PredictionReader, S3PredictionReader
from services.prediction_service import PredictionService
from services.scaler_service import ScalerService
from services.scaling_decision_engine import ScalingDecisionEngine, parse_rules


@lru_cache
def get_database() -> Database:
    return Database(get_settings().database_url)


@lru_cache
def get_s3_adapter() -> S3Adapter:
    settings = get_settings()
    factory = AwsClientFactory(settings.aws_region, settings.aws_endpoint_url)
    return S3Adapter(factory, bucket=settings.s3_bucket, auto_create=settings.s3_auto_create_bucket)


@lru_cache
def get_model_loader() -> ModelLoader:
    settings = get_settings()
    return ModelLoader(get_s3_adapter(), settings.model_s3_prefix, settings.model_cache_dir)


@lru_cache
def get_prediction_service() -> PredictionService:
    return PredictionService(get_model_loader(), get_s3_adapter(), get_database(), get_settings())


@lru_cache
def get_forecast_scheduler() -> ForecastScheduler:
    return ForecastScheduler(get_prediction_service(), get_settings().prediction_interval_seconds)


def get_db_session() -> Iterator[Session]:
    session = get_database().session()
    try:
        yield session
    finally:
        session.close()


# ---------- Predictive Scaling ----------
@lru_cache
def get_prediction_reader() -> PredictionReader:
    # Mock 교체 지점 — 테스트/Simulator 연동 시 여기서 다른 Reader 구현체를 반환
    settings = get_settings()
    return S3PredictionReader(get_s3_adapter(), settings.prediction_s3_prefix)


@lru_cache
def get_keda_adapter() -> KedaAdapter:
    settings = get_settings()
    if settings.keda_enabled:
        return KubernetesKedaAdapter(settings.keda_namespace, settings.keda_scaledobject_name)
    # 로컬(docker-compose)·테스트: dry-run InMemory Adapter
    return InMemoryKedaAdapter(initial_replicas=settings.scaling_min_replicas)


@lru_cache
def get_decision_engine() -> ScalingDecisionEngine:
    settings = get_settings()
    return ScalingDecisionEngine(
        parse_rules(settings.scaling_rules),
        settings.scaling_min_replicas,
        settings.scaling_max_replicas,
    )


@lru_cache
def get_scaler_service() -> ScalerService:
    return ScalerService(
        get_prediction_reader(),
        get_decision_engine(),
        get_keda_adapter(),
        get_database(),
        get_settings(),
    )


@lru_cache
def get_scaling_scheduler() -> ScalingScheduler:
    return ScalingScheduler(get_scaler_service(), get_settings().scaling_interval_seconds)


# ---------- Dashboard / Health ----------
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


@lru_cache
def get_dashboard_service():
    from services.dashboard_service import DashboardService

    return DashboardService(get_database(), get_sqs_adapter(), get_scaler_service(), get_settings())


@lru_cache
def get_health_service():
    from services.health_service import HealthService

    return HealthService(
        get_database(),
        get_sqs_adapter(),
        get_s3_adapter(),
        [get_forecast_scheduler(), get_scaling_scheduler()],
        get_settings(),
    )
