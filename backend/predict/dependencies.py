# Predict DI 조립 — ModelLoader/S3/Service/Scheduler 싱글턴 provider
from functools import lru_cache

from common.aws.client_factory import AwsClientFactory
from common.aws.s3_adapter import S3Adapter
from common.aws.sqs_adapter import SqsAdapter
from common.core.store import FileStore

from adapters.inmemory_keda_adapter import InMemoryKedaAdapter
from adapters.inmemory_node_adapter import InMemoryNodeAdapter
from adapters.keda_adapter import KedaAdapter
from adapters.kubernetes_keda_adapter import KubernetesKedaAdapter
from adapters.kubernetes_node_adapter import KubernetesNodeAdapter
from adapters.node_adapter import NodeAdapter
from config import get_settings
from ml_runtime.model_loader import ModelLoader
from schedulers.backup_scheduler import BackupScheduler
from schedulers.forecast_scheduler import ForecastScheduler
from schedulers.scaling_scheduler import ScalingScheduler
from schedulers.traffic_scheduler import TrafficScheduler
from services.pod_forecast_service import PodForecastService
from services.prediction_reader import FilePredictionReader, PredictionReader
from services.prediction_service import PredictionService
from services.scaler_service import ScalerService
from services.scaling_decision_engine import ScalingDecisionEngine
from services.traffic_aggregator_service import TrafficAggregatorService


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
def get_file_store() -> FileStore:
    settings = get_settings()
    s3_adapter = get_s3_adapter() if settings.json_store_backend == "s3" else None
    return FileStore(settings.json_store_backend, settings.json_store_local_dir, s3_adapter)


@lru_cache
def get_prediction_service() -> PredictionService:
    return PredictionService(get_model_loader(), get_file_store(), get_settings())


@lru_cache
def get_forecast_scheduler() -> ForecastScheduler:
    settings = get_settings()
    return ForecastScheduler(
        get_prediction_service(),
        settings.prediction_interval_seconds,
        align_offset_seconds=settings.prediction_align_offset_seconds,
    )


# ---------- A1: 트래픽 집계 ----------
@lru_cache
def get_traffic_aggregator_service() -> TrafficAggregatorService:
    settings = get_settings()
    return TrafficAggregatorService(get_file_store(), settings.traffic_json_key)


@lru_cache
def get_traffic_scheduler() -> TrafficScheduler:
    settings = get_settings()
    return TrafficScheduler(get_traffic_aggregator_service(), settings.traffic_aggregate_interval_seconds)


# ---------- Predictive Scaling ----------
@lru_cache
def get_prediction_reader() -> PredictionReader:
    # Mock 교체 지점 — 테스트/Simulator 연동 시 여기서 다른 Reader 구현체를 반환
    settings = get_settings()
    return FilePredictionReader(get_file_store(), settings.prediction_s3_prefix)


@lru_cache
def get_keda_adapter() -> KedaAdapter:
    settings = get_settings()
    if settings.keda_enabled:
        return KubernetesKedaAdapter(
            settings.keda_namespace, settings.keda_scaledobject_name, settings.worker_deployment_name
        )
    # 로컬(docker-compose)·테스트: dry-run InMemory Adapter
    return InMemoryKedaAdapter(initial_replicas=settings.scaling_min_replicas)


@lru_cache
def get_decision_engine() -> ScalingDecisionEngine:
    settings = get_settings()
    return ScalingDecisionEngine(
        settings.scaling_demand_per_pod,
        settings.scaling_buffer_pods,
        settings.scaling_min_replicas,
        settings.scaling_max_replicas,
    )


@lru_cache
def get_scaler_service() -> ScalerService:
    return ScalerService(
        get_prediction_reader(),
        get_decision_engine(),
        get_keda_adapter(),
        get_file_store(),
        get_settings(),
    )


@lru_cache
def get_scaling_scheduler() -> ScalingScheduler:
    return ScalingScheduler(get_scaler_service(), get_settings().scaling_interval_seconds)


# ---------- Pod 이력 백업 (Dashboard 예측-실제 파드 그래프) ----------
@lru_cache
def get_pod_forecast_service() -> PodForecastService:
    return PodForecastService(
        get_file_store(),
        get_prediction_reader(),
        get_decision_engine(),
        get_keda_adapter(),
        get_settings(),
    )


@lru_cache
def get_backup_scheduler() -> BackupScheduler:
    return BackupScheduler(get_pod_forecast_service(), get_settings().backup_interval_seconds)


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
def get_node_adapter() -> NodeAdapter:
    settings = get_settings()
    if settings.k8s_nodes_enabled:
        return KubernetesNodeAdapter()
    # 로컬(docker-compose, K8s 없음): 고정값 InMemory Adapter
    return InMemoryNodeAdapter(fixed_count=settings.k8s_nodes_stub_count)


@lru_cache
def get_dashboard_service():
    from services.dashboard_service import DashboardService

    return DashboardService(get_file_store(), get_keda_adapter(), get_node_adapter(), get_settings())


@lru_cache
def get_health_service():
    from services.health_service import HealthService

    return HealthService(
        get_file_store(),
        get_sqs_adapter(),
        get_s3_adapter(),
        [get_forecast_scheduler(), get_scaling_scheduler(), get_backup_scheduler(), get_traffic_scheduler()],
        get_settings(),
    )
