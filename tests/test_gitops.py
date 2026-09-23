#!/usr/bin/env python3
# -*- coding: utf-8 -*-

import json
import subprocess

import pytest
import yaml

import gitops


def env(**overrides):
    base = {
        "TG_USERNAME": "nalbam",
        "TG_PROJECT": "demo-app",
        "TG_VERSION": "v1.2.3",
        "TG_CONTAINER": "app",
        "TG_ACTION": "",
        "TG_PHASE": "alpha",
        "TG_TYPE": "helm",
        "GITHUB_TOKEN": "token",
    }
    base.update(overrides)
    return base


class TestConfig:
    def test_accepts_a_normal_payload(self):
        cfg = gitops.Config(env(), "/repo")

        assert cfg.project == "demo-app"
        assert cfg.phase == "alpha"
        assert cfg.image == "nalbam/demo-app:v1.2.3"
        assert cfg.auto_merge is False

    @pytest.mark.parametrize("value,expected", [
        ("", False), ("false", False), ("true", True), (" TRUE ", True),
    ])
    def test_auto_merge_is_an_explicit_boolean(self, value, expected):
        assert gitops.Config(env(TG_AUTO_MERGE=value), "/repo").auto_merge is expected

    @pytest.mark.parametrize("value", ["1", "0", "yes", "no", "tru"])
    def test_rejects_invalid_auto_merge(self, value):
        with pytest.raises(gitops.ConfigError, match="TG_AUTO_MERGE"):
            gitops.Config(env(TG_AUTO_MERGE=value), "/repo")

    def test_blank_phase_means_fan_out(self):
        assert gitops.Config(env(TG_PHASE=""), "/repo").phase == ""

    def test_defaults_fill_in_blanks(self):
        cfg = gitops.Config(env(TG_CONTAINER="", TG_TYPE=""), "/repo")

        assert cfg.container == "app"
        assert cfg.type == "helm"

    @pytest.mark.parametrize("project", ["../etc", "a/b", "UPPER", "", "-lead"])
    def test_rejects_malformed_project(self, project):
        with pytest.raises(gitops.ConfigError):
            gitops.Config(env(TG_PROJECT=project), "/repo")

    @pytest.mark.parametrize("version", ["", "v1 2", "v1;rm -rf /", "../v1"])
    def test_rejects_malformed_version(self, version):
        with pytest.raises(gitops.ConfigError):
            gitops.Config(env(TG_VERSION=version), "/repo")

    @pytest.mark.parametrize("phase", ["../prod", "Prod", "a b"])
    def test_rejects_malformed_phase(self, phase):
        with pytest.raises(gitops.ConfigError):
            gitops.Config(env(TG_PHASE=phase), "/repo")

    def test_rejects_reserved_phase(self):
        with pytest.raises(gitops.ConfigError):
            gitops.Config(env(TG_PHASE="template"), "/repo")

    def test_rejects_unknown_action(self):
        with pytest.raises(gitops.ConfigError):
            gitops.Config(env(TG_ACTION="rejected"), "/repo")

    def test_rejects_unknown_type(self):
        with pytest.raises(gitops.ConfigError):
            gitops.Config(env(TG_TYPE="kustomize"), "/repo")

    def test_require_token_when_missing(self):
        with pytest.raises(gitops.ConfigError):
            gitops.Config(env(GITHUB_TOKEN=""), "/repo").require_token()


class TestPayload:
    def test_matches_the_dispatch_schema(self):
        cfg = gitops.Config(env(TG_PHASE=""), "/repo")

        assert gitops.build_payload(cfg, "prod") == {
            "event_type": "gitops",
            "client_payload": {
                "username": "nalbam",
                "project": "demo-app",
                "version": "v1.2.3",
                "container": "app",
                "action": "",
                "phase": "prod",
                "type": "helm",
                "auto_merge": False,
            },
        }


class TestParseArgs:
    def test_defaults_to_auto(self):
        args = gitops.parse_args([])

        assert args.command == "auto"
        assert args.dry_run is False
        assert args.auto_merge is False

    def test_auto_merge_flag(self):
        assert gitops.parse_args(["deploy", "--auto-merge"]).auto_merge is True

    def test_accepts_the_legacy_action_argument(self):
        assert gitops.parse_args(["action"]).command == "action"

    def test_dry_run_flag(self):
        assert gitops.parse_args(["deploy", "--dry-run"]).dry_run is True

    def test_rejects_removed_circleci_provider(self):
        with pytest.raises(SystemExit):
            gitops.parse_args(["circleci"])


