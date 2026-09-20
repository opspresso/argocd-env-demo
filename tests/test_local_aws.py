from pathlib import Path

from jinja2 import Environment, FileSystemLoader
import pytest
import yaml


ROOT = Path(__file__).resolve().parents[1]


@pytest.mark.parametrize("env_file", sorted((ROOT / "env").glob("*.yaml")), ids=lambda path: path.stem)
def test_cloudwatch_uses_runtime_credentials_without_a_secret(env_file):
    context = yaml.safe_load(env_file.read_text())
    template = Environment(loader=FileSystemLoader(ROOT / "charts/mcp-cloudwatch")).get_template("values-template.yaml.j2")
    if context["env"] != "local":
        context["aws_local"] = {"profile": "unused", "config_file": "/unused/config", "credentials_file": "/unused/credentials"}
    app = yaml.safe_load(template.render(context))["app"]
    assert "additionalSecret" not in app
    if context["env"] != "local":
        assert "extraVolumes" not in app
        assert "AWS_PROFILE" not in app["configmap"]["data"]
        return
    local = context["aws_local"]
    variables = app["configmap"]["data"]
    assert variables["AWS_PROFILE"] == local["profile"]
    assert variables["AWS_CONFIG_FILE"] == "/aws/config"
    assert variables["AWS_SHARED_CREDENTIALS_FILE"] == "/aws/credentials"
    paths = {volume["hostPath"]["path"] for volume in app["extraVolumes"]}
    assert paths == {local["config_file"], local["credentials_file"]}
    mounts = {mount["name"]: mount for mount in app["extraVolumeMounts"]}
    for volume in app["extraVolumes"]:
        assert volume["hostPath"]["type"] == "File"
        assert mounts[volume["name"]]["readOnly"] is True
    assert "securityContext" not in app
