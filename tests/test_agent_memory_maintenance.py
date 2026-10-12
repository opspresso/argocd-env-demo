"""Maintenance must stop every Memory writer and permit an offline Neo4j copy."""
from pathlib import Path
import subprocess

from jinja2 import Environment, FileSystemLoader, StrictUndefined
import pytest
import yaml

ROOT = Path(__file__).resolve().parents[1]


def render(chart, env, tmp_path):
    folder = ROOT / "charts" / chart
    values = Environment(loader=FileSystemLoader(folder), undefined=StrictUndefined).get_template("values-template.yaml.j2").render(env)
    path = tmp_path / f"{chart}.yaml"
    path.write_text(values)
    args = ["helm", "template", chart, str(folder), "-f", str(folder / "values.yaml")]
    phase = folder / f"values-{env['phase']}.yaml"
    if phase.exists():
        args += ["-f", str(phase)]
    result = subprocess.run(args + ["-f", str(path)], capture_output=True, text=True, check=True)
    return [doc for doc in yaml.safe_load_all(result.stdout) if doc]


@pytest.mark.parametrize("platform", ["eks", "k3s"])
@pytest.mark.parametrize("maintenance", [False, True])
def test_memory_web_and_worker_stop_together(platform, maintenance, tmp_path):
    env = yaml.safe_load((ROOT / "env" / f"{platform}-demo.yaml").read_text())
    env["agent_memory_maintenance"] = maintenance
    docs = render("agent-memory", env, tmp_path)
    deployments = {doc["metadata"]["name"]: doc for doc in docs if doc["kind"] == "Deployment"}
    if maintenance or not env["autoscaling"]:
        assert deployments["agent-memory"]["spec"]["replicas"] == (0 if maintenance else env["replicas"])
    else:
        assert "replicas" not in deployments["agent-memory"]["spec"]
    assert deployments["agent-memory-worker"]["spec"]["replicas"] == (0 if maintenance else env["agent_memory"].get("worker_replicas", 1))
    assert any(doc["kind"] == "HorizontalPodAutoscaler" for doc in docs) == (env["autoscaling"] and not maintenance)


@pytest.mark.parametrize("platform", ["eks", "k3s"])
def test_offline_neo4j_keeps_the_data_volume_without_starting_the_database(platform, tmp_path):
    env = yaml.safe_load((ROOT / "env" / f"{platform}-demo.yaml").read_text())
    env["neo4j"]["offline_maintenance"] = True
    docs = render("neo4j", env, tmp_path)
    stateful = next(doc for doc in docs if doc["kind"] == "StatefulSet")
    container = stateful["spec"]["template"]["spec"]["containers"][0]
    assert "Neo4j is not running" in " ".join(container["command"])
    assert "startupProbe" not in container
    assert any(mount["mountPath"] == "/data" for mount in container["volumeMounts"])
    assert stateful["spec"]["volumeClaimTemplates"]
