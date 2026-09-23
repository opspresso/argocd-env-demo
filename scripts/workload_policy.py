"""EKS keeps chart defaults; k3s/local must not reserve compute or autoscale."""

from pathlib import Path

import yaml


PLATFORMS = {"eks", "k3s", "local"}
UNRESERVED_PLATFORMS = {"k3s", "local"}
AUTOSCALERS = {"HorizontalPodAutoscaler", "VerticalPodAutoscaler", "ScaledObject", "ScaledJob"}
VM_WORKLOADS = {"VMAgent", "VMAlert", "VMAlertmanager", "VMAuth", "VMCluster", "VMSingle"}


def target_platform(target, env):
    if env.get("env"):
        return env["env"]
    return next((part for part in reversed(Path(target["appset"]).parts[:-1]) if part in PLATFORMS), "eks")


def policy_errors(manifests, platform):
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
