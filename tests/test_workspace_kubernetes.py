"""Rendered isolation and migration contracts shared by alpha and prod."""
from pathlib import Path
from ipaddress import ip_network
import subprocess

import pytest
import yaml

ROOT = Path(__file__).resolve().parents[1]


def render(platform, *overrides):
    chart = ROOT / "charts/agent-studio"
    phase = "prod" if platform == "eks" else "alpha"
    result = subprocess.run(["helm", "template", "agent-studio", str(chart), "--namespace", "agent-studio",
                             "-f", str(chart / "values.yaml"), "-f", str(chart / f"values-{phase}.yaml"),
                             "-f", str(chart / platform / f"values-{platform}-demo.yaml"), "--set", "app.workloads.workspaceWorker.backend=kubernetes", *overrides],
                            capture_output=True, text=True, check=True)
    return [item for item in yaml.safe_load_all(result.stdout) if item]


@pytest.mark.parametrize("platform,max_pods", [("eks", "32"), ("k3s", "2")])
def test_isolation_permissions_and_total_capacity(platform, max_pods):
    docs = render(platform)
    namespace = "agent-studio-workspaces"
    scoped = {item["kind"] + "/" + item["metadata"]["name"]: item for item in docs
              if item["metadata"].get("namespace") == namespace}
    role = scoped["Role/agent-studio-sandbox"]
    assert role["rules"] == [
        {"apiGroups": [""], "resources": ["pods"], "verbs": ["get", "list", "create", "delete"]},
        {"apiGroups": [""], "resources": ["pods/exec"], "verbs": ["get", "create"]},
    ]
    assert scoped["RoleBinding/agent-studio-sandbox"]["subjects"] == [
        {"kind": "ServiceAccount", "name": "agent-studio", "namespace": "agent-studio"}]
    assert scoped["ServiceAccount/sandbox"]["automountServiceAccountToken"] is False
    quota = scoped["ResourceQuota/agent-studio-sandbox"]["spec"]["hard"]
    assert quota["pods"] == max_pods
    assert int(quota["requests.ephemeral-storage"][:-2]) == (2048 * 2 + 512) * int(max_pods)
    isolation = scoped["NetworkPolicy/sandbox-isolation"]["spec"]
    assert isolation == {"podSelector": {}, "policyTypes": ["Ingress", "Egress"], "ingress": [], "egress": []}
    egress = scoped["NetworkPolicy/sandbox-egress"]["spec"]["egress"]
    assert egress[0]["ports"] == [{"protocol": "UDP", "port": 53}, {"protocol": "TCP", "port": 53}]
    assert "169.254.0.0/16" in egress[1]["to"][0]["ipBlock"]["except"]
    assert "10.0.0.0/8" in egress[1]["to"][0]["ipBlock"]["except"]
    # Auto Mode compiles these rules for the cluster IP family, including DNS allowances.
    for rule in egress:
        for destination in rule["to"]:
            if "ipBlock" in destination:
                block = destination["ipBlock"]
                assert all(ip_network(cidr).version == 4 for cidr in [block["cidr"], *block.get("except", [])])
    assert scoped["ExternalSecret/ecr-registry"]["spec"]["target"]["name"] == "ecr-registry"
    assert not any(item["kind"] == "ClusterRoleBinding" for item in docs)
    assert not any(item["metadata"]["name"] == "agent-studio-workspace-docker" and item["kind"] in {"Deployment", "Service", "NetworkPolicy"} for item in docs)


@pytest.mark.parametrize("platform", ["eks", "k3s"])
def test_optional_legacy_daemon_preserves_migration_order(platform):
    docs = render(platform, "--set", "app.workloads.workspaceWorker.legacyDocker.enabled=true")
    daemon = next(item for item in docs if item["kind"] == "Deployment" and item["metadata"]["name"] == "agent-studio-workspace-docker")
    assert daemon["metadata"]["annotations"]["argocd.argoproj.io/sync-wave"] == "1"
    assert daemon["spec"]["strategy"]["type"] == "Recreate"
    assert daemon["spec"]["replicas"] == 1


def test_production_worker_capacity_and_single_writer_legacy_daemon():
    docs = render("eks", "--set", "app.workloads.workspaceWorker.legacyDocker.enabled=true")
    worker = next(item for item in docs if item["kind"] == "Deployment" and item["metadata"]["name"] == "agent-studio-workspace-worker")
    assert worker["spec"]["replicas"] == 2
    assert worker["spec"]["template"]["spec"]["terminationGracePeriodSeconds"] >= 120
    assert worker["spec"]["strategy"] == {"type": "RollingUpdate", "rollingUpdate": {"maxSurge": 1, "maxUnavailable": 0}}
    config = next(item for item in docs if item["kind"] == "ConfigMap" and item["metadata"]["name"] == "agent-studio-workspace")
    assert int(config["data"]["WORKSPACE_WORKER_CONCURRENCY"]) * worker["spec"]["replicas"] == 32
    pdb = next(item for item in docs if item["kind"] == "PodDisruptionBudget" and item["metadata"]["name"] == "agent-studio-workspace-worker")
    assert pdb["spec"]["selector"]["matchLabels"] == worker["spec"]["selector"]["matchLabels"]
    assert pdb["spec"]["maxUnavailable"] == 1
    daemon = next(item for item in docs if item["kind"] == "Deployment" and item["metadata"]["name"] == "agent-studio-workspace-docker")
    assert daemon["spec"]["replicas"] == 1


