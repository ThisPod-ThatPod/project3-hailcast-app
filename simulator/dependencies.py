# Simulator DI 조립 — State/Service 싱글턴을 provider로 주입 (Global Variable 직접 접근 금지)
from functools import lru_cache

from config import get_settings
from services.simulator_service import SimulatorService
from services.traffic_state import SimulatorState


@lru_cache
def get_state() -> SimulatorState:
    settings = get_settings()
    return SimulatorState(min_tps=settings.min_tps, max_tps=settings.max_tps)


@lru_cache
def get_simulator_service() -> SimulatorService:
    return SimulatorService(get_state(), get_settings())
