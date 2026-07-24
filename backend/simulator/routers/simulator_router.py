# Simulator Router — Frontend 버튼과 1:1 대응. Business Logic은 SimulatorService에 위임.
#
# [복원 2026-07-13] D2 — 6개 엔드포인트(start/stop/increase/decrease/reset/status)를
# 고정 계약 그대로 유지하기로 확정해서 backend/frontend-contract/simulator_router.py에서
# 다시 연결함.
from fastapi import APIRouter, Depends, Request, Response

from common.models.status import SimulatorStatus

from dependencies import get_simulator_service
from services.simulator_service import SimulatorService

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


# [B-1, 2026-07-24] k6(같은 파드의 서브프로세스) 전용 내부 엔드포인트 — 정식 6개 계약과 별개.
# frontend/외부에서 부를 대상 아님. k6가 call-api를 직접 안 때리고 여기를 거쳐가게 해서,
# simulator가 성공/실패를 그 자리에서 카운트한다(traffic_state.py record_success/record_fail).
@router.post("/_relay", include_in_schema=False)
async def relay(request: Request, service: SimulatorService = Depends(get_simulator_service)) -> Response:
    body = await request.body()
    status_code, content = await service.relay_call(body)
    return Response(content=content, status_code=status_code, media_type="application/json")
