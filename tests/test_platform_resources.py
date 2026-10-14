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
def test_local_platforms_follow_resource_and_autoscaling_policy(application):
    source = yaml.safe_load(application.read_text())["spec"]["source"]
    result = render(source["path"], source["helm"]["valueFiles"])
    assert result.returncode == 0, result.stderr
    assert policy_errors(result.stdout, application.parent.name) == []
    checked = list(containers(list(yaml.safe_load_all(result.stdout))))
    assert checked
    for container in checked:
        assert not container.get("resources"), container["name"]


@pytest.mark.parametrize("chart", ["mcp-argocd", "mcp-cloudwatch", "mcp-grafana", "mcp-kubernetes"])
def test_mcp_flags_are_independent_of_platform_routing(chart):
    context = yaml.safe_load((ROOT / "env/eks-demo.yaml").read_text())
    context.update(resources=False, autoscaling=False)
    template = Environment(loader=FileSystemLoader(ROOT / "charts" / chart)).get_template("values-template.yaml.j2")
    values = yaml.safe_load(template.render(context))["app"]
    assert values["resources"] is None
    assert values["autoscaling"]["enabled"] is False