@pytest.mark.parametrize("setting", ["workerConcurrency=8", "memoryMb=4096", "cpus=2"])
def test_workspace_configuration_restarts_both_web_and_worker(setting):
    before = render("eks")
    after = render("eks", "--set", "app.workloads.workspaceWorker." + setting)
    for name in ("agent-studio", "agent-studio-workspace-worker"):
        old = next(item for item in before if item["kind"] == "Deployment" and item["metadata"]["name"] == name)
        new = next(item for item in after if item["kind"] == "Deployment" and item["metadata"]["name"] == name)
        assert old["spec"]["template"]["metadata"]["annotations"]["checksum/workspace"] != new["spec"]["template"]["metadata"]["annotations"]["checksum/workspace"]


@pytest.mark.parametrize("platform", ["eks", "k3s"])
def test_retirement_does_not_remove_pvc_or_bypass_drain_gate(platform):
    docs = render(platform, "--set", "app.workloads.workspaceWorker.legacyDocker.enabled=false")
    pvc = next(item for item in docs if item["kind"] == "PersistentVolumeClaim")
    legacy_docs = render(platform, "--set", "app.workloads.workspaceWorker.legacyDocker.enabled=true")
    assert pvc == next(item for item in legacy_docs if item["kind"] == "PersistentVolumeClaim")
    assert pvc["metadata"]["annotations"]["argocd.argoproj.io/sync-options"] == "Prune=false,Delete=false"
    gate = next(item for item in docs if item["kind"] == "Job" and item["metadata"]["name"] == "agent-studio-workspace-migration")
    assert gate["metadata"]["annotations"]["argocd.argoproj.io/hook"] == "PreSync"
    assert gate["spec"]["backoffLimit"] == 0
    pod = gate["spec"]["template"]
    # Existing DinD ingress permits this name; no instance label selects the hook into the app Service.
    assert pod["metadata"]["labels"] == {"app.kubernetes.io/name": "agent-studio"}
    assert not pod["spec"]["containers"][0].get("envFrom")
    if platform == "eks":
        auth = next(item for item in docs if item["kind"] == "ExternalSecret" and not item["metadata"].get("namespace") and item["metadata"]["name"] == "ecr-registry")
        assert auth["metadata"]["annotations"]["argocd.argoproj.io/sync-options"] == "Prune=false,Delete=false"


def test_docker_backend_still_renders_its_original_execution_path():
    docs = render("k3s", "--set", "app.workloads.workspaceWorker.backend=docker")
    worker = next(item for item in docs if item["kind"] == "Deployment" and item["metadata"]["name"] == "agent-studio-workspace-worker")
    assert [container["name"] for container in worker["spec"]["template"]["spec"]["containers"]] == ["workspace-worker", "docker"]
    assert not any(item["kind"] == "Role" and item["metadata"].get("namespace") == "agent-studio-workspaces" for item in docs)


@pytest.mark.parametrize("platform", ["eks", "k3s"])
def test_native_gateway_uses_the_app_service_and_only_allows_its_pods(platform):
    docs = render(platform, "--set", "app.fullnameOverride=studio-gateway-fixture", "--set", "app.service.port=8080", "--set", "app.service.targetPort=3100")
    service = next(item for item in docs if item["kind"] == "Service" and item["metadata"]["name"] == "studio-gateway-fixture")
    config = next(item for item in docs if item["kind"] == "ConfigMap" and item["metadata"]["name"] == "agent-studio-workspace")
    assert config["data"]["WORKSPACE_MODEL_GATEWAY_URL"] == "http://studio-gateway-fixture.agent-studio.svc.cluster.local:8080"
    policy = next(item for item in docs if item["kind"] == "NetworkPolicy" and item["metadata"]["name"] == "sandbox-egress")
    expected = {"to": [{"namespaceSelector": {"matchLabels": {"kubernetes.io/metadata.name": "agent-studio"}},
                         "podSelector": {"matchLabels": service["spec"]["selector"]}}],
                "ports": [{"protocol": "TCP", "port": 3100}]}
    assert expected in policy["spec"]["egress"]
    deployments = [item for item in docs if item["kind"] == "Deployment" and item["metadata"]["name"] in ["studio-gateway-fixture", "agent-studio-workspace-worker"]]
    assert {deployment["metadata"]["name"] for deployment in deployments} == {"studio-gateway-fixture", "agent-studio-workspace-worker"}
    for deployment in deployments:
        worker = deployment["spec"]["template"]["spec"]["containers"][0]
        assert {"configMapRef": {"name": "agent-studio-workspace"}} in worker["envFrom"]
