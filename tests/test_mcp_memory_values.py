from pathlib import Path

import yaml


ROOT = Path(__file__).resolve().parents[1]
CHART = ROOT / "charts" / "mcp-memory"


def test_mcp_memory_uses_postgres_without_legacy_s3_settings() -> None:
    template = yaml.safe_load((CHART / "values-template.yaml.j2").read_text())
    data = template["app"]["configmap"]["data"]

    assert data["EMBEDDING_PROVIDER"] == "bedrock"
    assert {"VECTOR_BUCKET", "VECTOR_INDEX", "STATE_BUCKET"}.isdisjoint(data)


def test_mcp_memory_receives_its_database_url_from_parameter_store() -> None:
    common = yaml.safe_load((CHART / "values.yaml").read_text())["app"]
    phase = yaml.safe_load((CHART / "values-alpha.yaml").read_text())["app"]

    assert common["externalSecrets"]["enabled"] is True
    assert common["externalSecrets"]["secretStoreRef"] == {
        "kind": "ClusterSecretStore",
        "name": "parameter-store",
    }
    assert phase["externalSecrets"]["data"] == [
        {
            "key": "/k8s/common/mcp-memory/database-url",
            "name": "DATABASE_URL",
        }
    ]
