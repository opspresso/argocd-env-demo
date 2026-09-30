"""Shared chart composition must preserve workload identity and version coupling."""

from pathlib import Path
import subprocess

import pytest
import yaml


ROOT = Path(__file__).resolve().parents[1]


def render(chart, platform="k3s", *settings):
    path = ROOT / "charts" / chart
    phase = "prod" if platform == "eks" else "alpha"
    command = ["helm", "template", "custom-release", str(path), "-n", "custom-namespace",
               "-f", str(path / f"values-{phase}.yaml"),
               "-f", str(path / platform / f"values-{platform}-demo.yaml")]
    for setting in settings:
        command += ["--set", setting]
    output = subprocess.run(command, capture_output=True, text=True, check=True).stdout
    docs = [doc for doc in yaml.safe_load_all(output) if doc]
    identities = [(doc["kind"], doc["metadata"].get("namespace", "custom-namespace"),
                   doc["metadata"]["name"]) for doc in docs]
    assert len(identities) == len(set(identities)), "duplicate resource identity"
    return docs


@pytest.mark.parametrize("platform", ["eks", "k3s"])
@pytest.mark.parametrize("backend", ["docker", "kubernetes"])
def test_workers_keep_selectors_images_and_env_precedence(platform, backend):
    docs = render("agent-studio", platform, f"app.workloads.workspaceWorker.backend={backend}",
                  "app.image.tag=v9.8.7", "app.workloads.audioWorker.replicas=2")
    deployments = {doc["metadata"]["name"]: doc for doc in docs if doc["kind"] == "Deployment"}
    for name in ["agent-studio-audio-worker", "agent-studio-workspace-worker"]:
        deployment = deployments[name]
        selector = {"app.kubernetes.io/name": name, "app.kubernetes.io/instance": "custom-release"}
        assert deployment["spec"]["selector"]["matchLabels"] == selector
        assert selector.items() <= deployment["spec"]["template"]["metadata"]["labels"].items()
        container = deployment["spec"]["template"]["spec"]["containers"][0]
        assert container["image"].endswith(":v9.8.7")
        assert "ports" not in container
        refs = [{"configMapRef": {"name": "agent-studio"}},
                {"secretRef": {"name": "agent-studio-external"}}]
        if name.endswith("workspace-worker"):
            refs.append({"configMapRef": {"name": "agent-studio-workspace"}})
        assert container["envFrom"] == refs
    assert deployments["agent-studio-audio-worker"]["spec"]["replicas"] == 2
    assert not any(doc["kind"] in {"Service", "Pod"} and "worker" in doc["metadata"]["name"] for doc in docs)
    migration = [doc for doc in docs if doc["kind"] == "Job"]
    if backend == "kubernetes":
        assert migration[0]["spec"]["template"]["spec"]["containers"][0]["image"].endswith(":v9.8.7")


def test_disabled_workers_leave_no_workspace_resources():
    docs = render("agent-studio", "k3s", "app.workloads.audioWorker.enabled=false", "app.workloads.workspaceWorker.enabled=false")
    assert not any("workspace" in doc["metadata"]["name"] or "audio-worker" in doc["metadata"]["name"] for doc in docs)


@pytest.mark.parametrize("backend", ["docker", "kubernetes"])
def test_docker_image_can_be_pinned_by_digest(backend):
    image = "registry.example:5000/docker@sha256:" + "a" * 64
    docs = render("agent-studio", "k3s", f"app.workloads.workspaceWorker.backend={backend}",
                  f"app.workloads.workspaceWorker.dockerImage={image}")
    containers = [container for doc in docs if doc["kind"] == "Deployment"
                  for container in doc["spec"]["template"]["spec"]["containers"]]
    assert next(c for c in containers if c["name"] == "docker")["image"] == image


def test_config_changes_restart_both_workers():
    def checksums(value):
        docs = render("agent-studio", "k3s", f"app.configmap.data.WORKSPACE_NETWORK={value}")
        return {doc["metadata"]["name"]: doc["spec"]["template"]["metadata"]["annotations"]["checksum/config"]
                for doc in docs if doc["kind"] == "Deployment" and doc["metadata"]["name"].endswith("-worker")}

    before, after = checksums("network-before"), checksums("network-after")
    assert len(before) == 2
    assert all(before[name] != after[name] for name in before)


def test_argocd_network_policy_can_be_disabled():
    assert any(doc["kind"] == "NetworkPolicy" for doc in render("mcp-argocd"))
    assert not any(doc["kind"] == "NetworkPolicy" for doc in render("mcp-argocd", "k3s", "networkPolicy.enabled=false"))
