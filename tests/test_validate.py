import validate


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
