# JSON/CSV 상태를 로컬 디스크 또는 S3 중 설정된 한쪽으로 읽고 쓰는 공통 스토어.
# DB를 뺀 이번 재설계에서 트래픽 집계·예측 결과·스케일링 이력 등 모든 상태 동기화가
# 이 위를 지나간다. json_store_backend=local이면 프로세스 로컬 디스크에, s3면
# S3(여러 파드가 공유 가능한 유일한 진실원천)에 저장한다 — 호출부는 둘 중 뭔지 몰라도 된다.
import json
from pathlib import Path

from common.aws.s3_adapter import S3Adapter


class FileStore:
    def __init__(self, backend: str, local_dir: str, s3_adapter: S3Adapter | None = None):
        if backend not in ("local", "s3"):
            raise ValueError(f"unknown json_store_backend: {backend}")
        if backend == "s3" and s3_adapter is None:
            raise ValueError("s3 backend requires an S3Adapter")
        self._backend = backend
        self._local_dir = Path(local_dir)
        self._s3 = s3_adapter
        if backend == "local":
            self._local_dir.mkdir(parents=True, exist_ok=True)

    def exists(self, key: str) -> bool:
        if self._backend == "s3":
            return self._s3.exists(key)
        return (self._local_dir / key).exists()

    def list_keys(self, prefix: str) -> list[str]:
        """prefix로 시작하는 모든 키를 반환한다. 여러 파드가 각자 파일 하나씩 쓰고
        (예: traffic/instances/<pod-id>.json), 한쪽(predict)이 이걸로 목록을 모아
        집계하는 shard-and-aggregate 패턴에 쓴다."""
        if self._backend == "s3":
            return self._s3.list_keys(prefix)
        base = self._local_dir / prefix
        if base.is_dir():
            return [str(p.relative_to(self._local_dir)).replace("\\", "/") for p in base.rglob("*") if p.is_file()]
        parent = base.parent
        if not parent.is_dir():
            return []
        return [
            str(p.relative_to(self._local_dir)).replace("\\", "/")
            for p in parent.iterdir()
            if p.is_file() and str(p.relative_to(self._local_dir)).replace("\\", "/").startswith(prefix)
        ]

    def read_text(self, key: str) -> str | None:
        if not self.exists(key):
            return None
        if self._backend == "s3":
            return self._s3.download_text(key)
        return (self._local_dir / key).read_text(encoding="utf-8")

    def write_text(self, key: str, content: str) -> None:
        if self._backend == "s3":
            self._s3.upload_text(key, content)
            return
        path = self._local_dir / key
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(content, encoding="utf-8")

    def read_json(self, key: str) -> dict | list | None:
        text = self.read_text(key)
        return json.loads(text) if text is not None else None

    def write_json(self, key: str, data: dict | list) -> None:
        self.write_text(key, json.dumps(data, ensure_ascii=False, default=str, indent=2))
