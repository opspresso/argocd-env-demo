#!/usr/bin/env python3
# -*- coding: utf-8 -*-

import os
import sys

import pytest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

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
            },
        }


class TestParseArgs:
    def test_defaults_to_auto(self):
        args = gitops.parse_args([])

        assert args.command == "auto"
        assert args.dry_run is False

    def test_accepts_the_legacy_action_argument(self):
        assert gitops.parse_args(["action"]).command == "action"

    def test_dry_run_flag(self):
        assert gitops.parse_args(["deploy", "--dry-run"]).dry_run is True

    def test_rejects_removed_circleci_provider(self):
        with pytest.raises(SystemExit):
            gitops.parse_args(["circleci"])
