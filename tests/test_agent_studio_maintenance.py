"""A database cutover can stop only Studio writers in either cluster."""

from pathlib import Path
import subprocess

from jinja2 import Environment, FileSystemLoader, StrictUndefined
import pytest
import yaml


ROOT = Path(__file__).resolve().parents[1]
CHART = ROOT / "charts" / "agent-studio"


@pytest.mark.parametrize("platform", ["k3s", "eks"])
@pytest.mark.parametrize("legacy_docker", [False, True])
def test_maintenance_stops_studio_writers_without_removing_dependencies(platform, legacy_docker, tmp_path):
    if not list((CHART / "charts").glob("*.tgz")):
        pytest.skip("Run helm dependency update charts/agent-studio")
    env = yaml.safe_load((ROOT / "env" / f"{platform}-demo.yaml").read_text())
    env["agent_studio_maintenance"] = True
    env["workspace_legacy_docker"] = legacy_docker
    jinja = Environment(loader=FileSystemLoader(CHART), undefined=StrictUndefined)
    rendered = jinja.get_template("values-template.yaml.j2").render(env)
    values = yaml.safe_load(rendered)
    assert values["app"]["replicaCount"] == 0
    assert values["app"]["autoscaling"]["enabled"] is False
    assert values["app"]["workloads"]["audioWorker"]["replicas"] == 0
    assert values["app"]["workloads"]["workspaceWorker"]["replicas"] == 0
    assert values["app"]["workloads"]["scheduleTicker"]["replicas"] == 0

    target = tmp_path / "maintenance.yaml"
    target.write_text(rendered)
    result = subprocess.run([
        "helm", "template", "agent-studio", str(CHART),
        "-f", str(CHART / "values.yaml"),
        "-f", str(CHART / f"values-{env['phase']}.yaml"),
        "-f", str(target),
    ], capture_output=True, text=True, check=True)
    docs = [doc for doc in yaml.safe_load_all(result.stdout) if doc]
    deployments = {doc["metadata"]["name"]: doc for doc in docs if doc["kind"] == "Deployment"}
    names = ["agent-studio", "agent-studio-audio-worker", "agent-studio-workspace-worker", "agent-studio-ticker"]
    if values["app"]["workloads"]["workspaceWorker"]["backend"] == "kubernetes" and legacy_docker:
        names.append("agent-studio-workspace-docker")
    else:
        assert "agent-studio-workspace-docker" not in deployments
    for name in names:
        assert deployments[name]["spec"]["replicas"] == 0
    assert not any(doc["kind"] == "HorizontalPodAutoscaler" and doc["metadata"]["name"] == "agent-studio" for doc in docs)
    assert not any(doc["kind"] == "CronJob" for doc in docs)
