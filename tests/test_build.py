"""Publishing must validate first and commit only generated chart values."""

import os
from pathlib import Path
import shutil
import subprocess
import sys

import pytest


ROOT = Path(__file__).resolve().parents[1]


@pytest.fixture
def build_repo(tmp_path):
    remote = tmp_path / "origin.git"
    root = tmp_path / "checkout"
    subprocess.run(["git", "init", "--bare", "--initial-branch=main", str(remote)], check=True, capture_output=True)
    subprocess.run(["git", "clone", str(remote), str(root)], check=True, capture_output=True)

    def git(*args):
        return subprocess.run(["git", *args], cwd=root, check=True, capture_output=True, text=True).stdout.strip()

    git("config", "user.name", "Test Bot")
    git("config", "user.email", "test@example.com")
    (root / "scripts").mkdir()
    for name in ("build.sh", "gen_values.py"):
        shutil.copy(ROOT / "scripts" / name, root / "scripts" / name)
    # Isolate Helm's external boundary while exercising the real generator,
    # test runner, shell entrypoint and local git remote.
    (root / "scripts/validate.py").write_text(
        "import os, sys\nfrom pathlib import Path\n"
        "Path('validator-output.txt').write_text('diagnostic')\n"
        "sys.exit(int(os.environ.get('VALIDATE_EXIT', '0')))\n"
    )
    (root / "tests").mkdir()
    (root / "tests/test_contract.py").write_text(
        "import os\ndef test_contract():\n    assert os.environ.get('TEST_FAIL') != 'true'\n"
    )
    (root / ".gitignore").write_text("__pycache__/\n.pytest_cache/\n")
    (root / "env").mkdir()
    (root / "env/eks-test.yaml").write_text("env: eks\ncluster: eks-test\nreplicas: 2\n")
    chart = root / "charts/demo"
    (chart / "eks").mkdir(parents=True)
    (chart / "values-template.yaml.j2").write_text("replicas: {{replicas}}\n")
    (chart / "eks/values-eks-test.yaml").write_text("replicas: 1\n")
    git("add", ".")
    git("commit", "-m", "Initial chart")
    git("push", "origin", "main")

    def build(**overrides):
        environment = os.environ.copy()
        environment.update(GITHUB_PUSH="true", MAIN_BRANCH="main")
        environment.update(overrides)
        environment["PATH"] = str(Path(sys.executable).parent) + os.pathsep + environment["PATH"]
        return subprocess.run(["bash", str(root / "scripts/build.sh")], cwd=tmp_path,
                              env=environment, capture_output=True, text=True)

    return root, git, build


@pytest.mark.parametrize("failure", [{"VALIDATE_EXIT": "1"}, {"TEST_FAIL": "true"}])
def test_failed_checks_do_not_publish(build_repo, failure):
    root, git, build = build_repo
    before = git("rev-parse", "origin/main")
    result = build(**failure)
    assert result.returncode != 0
    assert git("rev-parse", "HEAD") == before
    assert git("rev-parse", "origin/main") == before
    assert git("diff", "--cached", "--name-only") == ""


def test_success_publishes_only_generated_values(build_repo):
    root, git, build = build_repo
    result = build()
    assert result.returncode == 0, result.stdout + result.stderr
    assert git("rev-parse", "HEAD") == git("rev-parse", "origin/main")
    assert git("diff-tree", "--no-commit-id", "--name-only", "-r", "HEAD") == "charts/demo/eks/values-eks-test.yaml"
    assert git("show", "origin/main:charts/demo/eks/values-eks-test.yaml") == "replicas: 2"
    assert git("status", "--porcelain") == "?? validator-output.txt"


def test_dirty_checkout_is_not_overwritten_or_published(build_repo):
    root, git, build = build_repo
    values = root / "charts/demo/eks/values-eks-test.yaml"
    values.write_text("replicas: 99\n")
    before = git("rev-parse", "HEAD")
    result = build()
    assert result.returncode != 0
    assert "clean" in result.stderr
    assert values.read_text() == "replicas: 99\n"
    assert git("rev-parse", "origin/main") == before


@pytest.mark.parametrize("branch", ["main", "feature"])
def test_unrelated_commits_cannot_be_published(build_repo, branch):
    root, git, build = build_repo
    before = git("rev-parse", "origin/main")
    if branch != "main":
        git("checkout", "-b", branch)
    (root / "unrelated.txt").write_text("local work\n")
    git("add", "unrelated.txt")
    git("commit", "-m", "Local work")
    result = build()
    assert result.returncode != 0
    assert git("rev-parse", "origin/main") == before
    assert git("status", "--porcelain") == ""
