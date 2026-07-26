#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""GitOps entrypoint driven by repository_dispatch payloads.

Triggered by a ``repository_dispatch`` of type ``gitops``; the client payload
arrives as TG_* environment variables.

With TG_PHASE set the run deploys that single phase. Without it the run fans
out, dispatching one event per phase found in the chart.
"""

import argparse
import json
import os
import re
import subprocess
import sys
import urllib.error
import urllib.request

import chart


REPO_USERNAME = os.environ.get("REPO_USERNAME", "opspresso")
REPO_NAME = os.environ.get("REPO_NAME", "argocd-env-demo")
MAIN_BRANCH = os.environ.get("MAIN_BRANCH", "main")

GIT_USERNAME = "nalbam-bot"
GIT_USEREMAIL = "bot@nalbam.com"

# prod lands on a pull request; every other phase pushes straight to main.
PROD_PHASE = "prod"

PUSH_RETRIES = 3
HTTP_TIMEOUT = 30

NAME_RE = re.compile(r"^[a-z0-9][a-z0-9-]*$")
PHASE_RE = re.compile(r"^[a-z][a-z0-9-]*$")
VERSION_RE = re.compile(r"^[A-Za-z0-9][A-Za-z0-9._-]*$")

ALLOWED_ACTIONS = frozenset({"", "approved"})
ALLOWED_TYPES = frozenset({"helm"})


class ConfigError(Exception):
    """Raised when the dispatch payload is unusable."""


def log(message):
    print("# {}".format(message), flush=True)


def run(cmd, **kwargs):
    print("$ {}".format(" ".join(cmd)), flush=True)
    return subprocess.run(cmd, check=True, **kwargs)


class Config(object):
    """The TG_* dispatch payload, validated.

    Every field reaches a filesystem path, a git ref or an HTTP body, so each is
    checked against an allow-list rather than trusted as sent.
    """

    def __init__(self, env, root):
        self.root = root

        self.username = _require(env, "TG_USERNAME", NAME_RE, default="opspresso")
        self.project = _require(env, "TG_PROJECT", NAME_RE)
        self.version = _require(env, "TG_VERSION", VERSION_RE)
        self.container = _require(env, "TG_CONTAINER", NAME_RE, default="app")

        self.action = env.get("TG_ACTION", "").strip()
        if self.action not in ALLOWED_ACTIONS:
            raise ConfigError(
                "TG_ACTION must be one of {}, got '{}'".format(
                    sorted(ALLOWED_ACTIONS), self.action
                )
            )

        self.type = env.get("TG_TYPE", "").strip() or "helm"
        if self.type not in ALLOWED_TYPES:
            raise ConfigError(
                "TG_TYPE must be one of {}, got '{}'".format(
                    sorted(ALLOWED_TYPES), self.type
                )
            )

        # Empty means "fan out to every phase" rather than a default phase.
        self.phase = env.get("TG_PHASE", "").strip()
        if self.phase:
            if not PHASE_RE.match(self.phase):
                raise ConfigError("TG_PHASE is malformed: '{}'".format(self.phase))
            if self.phase in chart.RESERVED_PHASES:
                raise ConfigError("TG_PHASE is reserved: '{}'".format(self.phase))

        self.github_token = env.get("GITHUB_TOKEN", "").strip()

    @property
    def image(self):
        return "{}/{}:{}".format(self.username, self.project, self.version)

    def require_token(self):
        if not self.github_token:
            raise ConfigError("GITHUB_TOKEN is not set")


def _require(env, key, pattern, default=None):
    value = env.get(key, "").strip() or (default or "")

    if not value:
        raise ConfigError("{} is required".format(key))

    if not pattern.match(value):
        raise ConfigError("{} is malformed: '{}'".format(key, value))

    return value


def build_payload(cfg, phase):
    """The repository_dispatch body. Schema is a contract with the trigger."""
    return {
        "event_type": "gitops",
        "client_payload": {
            "username": cfg.username,
            "project": cfg.project,
            "version": cfg.version,
            "container": cfg.container,
            "action": cfg.action,
            "phase": phase,
            "type": cfg.type,
        },
    }


def post_dispatch(cfg, payload):
    url = "https://api.github.com/repos/{}/{}/dispatches".format(
        REPO_USERNAME, REPO_NAME
    )

    request = urllib.request.Request(
        url, data=json.dumps(payload).encode("utf-8"), method="POST"
    )
    request.add_header("Accept", "application/vnd.github+json")
    request.add_header("Authorization", "Bearer {}".format(cfg.github_token))
    request.add_header("Content-Type", "application/json")

    try:
        with urllib.request.urlopen(request, timeout=HTTP_TIMEOUT) as response:
            if response.status != 204:
                raise ConfigError(
                    "dispatch returned HTTP {}".format(response.status)
                )
    except urllib.error.HTTPError as error:
        # The body carries GitHub's reason (bad ref, missing scope, ...).
        raise ConfigError(
            "dispatch failed: HTTP {} {}".format(
                error.code, error.read().decode("utf-8", "replace").strip()
            )
        )
    except urllib.error.URLError as error:
        raise ConfigError("dispatch failed: {}".format(error.reason))


def cmd_dispatch(cfg, dry_run=False):
    """Fan out one dispatch per phase found in the chart."""
    directory = chart.chart_dir(cfg.root, cfg.project)
    if not os.path.isdir(directory):
        raise ConfigError("chart not found: {}".format(directory))

    phases = chart.discover_phases(cfg.root, cfg.project)
    if not phases:
        raise ConfigError("no deployable phase in {}".format(directory))

    if not dry_run:
        cfg.require_token()

    log("{} -> {}".format(cfg.image, ", ".join(phases)))

    for phase in phases:
        payload = build_payload(cfg, phase)
        log("dispatch {} {}".format(phase, json.dumps(payload["client_payload"])))

        if not dry_run:
            post_dispatch(cfg, payload)

    return 0


def cmd_deploy(cfg, dry_run=False):
    """Write the version into one phase and commit it."""
    if not cfg.phase:
        raise ConfigError("TG_PHASE is required to deploy")

    values = chart.values_path(cfg.root, cfg.project, cfg.phase)
    if not os.path.exists(values):
        raise ConfigError("values file not found: {}".format(values))

    log("{} {}".format(cfg.image, cfg.phase))

    branch = "{}-{}-{}".format(cfg.project, cfg.phase, cfg.version)
    message = "Deploy {} {} {}".format(cfg.project, cfg.phase, cfg.version)
    is_prod = cfg.phase == PROD_PHASE

    if dry_run:
        _write_version(cfg)
        log("dry-run: left the working tree uncommitted")
        return 0

    cfg.require_token()
    _git_config()
    _git_pull()

    # A re-dispatch of a version already on a release branch must not open a
    # second pull request.
    if is_prod and _remote_branch_exists(branch):
        log("{} already exists, nothing to do".format(branch))
        return 0

    if is_prod:
        run(["git", "checkout", "-b", branch])

    _write_version(cfg)

    run(["git", "add", "--all"])

    if _nothing_staged():
        log("{} is already at {}, nothing to commit".format(values, cfg.version))
        return 0

    run(["git", "commit", "-m", message])

    if is_prod:
        run(["git", "push", "origin", branch])
        run(
            [
                "gh", "pr", "create",
                "--base", MAIN_BRANCH,
                "--head", branch,
                "--title", message,
                "--body", "Deploy `{}` to `{}`.".format(cfg.image, cfg.phase),
            ]
        )
    else:
        _push_with_retry()

    return 0


def _write_version(cfg):
    versions = chart.update_versions(
        cfg.root, cfg.project, cfg.phase, cfg.version, cfg.action
    )
    log("updated {}".format(versions))

    values = chart.update_values(
        cfg.root, cfg.project, cfg.phase, cfg.version, cfg.container
    )
    log("updated {}".format(values))


def _git_config():
    run(["git", "config", "user.name", GIT_USERNAME])
    run(["git", "config", "user.email", GIT_USEREMAIL])
    run(["git", "config", "pull.rebase", "true"])


def _git_pull():
    run(["git", "pull", "--rebase", "origin", MAIN_BRANCH])


def _nothing_staged():
    """True when `git add` produced no change - re-deploying the same version.

    Staged rather than working-tree state, so a brand new versions-<phase>.json
    counts instead of being missed as untracked.
    """
    return subprocess.run(["git", "diff", "--cached", "--quiet"]).returncode == 0


def _remote_branch_exists(branch):
    completed = subprocess.run(
        ["git", "ls-remote", "--heads", "origin", branch],
        capture_output=True,
        text=True,
        check=True,
    )
    return bool(completed.stdout.strip())


def _push_with_retry():
    """Concurrent deploys race for main; rebase and retry instead of failing."""
    for attempt in range(1, PUSH_RETRIES + 1):
        try:
            run(["git", "push", "origin", "HEAD:{}".format(MAIN_BRANCH)])
            return
        except subprocess.CalledProcessError:
            if attempt == PUSH_RETRIES:
                raise
            log("push rejected, rebasing and retrying ({}/{})".format(
                attempt, PUSH_RETRIES
            ))
            _git_pull()


def parse_args(argv):
    parser = argparse.ArgumentParser(description="GitOps")
    parser.add_argument(
        "command",
        nargs="?",
        choices=["auto", "dispatch", "deploy", "action"],
        default="auto",
        help="'auto' (default) deploys when TG_PHASE is set, else dispatches",
    )
    parser.add_argument(
        "-n", "--dry-run",
        action="store_true",
        help="update files but do not call GitHub or touch git",
    )
    return parser.parse_args(argv)


def main(argv=None):
    args = parse_args(argv if argv is not None else sys.argv[1:])

    # Chart paths and git both resolve against the repository root, whatever
    # directory the caller happened to be in.
    root = os.path.dirname(os.path.abspath(__file__))
    os.chdir(root)

    command = args.command
    if command == "action":
        log("'action' is deprecated, use 'auto'")
        command = "auto"

    try:
        cfg = Config(os.environ, root)

        if command == "auto":
            command = "deploy" if cfg.phase else "dispatch"

        if command == "deploy":
            return cmd_deploy(cfg, args.dry_run)
        return cmd_dispatch(cfg, args.dry_run)

    except ConfigError as error:
        print("- {}".format(error), file=sys.stderr)
        return 1
    except subprocess.CalledProcessError as error:
        print("- command failed: {}".format(" ".join(error.cmd)), file=sys.stderr)
        return error.returncode or 1


if __name__ == "__main__":
    sys.exit(main())
