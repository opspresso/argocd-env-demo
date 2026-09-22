"""Deployment contracts between the applications and their cluster dependencies."""

from functools import lru_cache
from pathlib import Path
import subprocess

import pytest
import yaml

from workload_policy import policy_errors


ROOT = Path(__file__).resolve().parents[1]


@lru_cache
def manifests(chart, platform, image_tag=None):
    path = ROOT / "charts" / chart
    definition = yaml.safe_load((path / "Chart.yaml").read_text())
    if definition.get("dependencies") and not list((path / "charts").glob("*.tgz")):
        pytest.skip(f"Run helm dependency update {path}")
    args = ["helm", "template", f"{chart}-{platform}-demo", str(path),
            "--api-versions", "monitoring.coreos.com/v1", "-f", str(path / "values.yaml")]
    phase = yaml.safe_load((ROOT / "env" / f"{platform}-demo.yaml").read_text())["phase"]
    if (path / "values-alpha.yaml").exists():
        args += ["-f", str(path / f"values-{phase}.yaml")]
    args += ["-f", str(path / platform / f"values-{platform}-demo.yaml")]
    if image_tag:
        args += ["--set-string", f"app.image.tag={image_tag}"]
    result = subprocess.run(args, capture_output=True, text=True, check=True)
    assert not policy_errors(result.stdout, platform)
    return [doc for doc in yaml.safe_load_all(result.stdout) if doc]


def resource(chart, platform, kind, name):
    return next(doc for doc in manifests(chart, platform)
                if doc["kind"] == kind and doc["metadata"]["name"] == name)


@pytest.mark.parametrize("platform", ["eks", "k3s"])
@pytest.mark.parametrize("chart", ["agent-studio", "agent-memory"])
def test_application_credentials_match_cluster_dependencies(chart, platform):
    secret = resource(chart, platform, "ExternalSecret", f"{chart}-external")
    refs = {entry["secretKey"]: entry["remoteRef"]["key"] for entry in secret["spec"]["data"]}
    assert refs["DATABASE_URL"] == f"/k8s/{platform}-demo/{chart}/database-url"
    config = resource(chart, platform, "ConfigMap", chart)["data"]
    assert not any("BEDROCK" in key or "DYNAMO" in key for key in config)
    if platform == "eks":
        assert "S3_ENDPOINT" not in config
        assert "S3_ACCESS_KEY_ID" not in refs
        assert "S3_SECRET_ACCESS_KEY" not in refs
        assert config.get("S3_BUCKET", config.get("S3_BUCKET_NAME")) == "agent-studio-static"
    else:
        assert config["S3_ENDPOINT"] == "http://minio.agent-studio.svc.cluster.local:9000"
        assert refs["S3_ACCESS_KEY_ID"] == "/k8s/k3s-demo/agent-studio/minio-root-user"
    if chart == "agent-memory":
        assert refs["NEO4J_PASSWORD"] == f"/k8s/{platform}-demo/agent-memory/neo4j-password"
        assert config["NEO4J_URI"] == "bolt://memory-neo4j.agent-memory.svc.cluster.local:7687"
        assert config["DOCUMENT_WORKER_ENABLED"] == "true"


@pytest.mark.parametrize("platform", ["eks", "k3s"])
def test_memory_monitor_authenticates_and_selects_the_application_service(platform):
    monitor = resource("agent-memory", platform, "ServiceMonitor", "agent-memory")["spec"]
    service = resource("agent-memory", platform, "Service", "agent-memory")
    assert monitor["endpoints"][0]["authorization"]["credentials"] == {
        "name": "agent-memory-external", "key": "METRICS_BEARER_TOKEN"
    }
    assert monitor["selector"]["matchLabels"].items() <= service["metadata"]["labels"].items()
    container = resource("agent-memory", platform, "Deployment", "agent-memory")["spec"]["template"]["spec"]["containers"][0]
    assert container["readinessProbe"]["httpGet"]["path"] == "/api/health"
    assert container["livenessProbe"]["tcpSocket"]["port"] == 3000


def test_memory_hpa_uses_a_metric_memory_actually_provides():
    hpa = resource("agent-memory", "eks", "HorizontalPodAutoscaler", "agent-memory")
    assert hpa["spec"]["metrics"] == [{
        "type": "Resource", "resource": {"name": "cpu", "target": {
            "type": "Utilization", "averageUtilization": 70
        }}
    }]


