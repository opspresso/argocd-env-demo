"""Fresh-volume PostgreSQL contracts shared by k3s and OrbStack."""

from pathlib import Path
import shutil
import subprocess

import pytest
import yaml


ROOT = Path(__file__).resolve().parents[1]


@pytest.fixture(params=["k3s/values-k3s-demo.yaml", "orb/values-orb-demo.yaml"])
def manifests(request):
    if not shutil.which("helm"):
        pytest.skip("Helm is required to validate deployment manifests")
    chart = ROOT / "charts/postgresql"
    command = ["helm", "template", "postgresql-test", str(chart), "-f", str(chart / "values.yaml")]
    if request.param:
        command += ["-f", str(chart / request.param)]
    rendered = subprocess.run(command, check=True, text=True, capture_output=True).stdout
    return {doc["kind"]: doc for doc in yaml.safe_load_all(rendered) if doc}


def test_bootstrap_connects_as_the_user_created_by_the_image(manifests):
    container = manifests["StatefulSet"]["spec"]["template"]["spec"]["containers"][0]
    user = next(env["value"] for env in container["env"] if env["name"] == "POSTGRES_USER")
    bootstrap = manifests["Job"]["spec"]["template"]["spec"]["containers"][0]["command"][-1]
    assert f"pg_isready -h postgres -U {user}" in bootstrap
    assert f"psql -h postgres -U {user}" in bootstrap
    assert "ALTER ROLE" not in bootstrap


def test_official_entrypoint_owns_empty_volume_initialization(manifests):
    pod = manifests["StatefulSet"]["spec"]["template"]["spec"]
    assert not pod.get("initContainers")
    container = pod["containers"][0]
    assert "command" not in container
    assert next(env["value"] for env in container["env"] if env["name"] == "PGDATA") == "/var/lib/postgresql/data"
    for probe in ["readinessProbe", "livenessProbe"]:
        command = container[probe]["exec"]["command"][-1]
        assert '"${POSTGRES_USER}"' in command
        assert "$${" not in command
