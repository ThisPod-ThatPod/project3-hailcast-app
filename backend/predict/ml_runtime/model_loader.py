# Model Loader — S3 Download → joblib Deserialize → Memory Load. 버전 캐시로 불필요한 다운로드 방지.
# 매 Scheduler 실행 시 latest metadata를 확인해 재학습 모델이 올라오면 자동 교체된다.
# ml/train.py가 joblib으로 저장하는 sklearn 호환 LGBMRegressor를 그대로 읽는다 (lgb.Booster 아님).
import os

import joblib

from common.aws.s3_adapter import S3Adapter
from common.core.logger import get_logger

logger = get_logger("model_loader")


class ModelLoader:
    def __init__(self, s3: S3Adapter, model_prefix: str, cache_dir: str):
        self._s3 = s3
        self._prefix = model_prefix
        self._cache_dir = cache_dir
        self._cached_version: str | None = None
        self._model = None
        self._metadata: dict = {}

    def load_latest(self) -> tuple[object, dict]:
        """항상 latest 모델을 반환한다. 버전이 같으면 메모리 캐시를 재사용한다."""
        metadata = self._s3.download_json(f"{self._prefix}/latest/metadata.json")
        version = metadata.get("version", "unknown")
        if version != self._cached_version or self._model is None:
            os.makedirs(self._cache_dir, exist_ok=True)
            local_path = os.path.join(self._cache_dir, f"model-{version}.pkl")
            self._s3.download_file(f"{self._prefix}/latest/model.pkl", local_path)
            self._model = joblib.load(local_path)
            self._cached_version = version
            self._metadata = metadata
            logger.info(
                f"model loaded (version={version})",
                extra={"event": "model_loaded", "detail": {"version": version, "mae": metadata.get("mae")}},
            )
        return self._model, self._metadata
