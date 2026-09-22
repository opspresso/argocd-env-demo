"""Provisioning must preserve existing passwords and never log them."""

from unittest.mock import patch

import pytest

import bootstrap_agent_platform as bootstrap


def test_check_reports_missing_parameters_without_writes(capsys):
    with patch.object(bootstrap, "aws", return_value={"Parameters": []}) as aws:
        assert bootstrap.bootstrap("eks-demo", "ap-northeast-2") == 1
    assert aws.call_count == 1
    assert "6 missing" in capsys.readouterr().out


def test_apply_creates_consistent_securestrings_without_overwrite_or_secret_output(capsys):
    with patch.object(bootstrap, "aws", return_value={"Parameters": []}) as aws:
        assert bootstrap.bootstrap("eks-demo", "ap-northeast-2", apply=True) == 0
    writes = [call.kwargs["payload"] for call in aws.call_args_list[1:]]
    assert len(writes) == 6
    assert all(entry["Type"] == "SecureString" and entry["Overwrite"] is False for entry in writes)
    values = {entry["Name"]: entry["Value"] for entry in writes}
    prefix = "/k8s/eks-demo"
    password = values[f"{prefix}/agent-studio/postgres-password"]
    assert f":{password}@" in values[f"{prefix}/agent-memory/database-url"]
    assert f":{password}@" in values[f"{prefix}/agent-studio/database-url"]
    assert values[f"{prefix}/agent-memory/neo4j-auth"] == f"neo4j/{values[f'{prefix}/agent-memory/neo4j-password']}"
    output = capsys.readouterr().out
    assert all(value not in output for value in values.values())


def test_existing_parameters_are_not_rotated():
    values = bootstrap.parameter_values("/k8s/eks-demo", {})
    response = {"Parameters": [{"Name": name, "Value": value} for name, value in values.items()]}
    with patch.object(bootstrap, "aws", return_value=response) as aws:
        assert bootstrap.bootstrap("eks-demo", "ap-northeast-2", apply=True) == 0
    assert aws.call_count == 1


def test_partial_inconsistent_installation_fails_before_creating_anything():
    response = {"Parameters": [{
        "Name": "/k8s/eks-demo/agent-studio/database-url",
        "Value": "postgresql://old:password@old-host/agent_studio"
    }]}
    with patch.object(bootstrap, "aws", return_value=response) as aws:
        with pytest.raises(RuntimeError, match="Inconsistent connection parameters"):
            bootstrap.bootstrap("eks-demo", "ap-northeast-2", apply=True)
    assert aws.call_count == 1