def test_eks_workers_have_resources_identity_and_registry_refresh():
    for name in ["agent-studio-audio-worker", "agent-studio-workspace-worker"]:
        pod = resource("agent-studio", "eks", "Deployment", name)["spec"]["template"]["spec"]
        assert pod["serviceAccountName"] == "agent-studio"
        assert all(container["resources"]["requests"] for container in pod["containers"])
    registry = resource("agent-studio", "eks", "ExternalSecret", "ecr-registry")["spec"]
    assert registry["refreshInterval"] == "1h"
    assert registry["dataFrom"][0]["sourceRef"]["generatorRef"]["kind"] == "ECRAuthorizationToken"
    pvc = resource("agent-studio", "eks", "PersistentVolumeClaim", "agent-studio-workspace-docker")
    assert pvc["spec"]["storageClassName"] == "gp3"


@pytest.mark.parametrize("platform,stage", [("eks", "prod"), ("k3s", "alpha")])
def test_coding_workers_have_github_and_a_managed_egress_network(platform, stage):
    config = resource("agent-studio", platform, "ConfigMap", "agent-studio")["data"]
    assert config["STAGE"] == stage
    assert config["WORKSPACE_GITHUB_AUTH"] == "token"
    assert config["GITHUB_WEB_URL"] == "https://github.com"
    assert config["WORKSPACE_NETWORK"] == "agent-studio-public"
    pod = resource("agent-studio", platform, "Deployment", "agent-studio-workspace-worker")["spec"]["template"]["spec"]
    worker, docker = pod["containers"]
    assert docker["command"] == ["/bin/sh", "/opt/workspace-network/workspace-network.sh"]
    assert {env["name"]: env["value"] for env in docker["env"]}["WORKSPACE_NETWORK"] == config["WORKSPACE_NETWORK"]
    script = resource("agent-studio", platform, "ConfigMap", "agent-studio-workspace-network")["data"]["workspace-network.sh"]
    assert script == (ROOT / "charts/agent-studio/files/workspace-network.sh").read_text()
    assert worker["livenessProbe"]["exec"]["command"] == ["node", "build/workspace-health.cjs", "--heartbeat-only"]
    for cron in ["agent-studio-scan", "agent-studio-reindex"]:
        assert resource("agent-studio", platform, "CronJob", cron)["spec"]["suspend"] is False


@pytest.mark.parametrize("platform", ["eks", "k3s"])
@pytest.mark.parametrize("tag", ["v0.115.1", "v0.115.2"])
def test_application_and_workspace_use_the_same_release(platform, tag):
    documents = manifests("agent-studio", platform, tag)
    configs = {doc["metadata"]["name"]: doc["data"] for doc in documents if doc["kind"] == "ConfigMap"}
    deployments = {doc["metadata"]["name"]: doc for doc in documents if doc["kind"] == "Deployment"}
    for name in ["agent-studio", "agent-studio-workspace-worker"]:
        container = deployments[name]["spec"]["template"]["spec"]["containers"][0]
        repository, image_tag = container["image"].rsplit(":", 1)
        assert image_tag == tag
        images = [configs[entry["configMapRef"]["name"]]["WORKSPACE_IMAGE"]
                  for entry in container["envFrom"] if "configMapRef" in entry
                  and "WORKSPACE_IMAGE" in configs.get(entry["configMapRef"]["name"], {})]
        assert images == [f"{repository}:workspace-{tag}"]
        assert not any(entry["name"] == "WORKSPACE_IMAGE" for entry in container.get("env", []))


@pytest.mark.parametrize("chart,name", [("postgresql", "postgres"), ("neo4j", "memory-neo4j")])
def test_eks_databases_are_gitops_managed_with_persistent_storage(chart, name):
    application = yaml.safe_load((ROOT / "apps/eks" / f"{chart}.yaml").read_text())
    source = application["spec"]["template"]["spec"]["source"]
    assert source["path"] == f"charts/{chart}"
    assert source["helm"]["valueFiles"] == ["values.yaml", "{{env}}/values-{{cluster}}.yaml"]
    workload = resource(chart, "eks", "StatefulSet", name)["spec"]
    assert workload["volumeClaimTemplates"][0]["spec"]["resources"]["requests"]["storage"] == "20Gi"
    assert workload["template"]["spec"]["containers"][0]["resources"]["requests"]