@pytest.fixture
def deployment_repo(tmp_path, monkeypatch):
    """Exercise real git against a local remote; only GitHub is mocked."""
    remote = tmp_path / "origin.git"
    root = tmp_path / "checkout"
    subprocess.run(["git", "init", "--bare", "--initial-branch=main", str(remote)], check=True)
    subprocess.run(["git", "clone", str(remote), str(root)], check=True)
    monkeypatch.chdir(root)

    def git(*args):
        return subprocess.run(
            ["git", *args], check=True, capture_output=True, text=True
        ).stdout.strip()

    git("config", "user.name", "Test Bot")
    git("config", "user.email", "test@example.com")
    directory = root / "charts" / "demo-app"
    directory.mkdir(parents=True)
    for phase in ("alpha", "prod"):
        (directory / f"values-{phase}.yaml").write_text("app:\n  image:\n    tag: v0.0.1\n")
    (root / "README.md").write_text("original\n")
    git("add", ".")
    git("commit", "-m", "Initial chart")
    git("push", "origin", "main")

    github = {"prs": [], "calls": [], "fail_create": False}
    original_run = gitops.run

    def run(cmd, **kwargs):
        if cmd[0] != "gh":
            return original_run(cmd, **kwargs)
        github["calls"].append(cmd)
        if cmd[1:3] == ["pr", "list"]:
            return subprocess.CompletedProcess(cmd, 0, stdout=json.dumps(github["prs"]))
        assert cmd[1:3] == ["pr", "create"]
        if github["fail_create"]:
            raise subprocess.CalledProcessError(1, cmd)
        github["prs"].append({"state": "OPEN", "url": "https://example.com/pr/1"})
        return subprocess.CompletedProcess(cmd, 0)

    monkeypatch.setattr(gitops, "run", run)
    return root, git, github


