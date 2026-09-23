import sys

import pytest

import validate


@pytest.mark.parametrize("exists", [False, True])
def test_empty_or_missing_target_directory_fails(tmp_path, monkeypatch, capsys, exists):
    root = tmp_path / "repo"
    (root / "charts").mkdir(parents=True)
    if exists:
        (root / "apps").mkdir()
    monkeypatch.setattr(validate, "__file__", str(root / "scripts/validate.py"))
    monkeypatch.setattr(sys, "argv", ["validate.py"])
    monkeypatch.chdir(root)
    assert validate.main() == 1
    assert "no" in capsys.readouterr().out.lower()


def test_failed_dependencies_are_not_rendered_for_another_target(monkeypatch):
    targets = [{"chart": "charts/demo", "env_files": [None], "appset": "apps/a.yaml"},
               {"chart": "charts/demo", "env_files": [None], "appset": "apps/b.yaml"}]
    monkeypatch.setattr(sys, "argv", ["validate.py"])
    monkeypatch.setattr(validate, "load_targets", lambda dirs: targets)
    monkeypatch.setattr(validate, "check_templates", lambda only: [])
    monkeypatch.setattr(validate, "update_dependencies", lambda chart: "dependency failed")
    monkeypatch.setattr(validate, "render", lambda *args: pytest.fail("must not render stale dependencies"))
    assert validate.main() == 1


def test_malformed_env_is_reported_as_a_render_failure(tmp_path, monkeypatch, capsys):
    env_file = tmp_path / "bad.yaml"
    env_file.write_text("cluster: [\n")
    target = {"chart": "charts/demo", "env_files": [str(env_file)], "appset": "apps/a.yaml"}
    monkeypatch.setattr(sys, "argv", ["validate.py"])
    monkeypatch.setattr(validate, "load_targets", lambda dirs: [target])
    monkeypatch.setattr(validate, "check_templates", lambda only: [])
    monkeypatch.setattr(validate, "update_dependencies", lambda chart: None)
    assert validate.main() == 1
    assert "FAIL" in capsys.readouterr().out


def test_load_targets_includes_direct_applications(tmp_path):
    apps = tmp_path / "apps" / "k3s"
    apps.mkdir(parents=True)
    (apps / "agent-studio.yaml").write_text(
        """\
apiVersion: argoproj.io/v1alpha1
kind: Application
metadata:
  name: agent-studio-k3s
spec:
  source:
    path: charts/agent-studio
    helm:
      valueFiles:
        - values.yaml
  destination:
    namespace: agent-studio
"""
    )

    targets = validate.load_targets([str(tmp_path / "apps")])

    assert len(targets) == 1
    assert targets[0]["chart"] == "charts/agent-studio"
    assert targets[0]["env_files"] == [None]
    assert targets[0]["value_files"] == ["values.yaml"]
