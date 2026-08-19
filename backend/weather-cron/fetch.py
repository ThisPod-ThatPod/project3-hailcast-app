# 8.4 날씨 수집 (CronJob 유력)
# Entry Point — 두 가지 실행 모드:
#   python fetch.py            : FastAPI(:8002) + 백그라운드 Scheduler (Deployment 모드)
#   python fetch.py --once     : 1회 수집 후 종료 (K8s CronJob 모드)
#
# [2026-08-19 CI 검증용 · 기능 영향 없음] GitHub App 설치 토큰으로 이관한 뒤(PR#51)
# manifests 태그 자동 갱신이 실제로 도는지 확인하기 위한 단일 서비스 트리거.
# weather-cron 만 골랐다 — detect 가 backend/weather-cron/ 변경을 이 서비스 하나로만
# 판정하므로, 성공하면 manifests apps/weather-cron/deployment.yaml 의 태그 '한 줄만'
# 바뀐다. 6종이 한꺼번에 움직이는 build.yml 변경과 달리 결과 해석에 여지가 없다.
# 검증이 끝나면 이 주석 블록은 지워도 된다.
import asyncio
import os
import sys
from contextlib import asynccontextmanager

os.environ.setdefault("SERVICE_NAME", "weather-cron")

from fastapi import FastAPI

from common.core.exception_handlers import register_exception_handlers
from common.core.logger import configure_logging, get_logger

from config import get_settings
from dependencies import get_weather_scheduler
from routers.weather_router import router as weather_router

settings = get_settings()
configure_logging(settings.log_level)
logger = get_logger("weather_cron")


@asynccontextmanager
async def lifespan(app: FastAPI):
    scheduler = get_weather_scheduler()
    task = asyncio.create_task(scheduler.run_loop(), name="weather-scheduler")
    yield
    scheduler.stop()
    task.cancel()


app = FastAPI(title="HailCast Weather Collector", version="0.1.0", lifespan=lifespan)
register_exception_handlers(app)
app.include_router(weather_router)


@app.get("/healthz")
def healthz() -> dict:
    return {"status": "ok"}


async def run_once() -> None:
    """CronJob 모드 — 1회 수집."""
    await get_weather_scheduler().run_one_shot()


if __name__ == "__main__":
    if "--once" in sys.argv:
        asyncio.run(run_once())
    else:
        import uvicorn

        uvicorn.run(app, host="0.0.0.0", port=8002)
