from pathlib import Path

import yaml
from jinja2 import Environment, FileSystemLoader


ROOT = Path(__file__).resolve().parents[1]


def test_local_applications_use_the_existing_local_controller():
    root = yaml.safe_load((ROOT / "apps-local.yaml").read_text())
    assert root["metadata"]["namespace"] == root["spec"]["destination"]["namespace"] == "argocd"
    assert root["spec"]["project"] == "apps"
    for path in (ROOT / "apps/local").glob("*.yaml"):
        application = yaml.safe_load(path.read_text())
        assert application["metadata"]["namespace"] == "argocd"
        assert application["spec"]["project"] == "apps"


def test_argocd_mcp_uses_local_server_and_local_token_only_on_orb():
    template = Environment(loader=FileSystemLoader(ROOT / "charts/mcp-argocd")).get_template("values-template.yaml.j2")
    for platform in ("local", "k3s", "eks"):
        context = yaml.safe_load((ROOT / "env" / f"{platform}-demo.yaml").read_text())
        app = yaml.safe_load(template.render(context))["app"]
        if platform == "local":
            assert app["configmap"]["data"]["ARGOCD_BASE_URL"] == "http://argocd-server.argocd.svc.cluster.local"
            assert app["externalSecrets"]["data"] == [{"key": "/k8s/local-demo/mcp-argocd/argocd-api-token", "name": "ARGOCD_API_TOKEN"}]
        else:
            assert app["configmap"]["data"]["ARGOCD_BASE_URL"] == "http://argocd-server.argocd.svc.cluster.local"
            assert "externalSecrets" not in app
