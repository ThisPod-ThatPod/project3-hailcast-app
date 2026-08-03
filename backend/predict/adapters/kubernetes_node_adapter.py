# Kubernetes 구현체 — CoreV1Api로 클러스터 노드 목록을 읽어 Ready 노드 수를 센다.
# Pod에는 nodes get/list RBAC가 필요하다 — Node는 cluster-scoped라 ClusterRole
# (k8s/predict-rbac.yaml 예시 참고). 로컬 k8s는 kubeconfig, EKS는 Pod 내
# ServiceAccount로 자동 전환되므로 동일 코드로 동작한다 (AWS IAM 불필요 — K8s API만 사용).
from common.core.exceptions import KubernetesError
from common.core.logger import get_logger

from adapters.node_adapter import NodeAdapter

logger = get_logger("node_adapter")


class KubernetesNodeAdapter(NodeAdapter):
    def __init__(self):
        self._api = None  # CoreV1Api — lazy (클러스터 밖에서 생성돼도 startup은 죽지 않는다)

    def _ensure_api(self):
        if self._api is not None:
            return self._api
        try:
            from kubernetes import client
            from kubernetes import config as k8s_config

            try:
                k8s_config.load_incluster_config()   # Pod 내부 (ServiceAccount) — EKS 포함
            except Exception:
                k8s_config.load_kube_config()        # 로컬 kubeconfig
            self._api = client.CoreV1Api()
            return self._api
        except Exception as exc:
            raise KubernetesError(
                f"kubernetes client init failed: {exc}",
                detail={"resource": "nodes"},
            ) from exc

    def count_ready_nodes(self) -> int:
        try:
            nodes = self._ensure_api().list_node()
        except KubernetesError:
            raise
        except Exception as exc:
            raise KubernetesError(
                f"list nodes failed: {exc}",
                detail={"resource": "nodes"},
            ) from exc
        ready = 0
        for node in nodes.items:
            conditions = node.status.conditions or []
            if any(c.type == "Ready" and c.status == "True" for c in conditions):
                ready += 1
        return ready
