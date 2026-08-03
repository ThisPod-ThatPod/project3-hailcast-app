# Scaling Router — Dashboard 조회용. 위임만 수행.
from fastapi import APIRouter

from common.models.scaling import ScalingCurrentResponse, ScalingStatusResponse

from config import get_settings
from dependencies import get_keda_adapter, get_scaler_service, get_scaling_scheduler

router = APIRouter(prefix="/scaling", tags=["scaling"])


@router.get("/status", response_model=ScalingStatusResponse)
def status() -> ScalingStatusResponse:
    settings = get_settings()
    scheduler = get_scaling_scheduler()
    service = get_scaler_service()
    try:
        current = get_keda_adapter().get_min_replicas()
    except Exception:
        current = None  # K8s 접근 불가 상태에서도 status는 응답한다
    return ScalingStatusResponse(
        scheduler_running=scheduler.is_running,
        interval_seconds=scheduler.interval_seconds,
        keda_enabled=settings.keda_enabled,
        scaledobject=settings.keda_scaledobject_name,
        namespace=settings.keda_namespace,
        current_replicas=current,
        last_predicted_demand=service.last_predicted_demand,
        last_decision=service.last_decision,
        cooldown_seconds=settings.scaling_cooldown_seconds,
        cooldown_remaining_seconds=round(service.cooldown_remaining(), 1),
        last_scaling_at=service.last_scaling_at,
        last_run_at=scheduler.last_run_at,
        last_error=scheduler.last_error,
        run_count=scheduler.run_count,
        failure_count=scheduler.failure_count,
    )


@router.get("/current", response_model=ScalingCurrentResponse)
def current() -> ScalingCurrentResponse:
    return ScalingCurrentResponse(**get_scaler_service().preview())
