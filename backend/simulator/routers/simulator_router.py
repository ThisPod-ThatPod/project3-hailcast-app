# Simulator Router — Frontend 버튼과 1:1 대응. Business Logic은 SimulatorService에 위임.
#
# [복원 2026-07-13] D2 — 6개 엔드포인트를 고정 계약 그대로 유지하기로 확정해서
# backend/frontend-contract/simulator_router.py에서 다시 연결함.
from fastapi import APIRouter, Depends

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
