# Copyright (c) Last9, Inc.
"""Map GPU ordinal (0-based) → K8s pod metadata using sequential allocation.

Mirrors k8shelper/k8shelper.go::buildGPU2K8s.
Returns {} if not running in Kubernetes or kubernetes package unavailable.
"""

import logging
from typing import Dict, Optional

logger = logging.getLogger(__name__)

GPU_RESOURCE_TYPES = ("nvidia.com/gpu", "amd.com/gpu")


def _resolve_deployment(core_api, apps_api, namespace: str, pod) -> Optional[str]:
    """Walk owner refs: Pod → ReplicaSet → Deployment. Returns Deployment name or None."""
    for ref in pod.metadata.owner_references or []:
        if ref.kind == "ReplicaSet":
            try:
                rs = apps_api.read_namespaced_replica_set(ref.name, namespace)
                for rs_ref in rs.metadata.owner_references or []:
                    if rs_ref.kind == "Deployment":
                        return rs_ref.name
            except Exception:
                pass
        if ref.kind == "Deployment":
            return ref.name
    return None


def _job_name(pod) -> Optional[str]:
    for ref in pod.metadata.owner_references or []:
        if ref.kind == "Job":
            return ref.name
    return None


def get_gpu_k8s_mapping(node_name: str) -> Dict[int, Dict[str, str]]:
    """Return {gpu_index: {"k8s.namespace.name": ..., "k8s.pod.name": ..., ...}}."""
    try:
        from kubernetes import client, config  # type: ignore

        config.load_incluster_config()
    except Exception as e:
        logger.debug("K8s client unavailable: %s", e)
        return {}

    try:
        core_api = client.CoreV1Api()
        apps_api = client.AppsV1Api()
        pods = core_api.list_pod_for_all_namespaces(
            field_selector=f"spec.nodeName={node_name},status.phase=Running"
        ).items
    except Exception as e:
        logger.warning("K8s pod list failed: %s", e)
        return {}

    result: Dict[int, Dict[str, str]] = {}
    ordinal = 0
    for pod in pods:
        gpu_count = 0
        for container in pod.spec.containers or []:
            limits = (container.resources.limits or {}) if container.resources else {}
            for rtype in GPU_RESOURCE_TYPES:
                try:
                    gpu_count += int(limits.get(rtype, 0))
                except (ValueError, TypeError):
                    pass
        if gpu_count == 0:
            continue

        namespace = pod.metadata.namespace
        pod_name = pod.metadata.name
        attrs: Dict[str, str] = {
            "k8s.namespace.name": namespace,
            "k8s.pod.name": pod_name,
        }
        dep = _resolve_deployment(core_api, apps_api, namespace, pod)
        if dep:
            attrs["k8s.deployment.name"] = dep
        job = _job_name(pod)
        if job:
            attrs["k8s.job.name"] = job

        for i in range(gpu_count):
            result[ordinal + i] = attrs
        ordinal += gpu_count

    return result
