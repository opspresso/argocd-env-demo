"""Verify rendered containers, including upstream defaults and initialization hooks."""

from pathlib import Path
import shutil
import subprocess

import pytest
import yaml
from jinja2 import Environment, FileSystemLoader

from workload_policy import policy_errors


ROOT = Path(__file__).resolve().parents[1]


def render(chart, value_files, extra_args=()):
    if not shutil.which("helm"):
        pytest.skip("Helm is required to validate deployment manifests")
    chart_path = ROOT / chart
    definition = yaml.safe_load((chart_path / "Chart.yaml").read_text())
    if definition.get("dependencies") and not list((chart_path / "charts").glob("*.tgz")):
        pytest.skip(f"Run helm dependency update {chart} before this render check")
    command = ["helm", "template", "local-test", str(chart_path)]
    for value_file in value_files:
        command += ["-f", str(chart_path / value_file)]
    return subprocess.run(command + list(extra_args), capture_output=True, text=True)


def containers(value):
    if isinstance(value, dict):
        for key, child in value.items():
            if key in {"containers", "initContainers", "ephemeralContainers"}:
                yield from child or []
            else:
                yield from containers(child)
    elif isinstance(value, list):
        for child in value:
            yield from containers(child)


@pytest.mark.parametrize("application", sorted(path for platform in ("k3s", "local") for path in (ROOT / "apps" / platform).glob("*.yaml")), ids=lambda path: f"{path.parent.name}-{path.stem}")
def test_local_platforms_have_no_resources_or_autoscaling(application):
    source = yaml.safe_load(application.read_text())["spec"]["source"]
    result = render(source["path"], source["helm"]["valueFiles"])
    assert result.returncode == 0, result.stderr
    assert policy_errors(result.stdout, application.parent.name) == []
    checked = list(containers(list(yaml.safe_load_all(result.stdout))))
    assert checked
    for container in checked:
        assert not container.get("resources"), container["name"]


def test_neo4j_default_resource_validation_is_preserved():
    result = render("charts/neo4j", ["values.yaml"], ["--set", "ssmPrefix=/k8s/eks-demo"])
    assert result.returncode == 0, result.stderr
    workload = next(doc for doc in yaml.safe_load_all(result.stdout) if doc and doc["kind"] == "StatefulSet")
    resources = workload["spec"]["template"]["spec"]["containers"][0]["resources"]
    assert resources["requests"] == {"cpu": "1000m", "memory": "2Gi"}
    assert resources["limits"] == resources["requests"]


def test_workspace_docker_volume_has_only_one_owner_during_rollout():
    result = render("charts/agent-studio", ["values.yaml", "values-alpha.yaml", "k3s/values-k3s-demo.yaml"])
    assert result.returncode == 0, result.stderr
    documents = [doc for doc in yaml.safe_load_all(result.stdout) if doc]
    worker = next(doc for doc in documents if doc["kind"] == "Deployment" and doc["metadata"]["name"] == "agent-studio-workspace-worker")
    spec = worker["spec"]
    docker = next(container for container in spec["template"]["spec"]["containers"] if container["name"] == "docker")
    mount = next(mount for mount in docker["volumeMounts"] if mount["mountPath"] == "/var/lib/docker")
    volume = next(volume for volume in spec["template"]["spec"]["volumes"] if volume["name"] == mount["name"])
    assert volume["persistentVolumeClaim"]["claimName"] == "agent-studio-workspace-docker"
    assert spec["replicas"] == 1
    assert spec.get("strategy", {}).get("type") == "Recreate"


@pytest.mark.parametrize("setting", ["cpu=100m", "memory=512Mi"])
def test_neo4j_still_rejects_invalid_explicit_resources(setting):
    result = render("charts/neo4j", ["values.yaml"], ["--set", "ssmPrefix=/k8s/eks-demo", "--set", f"neo4jdb.neo4j.resources.{setting}"])
    assert result.returncode != 0
    assert "less than minimum" in result.stderr


@pytest.mark.parametrize("chart", ["mcp-argocd", "mcp-brave-search", "mcp-cloudwatch", "mcp-grafana", "mcp-kubernetes"])
def test_mcp_flags_are_independent_of_platform_routing(chart):
    context = yaml.safe_load((ROOT / "env/eks-demo.yaml").read_text())
    context.update(resources=False, autoscaling=False)
    template = Environment(loader=FileSystemLoader(ROOT / "charts" / chart)).get_template("values-template.yaml.j2")
    values = yaml.safe_load(template.render(context))["app"]
    assert values["resources"] is None
    assert values["autoscaling"]["enabled"] is False
