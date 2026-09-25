from argparse import Namespace

from jinja2 import UndefinedError
import pytest
import yaml

import gen_values


@pytest.fixture
def project(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    chart = tmp_path / "charts/demo-app"
    chart.mkdir(parents=True)
    (chart / "values-template.yaml.j2").write_text("cluster: {{cluster}}\nreplicas: {{replicas}}\n")
    (tmp_path / "env").mkdir()
    (tmp_path / "env/eks-demo.yaml").write_text("env: eks\ncluster: eks-demo\nreplicas: 2\n")
    return tmp_path, chart, Namespace(reponame="demo-app", platform="eks")


def test_renders_the_selected_platform(project):
    root, chart, args = project
    (root / "env/k3s-demo.yaml").write_text("env: k3s\ncluster: k3s-demo\nreplicas: 1\n")
    gen_values.gen_repos(args)
    assert yaml.safe_load((chart / "eks/values-eks-demo.yaml").read_text()) == {"cluster": "eks-demo", "replicas": 2}
    assert not (chart / "eks/values-k3s-demo.yaml").exists()


def test_missing_variable_does_not_overwrite_existing_values(project):
    root, chart, args = project
    (chart / "eks").mkdir()
    output = chart / "eks/values-eks-demo.yaml"
    output.write_text("original\n")
    (root / "env/eks-demo.yaml").write_text("env: eks\ncluster: eks-demo\n")
    with pytest.raises(UndefinedError):
        gen_values.gen_repos(args)
    assert output.read_text() == "original\n"


def test_missing_template_fails(project):
    root, chart, args = project
    args.reponame = "missing-chart"
    with pytest.raises(FileNotFoundError):
        gen_values.gen_repos(args)


@pytest.mark.parametrize("body", [
    "env: eks\ncluster: other-cluster\nreplicas: 2\n",
    "env: eks\nreplicas: 2\n",
    "env: typo\ncluster: eks-demo\nreplicas: 2\n",
    "env: eks\ncluster: eks-demo\nreplicas: 2\nresources: 'false'\n",
    "env: eks\ncluster: eks-demo\nreplicas: 2\nagent_studio_maintenance: 'false'\n",
    "[]\n",
])
def test_rejects_invalid_cluster_identity(project, body):
    root, chart, args = project
    (root / "env/eks-demo.yaml").write_text(body)
    with pytest.raises(ValueError):
        gen_values.gen_repos(args)
    assert not (chart / "eks/values-eks-demo.yaml").exists()


def test_later_environment_error_does_not_write_earlier_output(project):
    root, chart, args = project
    (root / "env/eks-other.yaml").write_text("env: eks\ncluster: eks-other\n")
    with pytest.raises(UndefinedError):
        gen_values.gen_repos(args)
    assert not (chart / "eks/values-eks-demo.yaml").exists()
