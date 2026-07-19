# Simulator Router — Frontend 버튼과 1:1 대응. Business Logic은 SimulatorService에 위임.
#
# [복원 2026-07-13] D2 — 6개 엔드포인트를 고정 계약 그대로 유지하기로 확정해서
# backend/frontend-contract/simulator_router.py에서 다시 연결함.
from fastapi import APIRouter, Depends, HTTPException, Query

from common.models.call import SqsInjectResponse
from common.models.status import SimulatorStatus

from config import get_settings
from dependencies import get_simulator_service, get_sqs_inject_service
from services.simulator_service import SimulatorService
from services.sqs_inject_service import SqsInjectService

router = APIRouter(prefix="/simulator", tags=["simulator"])


@router.post("/start", response_model=SimulatorStatus)
async def start(service: SimulatorService = Depends(get_simulator_service)) -> SimulatorStatus:
    return await service.start()


@router.post("/stop", response_model=SimulatorStatus)
async def stop(service: SimulatorService = Depends(get_simulator_service)) -> SimulatorStatus:
    return await service.stop()


@router.post("/increase", response_model=SimulatorStatus)
async def increase(service: SimulatorService = Depends(get_simulator_service)) -> SimulatorStatus:
    return await service.increase()


@router.post("/decrease", response_model=SimulatorStatus)
async def decrease(service: SimulatorService = Depends(get_simulator_service)) -> SimulatorStatus:
    return await service.decrease()


@router.post("/reset", response_model=SimulatorStatus)
async def reset(service: SimulatorService = Depends(get_simulator_service)) -> SimulatorStatus:
    return await service.reset()


@router.get("/status", response_model=SimulatorStatus)
async def status(service: SimulatorService = Depends(get_simulator_service)) -> SimulatorStatus:
    return service.status()


@router.post("/sqs-inject", response_model=SqsInjectResponse)
async def sqs_inject(
    # ?count=N 쿼리 파라미터. 생략하면 1건, 0 이하는 FastAPI가 자동으로 422 처리(ge=1)
    count: int = Query(default=1, ge=1, description="발행할 메시지 수"),
    service: SqsInjectService = Depends(get_sqs_inject_service),
) -> SqsInjectResponse:
    """call-api를 우회해 SQS에 CallMessage를 직접 발행 (C3 — 인프라 데모/테스트용)."""
    # 상한은 env(SQS_INJECT_MAX_COUNT, 기본 100)라 Query(le=...)에 고정할 수 없어 여기서 검증.
    # 입력 검증까지만 라우터 몫이고, 발행 로직은 전부 Service에 위임한다.
    max_count = get_settings().sqs_inject_max_count
    if count > max_count:
        raise HTTPException(status_code=422, detail=f"count must be <= {max_count}")
    return service.inject(count)
