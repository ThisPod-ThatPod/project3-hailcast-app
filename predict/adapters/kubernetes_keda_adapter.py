# Kubernetes 구현체 — keda.sh/v1alpha1 ScaledObject를 CustomObjectsApi로 Read/Patch.
# Pod에는 scaledobjects get/patch RBAC가 필요하다 (인프라 레포에서 ServiceAccount 구성).
from common.core.exceptions import KubernetesError
from common.core.logger import get_logger

logger = get_logger("keda_adapter")

_GROUP = "keda.sh"
_VERSION = "v1alpha1"
_PLURAL = "scaledobjects"


class KubernetesKedaAdapter:
    def __init__(self, namespace: str, scaledobject_name: str):
        self._namespace = namespace
        self._name = scaledobject_name
        self._api = None  # lazy — 클러스터 밖에서 생성돼도 startup은 죽지 않는다

    def _ensure_api(self):
        if self._api is not None:
            return self._api
        try:
            from kubernetes import client, config as k8s_config

            try:
                k8s_config.load_incluster_config()   # Pod 내부 (ServiceAccount)
            except Exception:
                k8s_config.load_kube_config()        # 로컬 kubeconfig
            self._api = client.CustomObjectsApi()
            return self._api
        except Exception as exc:
            raise KubernetesError(
                f"kubernetes client init failed: {exc}",
                detail={"scaledobject": self._name},
            ) from exc

    def get_min_replicas(self) -> int:
        try:
            obj = self._ensure_api().get_namespaced_custom_object(
                _GROUP, _VERSION, self._namespace, _PLURAL, self._name
            )
            return int(obj.get("spec", {}).get("minReplicaCount", 0))
        except KubernetesError:
            raise
        except Exception as exc:
            raise KubernetesError(
                f"read ScaledObject failed: {exc}",
                detail={"scaledobject": self._name, "namespace": self._namespace},
            ) from exc

    def patch_min_replicas(self, replicas: int) -> int:
        try:
            self._ensure_api().patch_namespaced_custom_object(
                _GROUP, _VERSION, self._namespace, _PLURAL, self._name,
                {"spec": {"minReplicaCount": replicas}},
            )
            # Read Result — Patch 적용값 재확인
            applied = self.get_min_replicas()
            logger.info(
                f"scaledobject patched (minReplicaCount={applied})",
                extra={"event": "patch_success", "count": applied},
            )
            return applied
        except KubernetesError:
            raise
        except Exception as exc:
            raise KubernetesError(
                f"patch ScaledObject failed: {exc}",
                detail={"scaledobject": self._name, "namespace": self._namespace},
            ) from exc
