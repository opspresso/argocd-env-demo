"""Secret bootstrap preserves identity, scopes and all existing credentials."""
import hashlib
import json
from unittest.mock import patch
import pytest
import bootstrap_agent_platform as bootstrap

PREFIX = "/k8s/k3s-demo"


def fake_ssm(existing):
    def invoke(_region, service, action, *args, payload=None):
        if action == "get-parameters":
            names = args[args.index("--names") + 1:args.index("--with-decryption")]
            assert len(names) <= 10
            return {"Parameters": [{"Name": name, "Value": existing[name]} for name in names if name in existing]}
        assert service == "ssm" and action == "put-parameter"
        return {}
    return invoke


def test_check_reports_missing_without_writes_or_fabricated_installation_ids(capsys):
    with patch.object(bootstrap, "aws", side_effect=fake_ssm({})) as aws:
        assert bootstrap.bootstrap("k3s-demo", "ap-northeast-2") == 1
    assert all(call.args[2] == "get-parameters" for call in aws.call_args_list)
    output = capsys.readouterr().out
    assert "agent-memory/organization-id" in output and "agent-librio/audio-models" in output
    desired = bootstrap.parameter_values(PREFIX, {})
    assert f"{PREFIX}/agent-memory/organization-id" not in desired
    assert f"{PREFIX}/agent-librio/organization-id" not in desired
    assert f"{PREFIX}/agent-forge/model-channels" not in desired
    assert not any("neo4j" in name for name in desired)


def test_apply_preserves_db_password_and_derives_scoped_secrets_without_logging(capsys):
    password = "existing-password:escaped/@"
    existing = {f"{PREFIX}/agent-studio/postgres-password": password}
    with patch.object(bootstrap, "aws", side_effect=fake_ssm(existing)) as aws:
        assert bootstrap.bootstrap("k3s-demo", "ap-northeast-2", apply=True) == 0
    writes = [call.kwargs["payload"] for call in aws.call_args_list if call.args[2] == "put-parameter"]
    assert all(entry["Type"] == "SecureString" and entry["Overwrite"] is False for entry in writes)
    values = {**existing, **{entry["Name"]: entry["Value"] for entry in writes}}
    assert values[f"{PREFIX}/agent-platform/database-url"].endswith(":5432/agent_platform")
    assert "existing-password%3Aescaped%2F%40@" in values[f"{PREFIX}/agent-platform/database-url"]
    assert not any(entry["Name"].endswith("/agent-studio/postgres-password") for entry in writes)
    assert not any(entry["Name"].endswith("/agent-studio/database-url") for entry in writes)
    delegator = json.loads(values[f"{PREFIX}/agent-forge/delegators"])[0]
    assert delegator["policyRequired"] is True
    assert delegator["secret"] == values[f"{PREFIX}/agent-forge/delegation-secret"]
    credential = json.loads(values[f"{PREFIX}/agent-forge/credentials"])[0]
    assert credential["scopes"] == ["workspace:read"]
    assert credential["tokenSha256"] == hashlib.sha256(values[f"{PREFIX}/agent-forge/metrics-bearer-token"].encode()).hexdigest()
    for name in ("forge", "librio"):
        policy = json.loads(values[f"{PREFIX}/agent-{name}/issuer-policies"])[0]
        assert policy["secret"] == values[f"{PREFIX}/agent-{name}/policy-secret"]
        assert policy["secret"] != values[f"{PREFIX}/agent-{name}/delegation-secret"]
        assert policy["url"] == f"http://agent-studio.agent-studio.svc.cluster.local:3000/api/services/{name}/model-policy"
    output = capsys.readouterr().out
    assert all(value not in output for value in values.values())


def test_existing_parameters_are_never_rotated_and_json_format_is_irrelevant():
    values = bootstrap.parameter_values(PREFIX, {})
    key = f"{PREFIX}/agent-forge/delegators"
    values[key] = json.dumps(json.loads(values[key]), indent=2)
    with patch.object(bootstrap, "aws", side_effect=fake_ssm(values)) as aws:
        assert bootstrap.bootstrap("k3s-demo", "ap-northeast-2", apply=True) == 0
    assert all(call.args[2] == "get-parameters" for call in aws.call_args_list)


@pytest.mark.parametrize("key", ["agent-platform/database-url", "agent-forge/delegators", "agent-forge/credentials"])
def test_inconsistent_existing_connection_or_authority_fails_before_any_write(key):
    existing = {f"{PREFIX}/{key}": "inconsistent"}
    with patch.object(bootstrap, "aws", side_effect=fake_ssm(existing)) as aws:
        with pytest.raises(RuntimeError, match="Inconsistent connection parameters"):
            bootstrap.bootstrap("k3s-demo", "ap-northeast-2", apply=True)
    assert all(call.args[2] == "get-parameters" for call in aws.call_args_list)
