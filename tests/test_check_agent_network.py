import json
from types import SimpleNamespace

import pytest

import check_agent_network


@pytest.mark.parametrize("kind,containers,legacy", [
    ("agent-studio-workspace-worker", ["workspace-worker"], False),
    ("agent-studio-workspace-worker", ["workspace-worker", "docker"], True),
    ("agent-studio-workspace-docker", ["daemon"], True),
])
def test_missing_service_is_skipped_only_after_confirming_no_legacy_compute(monkeypatch, capsys, kind, containers, legacy):
    pod = {"metadata": {"labels": {"app.kubernetes.io/name": kind}},
           "spec": {"containers": [{"name": name} for name in containers]}}

    def run(args, **kwargs):
        assert "exec" not in args
        return SimpleNamespace(stdout=json.dumps({"items": [] if "services" in args else [pod]}))

    monkeypatch.setattr(check_agent_network.subprocess, "run", run)
    if legacy:
        with pytest.raises(RuntimeError, match="Legacy Docker Pods remain"):
            check_agent_network.check("fixture")
    else:
        check_agent_network.check("fixture")
        output = capsys.readouterr().out
        assert output.startswith("SKIP:") and "PASS" not in output