class TestDeploy:
    @pytest.mark.parametrize("phase,auto_merge", [
        ("alpha", ""), ("alpha", "false"), ("alpha", "true"), ("prod", "true"),
    ])
    def test_direct_push_updates_only_the_deployment_files(self, deployment_repo, phase, auto_merge):
        root, git, github = deployment_repo
        cfg = gitops.Config(env(TG_PHASE=phase, TG_AUTO_MERGE=auto_merge), str(root))

        assert gitops.cmd_deploy(cfg) == 0

        assert git("rev-parse", "HEAD") == git("rev-parse", "origin/main")
        assert set(git("diff-tree", "--no-commit-id", "--name-only", "-r", "HEAD").splitlines()) == {
            f"charts/demo-app/values-{phase}.yaml", f"charts/demo-app/versions-{phase}.json"
        }
        values = yaml.safe_load(git("show", f"origin/main:charts/demo-app/values-{phase}.yaml"))
        assert values["app"]["image"]["tag"] == cfg.version
        assert github["calls"] == []

    @pytest.mark.parametrize("auto_merge", ["", "false"])
    def test_prod_creates_a_pr_without_changing_main(self, deployment_repo, auto_merge):
        root, git, github = deployment_repo
        before = git("rev-parse", "origin/main")
        cfg = gitops.Config(env(TG_PHASE="prod", TG_AUTO_MERGE=auto_merge), str(root))

        assert gitops.cmd_deploy(cfg) == 0

        assert git("rev-parse", "origin/main") == before
        values = yaml.safe_load(git("show", "origin/demo-app-prod-v1.2.3:charts/demo-app/values-prod.yaml"))
        assert values["app"]["image"]["tag"] == cfg.version
        assert len(github["prs"]) == 1

    def test_recovers_pr_creation_after_branch_was_pushed(self, deployment_repo):
        root, git, github = deployment_repo
        cfg = gitops.Config(env(TG_PHASE="prod"), str(root))
        github["fail_create"] = True
        with pytest.raises(subprocess.CalledProcessError):
            gitops.cmd_deploy(cfg)
        branch_head = git("rev-parse", "origin/demo-app-prod-v1.2.3")
        git("checkout", "main")
        github["fail_create"] = False

        assert gitops.cmd_deploy(cfg) == 0

        assert len(github["prs"]) == 1
        assert git("rev-parse", "origin/demo-app-prod-v1.2.3") == branch_head

    @pytest.mark.parametrize("kind", ["unstaged", "staged", "untracked"])
    def test_rejects_unrelated_work_without_touching_it(self, deployment_repo, kind):
        root, git, github = deployment_repo
        before = git("rev-parse", "HEAD")
        path = root / ("notes.txt" if kind == "untracked" else "README.md")
        path.write_text("user change\n")
        if kind == "staged":
            git("add", str(path))
        status = git("status", "--porcelain")
        cfg = gitops.Config(env(), str(root))

        with pytest.raises(gitops.ConfigError, match="clean"):
            gitops.cmd_deploy(cfg)

        assert git("rev-parse", "origin/main") == before
        assert git("status", "--porcelain") == status
        assert path.read_text() == "user change\n"
        assert github["calls"] == []

    @pytest.mark.parametrize("state", ["OPEN", "CLOSED", "MERGED"])
    def test_repeated_prod_does_not_duplicate_or_reopen_a_pr(self, deployment_repo, state):
        root, git, github = deployment_repo
        cfg = gitops.Config(env(TG_PHASE="prod"), str(root))
        gitops.cmd_deploy(cfg)
        git("checkout", "main")
        github["prs"][0]["state"] = state

        assert gitops.cmd_deploy(cfg) == 0

        assert len([cmd for cmd in github["calls"] if cmd[1:3] == ["pr", "create"]]) == 1

    def test_auto_merge_can_deploy_a_version_with_an_existing_pr(self, deployment_repo):
        root, git, github = deployment_repo
        cfg = gitops.Config(env(TG_PHASE="prod"), str(root))
        gitops.cmd_deploy(cfg)
        git("checkout", "main")
        github["calls"].clear()
        cfg.auto_merge = True

        assert gitops.cmd_deploy(cfg) == 0

        values = yaml.safe_load(git("show", "origin/main:charts/demo-app/values-prod.yaml"))
        assert values["app"]["image"]["tag"] == cfg.version
        assert github["calls"] == []

    @pytest.mark.parametrize("phase,auto_merge", [("alpha", "false"), ("prod", "true")])
    @pytest.mark.parametrize("action", ["", "approved"])
    def test_repeated_direct_deploy_does_not_commit(self, deployment_repo, phase, auto_merge, action):
        root, git, github = deployment_repo
        cfg = gitops.Config(env(TG_PHASE=phase, TG_AUTO_MERGE=auto_merge, TG_ACTION=action), str(root))
        gitops.cmd_deploy(cfg)
        before = git("rev-parse", "HEAD")

        assert gitops.cmd_deploy(cfg) == 0

        assert git("rev-parse", "HEAD") == before
        assert git("status", "--porcelain") == ""
        assert github["calls"] == []

    def test_prod_already_on_main_leaves_no_empty_branch(self, deployment_repo):
        root, git, github = deployment_repo
        cfg = gitops.Config(env(TG_PHASE="prod", TG_AUTO_MERGE="true"), str(root))
        gitops.cmd_deploy(cfg)
        cfg.auto_merge = False

        assert gitops.cmd_deploy(cfg) == 0

        assert git("branch", "--show-current") == "main"
        assert git("branch", "--list", "demo-app-prod-v1.2.3") == ""
        assert github["calls"] == []

    @pytest.mark.parametrize("branch", ["feature", "main"])
    def test_refuses_to_publish_unrelated_commits(self, deployment_repo, branch):
        root, git, github = deployment_repo
        before = git("rev-parse", "origin/main")
        if branch != "main":
            git("checkout", "-b", branch)
        (root / "README.md").write_text("local commit\n")
        git("add", "README.md")
        git("commit", "-m", "Unrelated work")
        local_head = git("rev-parse", "HEAD")

        with pytest.raises(gitops.ConfigError, match="branch|unpublished"):
            gitops.cmd_deploy(gitops.Config(env(), str(root)))

        assert git("rev-parse", "HEAD") == local_head
        assert git("rev-parse", "origin/main") == before
        assert github["calls"] == []

    def test_cli_auto_merge_overrides_false_env_for_prod(self, deployment_repo, monkeypatch):
        root, git, github = deployment_repo
        for key, value in env(TG_PHASE="prod", TG_AUTO_MERGE="false").items():
            monkeypatch.setenv(key, value)
        monkeypatch.setattr(gitops, "__file__", str(root / "scripts" / "gitops.py"))

        assert gitops.main(["deploy", "--auto-merge"]) == 0

        values = yaml.safe_load(git("show", "origin/main:charts/demo-app/values-prod.yaml"))
        assert values["app"]["image"]["tag"] == "v1.2.3"
        assert github["calls"] == []

    @pytest.mark.parametrize("timing", ["before_deploy", "before_push"])
    def test_prod_direct_push_preserves_concurrent_main_changes(self, deployment_repo, monkeypatch, timing):
        root, git, github = deployment_repo
        peer = root.parent / "peer"
        subprocess.run(["git", "clone", str(root.parent / "origin.git"), str(peer)], check=True)

        def peer_git(*args):
            subprocess.run(["git", "-C", str(peer), *args], check=True, capture_output=True)

        peer_git("config", "user.name", "Another Bot")
        peer_git("config", "user.email", "another@example.com")
        (peer / "README.md").write_text("concurrent update\n")
        peer_git("add", "README.md")
        peer_git("commit", "-m", "Concurrent update")
        if timing == "before_deploy":
            peer_git("push", "origin", "main")

        original_run = gitops.run
        pushes = []

        def run(cmd, **kwargs):
            if cmd == ["git", "push", "origin", "HEAD:main"]:
                pushes.append(cmd)
                if timing == "before_push" and len(pushes) == 1:
                    peer_git("push", "origin", "main")
            return original_run(cmd, **kwargs)

        monkeypatch.setattr(gitops, "run", run)
        cfg = gitops.Config(env(TG_PHASE="prod", TG_AUTO_MERGE="true"), str(root))
        assert gitops.cmd_deploy(cfg) == 0

        assert len(pushes) == (2 if timing == "before_push" else 1)
        assert git("show", "origin/main:README.md") == "concurrent update"
        values = yaml.safe_load(git("show", "origin/main:charts/demo-app/values-prod.yaml"))
        assert values["app"]["image"]["tag"] == cfg.version
        assert git("status", "--porcelain") == ""
        assert github["calls"] == []

    def test_invalid_prod_branch_fails_before_writing_chart(self, deployment_repo):
        root, git, github = deployment_repo
        before = git("rev-parse", "HEAD")
        cfg = gitops.Config(env(TG_PHASE="prod", TG_VERSION="v1..2"), str(root))

        with pytest.raises(subprocess.CalledProcessError):
            gitops.cmd_deploy(cfg)

        assert git("rev-parse", "HEAD") == before
        assert git("status", "--porcelain") == ""
        assert github["calls"] == []

    def test_dry_run_updates_files_without_git_or_github(self, deployment_repo, monkeypatch):
        root, git, github = deployment_repo
        before = git("rev-parse", "HEAD")
        cfg = gitops.Config(env(TG_PHASE="prod", TG_AUTO_MERGE="true", GITHUB_TOKEN=""), str(root))

        def unexpected_run(*args, **kwargs):
            pytest.fail("dry-run must not run git or gh")

        monkeypatch.setattr(gitops, "run", unexpected_run)
        assert gitops.cmd_deploy(cfg, dry_run=True) == 0

        assert git("rev-parse", "HEAD") == before
        assert git("rev-parse", "origin/main") == before
        values = yaml.safe_load((root / "charts/demo-app/values-prod.yaml").read_text())
        assert values["app"]["image"]["tag"] == "v1.2.3"
        assert github["calls"] == []


