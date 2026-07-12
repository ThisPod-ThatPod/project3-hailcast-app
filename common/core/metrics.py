# Metrics Stub — 이번 Part는 인메모리 카운터만. 향후 prometheus_client Counter/Histogram으로 교체.
# 계측 지점(호출부)은 그대로 두고 이 모듈 내부 구현만 바꾸면 되도록 이름을 고정한다.
import threading
from collections import defaultdict

# 지표 이름 상수 (지시서 요구 지표)
REQUEST_TOTAL = "request_total"
QUEUE_PUBLISH_TOTAL = "queue_publish_total"
WORKER_PROCESSED_TOTAL = "worker_processed_total"
WORKER_FAILED_TOTAL = "worker_failed_total"
QUEUE_LATENCY_SECONDS = "queue_latency_seconds"

# Simulator 지표
TRAFFIC_GENERATED_TOTAL = "traffic_generated_total"
TRAFFIC_FAILED_TOTAL = "traffic_failed_total"
CURRENT_TPS = "current_tps"
GENERATOR_RUNNING = "generator_running"
GENERATION_LATENCY_SECONDS = "generation_latency_seconds"

# Weather 지표
WEATHER_REQUEST_TOTAL = "weather_request_total"
WEATHER_SUCCESS_TOTAL = "weather_success_total"
WEATHER_FAILURE_TOTAL = "weather_failure_total"
WEATHER_REQUEST_LATENCY_SECONDS = "weather_request_latency_seconds"
LATEST_WEATHER_TIMESTAMP = "latest_weather_timestamp"

# Prediction 지표
PREDICTION_TOTAL = "prediction_total"
PREDICTION_FAILURE_TOTAL = "prediction_failure_total"
PREDICTION_DURATION_SECONDS = "prediction_duration_seconds"
PREDICTION_LATEST_VALUE = "predicted_taxi_demand"   # 네이밍규약서 §8 — KEDA/Prometheus 계약 지표명

# Scaling 지표
SCALING_TOTAL = "scaling_total"
SCALE_UP_TOTAL = "scale_up_total"
SCALE_DOWN_TOTAL = "scale_down_total"
CURRENT_REPLICA = "current_replica"
LAST_SCALING_TIMESTAMP = "last_scaling_timestamp"


class MetricsRegistry:
    """스레드 안전 인메모리 지표 저장소 (Prometheus 교체 전 Stub)."""

    def __init__(self) -> None:
        self._lock = threading.Lock()
        self._counters: dict[str, float] = defaultdict(float)
        self._observations: dict[str, list[float]] = defaultdict(list)

    def increment(self, name: str, value: float = 1.0) -> None:
        with self._lock:
            self._counters[name] += value

    def observe(self, name: str, value: float) -> None:
        with self._lock:
            samples = self._observations[name]
            samples.append(value)
            # Stub 메모리 보호: 최근 1000개만 유지
            if len(samples) > 1000:
                del samples[: len(samples) - 1000]

    def snapshot(self) -> dict:
        with self._lock:
            summary = {
                name: {
                    "count": len(v),
                    "avg": (sum(v) / len(v)) if v else 0.0,
                }
                for name, v in self._observations.items()
            }
            return {"counters": dict(self._counters), "observations": summary}


metrics = MetricsRegistry()
