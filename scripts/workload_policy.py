"""k3s/local omit compute reservations except Neo4j's required minimum requests."""

from pathlib import Path

import yaml
import re


PLATFORMS = {"eks", "k3s", "local"}
UNRESERVED_PLATFORMS = {"k3s", "local"}
AUTOSCALERS = {"HorizontalPodAutoscaler", "VerticalPodAutoscaler", "ScaledObject", "ScaledJob"}
VM_WORKLOADS = {"VMAgent", "VMAlert", "VMAlertmanager", "VMAuth", "VMCluster", "VMSingle"}
NEO4J_MINIMUM_REQUESTS = {"cpu": "500m", "memory": "2Gi"}


def target_platform(target, env):
    if env.get("env"):
        return env["env"]
    return next((part for part in reversed(Path(target["appset"]).parts[:-1]) if part in PLATFORMS), "eks")


def policy_errors(manifests, platform):
    if platform == "eks":
        return production_resource_errors(manifests)
    if platform not in UNRESERVED_PLATFORMS:
        return []
    errors = []

    def inspect(value, owner, path="", vm_workload=False):
        if isinstance(value, list):
            for index, child in enumerate(value):
                inspect(child, owner, f"{path}[{index}]", vm_workload)
        elif isinstance(value, dict):
            for key, child in value.items():
                location = f"{path}.{key}" if path else key
                if vm_workload and key in {"resources", "configReloaderResources"} and not isinstance(child, dict):
                    errors.append(f"{owner} {location} must be an object when present")
                if (key == "resources" or key.endswith("Resources")) and isinstance(child, dict):
                    for field in ("requests", "limits"):
                        quantities = child.get(field) or {}
                        # The unmodified official chart rejects missing/zero requests.
                        # Match the container path and exact minimum; sidecars, init
                        # containers, larger reservations and limits remain forbidden.
                        if (owner == "StatefulSet/memory-neo4j"
                                and location.startswith("spec.template.spec.containers[")
                                and location.count(".") == 4
                                and value.get("name") == "neo4j"
                                and field == "requests"
                                and quantities == NEO4J_MINIMUM_REQUESTS):
                            continue
                        if isinstance(quantities, dict) and any(name != "storage" for name in quantities):
                            errors.append(f"{owner} {location}.{field} reserves compute")
                if key in {"autoscaling", "hpa", "vpa"} and isinstance(child, dict) and child.get("enabled") is True:
                    errors.append(f"{owner} {location}.enabled must be false")
                if key == "autoscaleEnabled" and child is True:
                    errors.append(f"{owner} {location} must be false")
                inspect(child, owner, location, vm_workload)

    for document in yaml.safe_load_all(manifests):
        if not document or document.get("kind") == "CustomResourceDefinition":
            continue
        kind = document.get("kind")
        owner = f"{kind}/{document.get('metadata', {}).get('name', '?')}"
        if kind in AUTOSCALERS:
            errors.append(f"{owner} is not allowed on {platform}")
        if kind == "VMCluster":
            for component in ("vminsert", "vmselect", "vmstorage"):
                config = document.get("spec", {}).get(component)
                if isinstance(config, dict) and config.get("useDefaultResources") is not False:
                    errors.append(f"{owner} spec.{component}.useDefaultResources must be false")
        elif kind in VM_WORKLOADS and document.get("spec", {}).get("useDefaultResources") is not False:
            errors.append(f"{owner} spec.useDefaultResources must be false")
        inspect(document, owner, vm_workload=kind in VM_WORKLOADS)
        if kind == "HelmChartConfig":
            # k3s deploys its bundled Traefik chart from this embedded values document.
            values = yaml.safe_load(document.get("spec", {}).get("valuesContent", ""))
            inspect(values, owner, "spec.valuesContent")
            if document.get("metadata", {}).get("name") == "traefik":
                values = values or {}
                # Traefik dereferences resources.limits; removing the parent map breaks rendering.
                # Null children remove Helm defaults, while empty maps merge those defaults back in.
                resources = values.get("resources")
                if not isinstance(resources, dict) or any(
                    field not in resources or resources[field] is not None
                    for field in ("requests", "limits")
                ):
                    errors.append(f"{owner} valuesContent.resources must keep a map with requests/limits explicitly null")
                if values.get("autoscaling", {}).get("enabled") is not False:
                    errors.append(f"{owner} valuesContent.autoscaling.enabled must be false")
    return errors

def production_resource_errors(manifests):
    """Check Pod specs and operator resources, never arbitrary ConfigMap data."""
    errors = []

    def positive(quantity):
        if isinstance(quantity, bool):
            return False
        match = re.fullmatch(r"([+]?(?:\d+(?:\.\d*)?|\.\d+))(?:(?:[eE][+-]?\d+)|[KMGTPE]i|[numkMGTPE])?", str(quantity))
        return bool(match and float(match.group(1)) > 0)

    def budget(resources, owner, path):
        resources = resources or {}
        if not isinstance(resources, dict):
            errors.append(f"{owner} {path} must be an object")
            return
        for section, resource in (("requests", "cpu"), ("requests", "memory"), ("limits", "memory")):
            quantities = resources.get(section) or {}
            if not isinstance(quantities, dict) or not positive(quantities.get(resource)):
                errors.append(f"{owner} {path}.{section}.{resource} must reserve a positive EKS budget")

    def at(value, *keys):
        for key in keys:
            if not isinstance(value, dict):
                return None
            value = value.get(key)
        return value

    def pod(spec, owner, path):
        if spec is None:
            return
        if not isinstance(spec, dict):
            errors.append(f"{owner} {path} must be a Pod spec object")
            return
        for field in ("containers", "initContainers"):
            containers = spec.get(field) or []
            if not isinstance(containers, list):
                errors.append(f"{owner} {path}.{field} must be a list")
                continue
            for index, container in enumerate(containers):
                location = f"{path}.{field}[{index}]"
                if not isinstance(container, dict):
                    errors.append(f"{owner} {location} must be a container object")
                else:
                    budget(container.get("resources"), owner, location + ".resources")

    for document in yaml.safe_load_all(manifests):
        if not document or document.get("kind") == "CustomResourceDefinition":
            continue
        kind = document.get("kind")
        owner = f"{kind}/{document.get('metadata', {}).get('name', '?')}"
        if kind in {"Prometheus", "Alertmanager", "ThanosRuler"}:
            budget(at(document, "spec", "resources"), owner, "spec.resources")
            pod(document.get("spec"), owner, "spec")
        elif kind == "Pod":
            pod(document.get("spec"), owner, "spec")
        pod(at(document, "spec", "template", "spec"), owner, "spec.template.spec")
        if kind == "PodTemplate":
            pod(at(document, "template", "spec"), owner, "template.spec")
        if kind == "CronJob":
            pod(at(document, "spec", "jobTemplate", "spec", "template", "spec"), owner, "spec.jobTemplate.spec.template.spec")
        if kind in {"AnalysisTemplate", "ClusterAnalysisTemplate"}:
            for index, metric in enumerate(at(document, "spec", "metrics") or []):
                pod(at(metric, "provider", "job", "spec", "template", "spec"), owner,
                    f"spec.metrics[{index}].provider.job.spec.template.spec")
    return errors