def test_index_read_errors_are_not_treated_as_changes(monkeypatch):
    monkeypatch.setattr(
        gitops.subprocess, "run",
        lambda cmd: subprocess.CompletedProcess(cmd, 128),
    )
    with pytest.raises(subprocess.CalledProcessError) as error:
        gitops._nothing_staged()
    assert error.value.returncode == 128


class TestDispatch:
    @pytest.mark.parametrize("auto_merge,expected", [("", False), ("false", False), ("true", True)])
    def test_fan_out_preserves_auto_merge(self, deployment_repo, monkeypatch, auto_merge, expected):
        root, git, github = deployment_repo
        payloads = []
        monkeypatch.setattr(gitops, "post_dispatch", lambda cfg, payload: payloads.append(payload))
        cfg = gitops.Config(env(TG_PHASE="", TG_AUTO_MERGE=auto_merge), str(root))

        assert gitops.cmd_dispatch(cfg) == 0

        assert [payload["client_payload"]["phase"] for payload in payloads] == ["alpha", "prod"]
        for payload in payloads:
            assert payload["client_payload"]["auto_merge"] is expected
            dispatched_env = {"TG_" + key.upper(): str(value) for key, value in payload["client_payload"].items()}
            assert gitops.Config(dispatched_env, str(root)).auto_merge is expected
        assert git("status", "--porcelain") == ""
        assert github["calls"] == []
