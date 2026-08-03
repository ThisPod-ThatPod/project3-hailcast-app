# 공통 예외 계층 — Layer별 예외를 구분해 공통 핸들러에서 일관 처리
class AppError(Exception):
    """모든 애플리케이션 예외의 베이스."""

    status_code = 500
    code = "APP_ERROR"

    def __init__(self, message: str, *, detail: dict | None = None):
        super().__init__(message)
        self.message = message
        self.detail = detail or {}


class AwsError(AppError):
    """AWS SDK 호출 실패 (SQS/S3/CloudWatch...). Adapter에서만 발생시킨다."""

    status_code = 502
    code = "AWS_ERROR"

    def __init__(self, message: str, *, service: str, operation: str, detail: dict | None = None):
        super().__init__(message, detail=detail)
        self.service = service
        self.operation = operation


class DatabaseError(AppError):
    """DB 접근 실패. Repository에서만 발생시킨다."""

    status_code = 503
    code = "DATABASE_ERROR"


class MessageValidationError(AppError):
    """Queue 메시지 역직렬화/검증 실패. 재시도해도 성공할 수 없는 poison message."""

    status_code = 400
    code = "MESSAGE_VALIDATION_ERROR"


class SchedulerError(AppError):
    """Scheduler 실행 실패 (향후 weather/forecast/scaler 스케줄러 공용)."""

    code = "SCHEDULER_ERROR"


class ExternalApiError(AppError):
    """외부 API(Open-Meteo 등) 호출 실패. Adapter에서만 발생시킨다."""

    status_code = 502
    code = "EXTERNAL_API_ERROR"

    def __init__(self, message: str, *, provider: str, detail: dict | None = None):
        super().__init__(message, detail=detail)
        self.provider = provider


class KubernetesError(AppError):
    """Kubernetes API(KEDA ScaledObject Patch, Node 조회 등) 실패. K8s Adapter에서만 발생시킨다."""

    status_code = 502
    code = "KUBERNETES_ERROR"


class PredictionError(AppError):
    """Forecast Pipeline 실패 (모델 로드/예측/업로드 단계 재시도 소진)."""

    code = "PREDICTION_ERROR"


class ScalingError(AppError):
    """Predictive Scaling 실패 (Prediction 해석/KEDA Patch 재시도 소진)."""

    code = "SCALING_ERROR"


class WorkerError(AppError):
    """Worker 메시지 처리 실패 (재시도 불가능 오류 구분용)."""

    code = "WORKER_ERROR"
