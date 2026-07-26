#!/usr/bin/env python3
# -*- coding: utf-8 -*-

import base64
import datetime
import json
import os
import sys

import pytest
import yaml

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import chart


VALUES = """\
app:
  configmap:
    data:
      VERSION: v0.0.1
    enabled: true
  env:
  - name: ENV_HASH
    value: deadbeef
  - name: VERSION
    value: v0.0.1
  image:
    tag: v0.0.1
"""


@pytest.fixture
def root(tmp_path):
    (tmp_path / "charts" / "demo-app").mkdir(parents=True)
    return str(tmp_path)


def write_values(root, phase, body=VALUES):
    path = chart.values_path(root, "demo-app", phase)
    with open(path, "w") as file:
        file.write(body)
    return path


def read_values(root, phase):
    with open(chart.values_path(root, "demo-app", phase)) as file:
        return yaml.safe_load(file)


def env_of(docs, name):
    return [e["value"] for e in docs["app"]["env"] if e["name"] == name]


class TestDiscoverPhases:
    def test_finds_values_files(self, root):
        write_values(root, "alpha")
        write_values(root, "prod")

        assert chart.discover_phases(root, "demo-app") == ["alpha", "prod"]

    def test_excludes_template(self, root):
        write_values(root, "alpha")
        write_values(root, "template")

        assert chart.discover_phases(root, "demo-app") == ["alpha"]

    def test_ignores_unrelated_files(self, root):
        write_values(root, "alpha")
        write_values(root, "demo-b")

        directory = chart.chart_dir(root, "demo-app")
        for name in ["values.yaml", "Chart.yaml", "versions-alpha.json"]:
            with open(os.path.join(directory, name), "w") as file:
                file.write("{}\n")

        assert chart.discover_phases(root, "demo-app") == ["alpha", "demo-b"]

    def test_empty_chart(self, root):
        assert chart.discover_phases(root, "demo-app") == []


class TestUpdateValues:
    def test_replaces_version_everywhere(self, root):
        write_values(root, "alpha")

        chart.update_values(root, "demo-app", "alpha", "v1.2.3", "app")
        docs = read_values(root, "alpha")

        assert docs["app"]["image"]["tag"] == "v1.2.3"
        assert docs["app"]["configmap"]["data"]["VERSION"] == "v1.2.3"
        assert env_of(docs, "VERSION") == ["v1.2.3"]

    def test_env_hash_changes_with_version(self, root):
        write_values(root, "alpha")

        chart.update_values(root, "demo-app", "alpha", "v1.2.3", "app")
        first = env_of(read_values(root, "alpha"), "ENV_HASH")[0]

        chart.update_values(root, "demo-app", "alpha", "v1.2.4", "app")
        second = env_of(read_values(root, "alpha"), "ENV_HASH")[0]

        assert first != second

    def test_is_idempotent(self, root):
        path = write_values(root, "alpha")

        chart.update_values(root, "demo-app", "alpha", "v1.2.3", "app")
        with open(path, "rb") as file:
            once = file.read()

        chart.update_values(root, "demo-app", "alpha", "v1.2.3", "app")
        with open(path, "rb") as file:
            twice = file.read()

        assert once == twice

    def test_does_not_duplicate_env_entries(self, root):
        write_values(root, "alpha")

        for _ in range(3):
            chart.update_values(root, "demo-app", "alpha", "v1.2.3", "app")

        names = [e["name"] for e in read_values(root, "alpha")["app"]["env"]]
        assert names.count("ENV_HASH") == 1
        assert names.count("VERSION") == 1

    def test_seeds_missing_env_entries(self, root):
        write_values(root, "alpha", "app:\n  env: []\n  image:\n    tag: v0.0.1\n")

        chart.update_values(root, "demo-app", "alpha", "v1.2.3", "app")
        docs = read_values(root, "alpha")

        assert [e["name"] for e in docs["app"]["env"]] == ["ENV_HASH", "VERSION"]

    def test_secret_is_a_string_not_binary(self, root):
        write_values(
            root,
            "alpha",
            "app:\n  secret:\n    data:\n      SECRET_VERSION: b2xk\n",
        )

        chart.update_values(root, "demo-app", "alpha", "v1.2.3", "app")

        with open(chart.values_path(root, "demo-app", "alpha")) as file:
            raw = file.read()
        assert "!!binary" not in raw

        docs = read_values(root, "alpha")
        encoded = docs["app"]["secret"]["data"]["SECRET_VERSION"]
        assert isinstance(encoded, str)
        assert base64.b64decode(encoded).decode("utf-8") == "v1.2.3"

    def test_other_containers_are_untouched(self, root):
        write_values(
            root,
            "alpha",
            "app:\n  image:\n    tag: v0.0.1\nsidecar:\n  image:\n    tag: v0.0.1\n",
        )

        chart.update_values(root, "demo-app", "alpha", "v1.2.3", "app")
        docs = read_values(root, "alpha")

        assert docs["app"]["image"]["tag"] == "v1.2.3"
        assert docs["sidecar"]["image"]["tag"] == "v0.0.1"

    def test_empty_container_updates_every_section(self, root):
        write_values(
            root,
            "alpha",
            "app:\n  image:\n    tag: v0.0.1\nsidecar:\n  image:\n    tag: v0.0.1\n",
        )

        chart.update_values(root, "demo-app", "alpha", "v1.2.3", "")
        docs = read_values(root, "alpha")

        assert docs["app"]["image"]["tag"] == "v1.2.3"
        assert docs["sidecar"]["image"]["tag"] == "v1.2.3"

    def test_missing_file_raises(self, root):
        with pytest.raises(IOError):
            chart.update_values(root, "demo-app", "nope", "v1.2.3", "app")


class TestUpdateVersions:
    def now(self):
        return datetime.datetime(2026, 1, 2, 3, 4, 5)

    def read(self, root, phase="alpha"):
        with open(chart.versions_path(root, "demo-app", phase)) as file:
            return json.load(file)

    def test_creates_the_log(self, root):
        chart.update_versions(root, "demo-app", "alpha", "v1.2.3", now=self.now())

        docs = self.read(root)
        assert docs["version"] == ""
        assert docs["items"] == [
            {"version": "v1.2.3", "updated": "2026-01-02T03:04:05"}
        ]

    def test_records_new_versions_newest_first(self, root):
        chart.update_versions(root, "demo-app", "alpha", "v1.2.3", now=self.now())
        chart.update_versions(root, "demo-app", "alpha", "v1.2.4", now=self.now())

        assert [i["version"] for i in self.read(root)["items"]] == ["v1.2.4", "v1.2.3"]

    def test_skips_duplicates(self, root):
        for _ in range(3):
            chart.update_versions(root, "demo-app", "alpha", "v1.2.3", now=self.now())

        assert len(self.read(root)["items"]) == 1

    def test_approved_records_the_current_version(self, root):
        chart.update_versions(
            root, "demo-app", "alpha", "v1.2.3", action="approved", now=self.now()
        )

        docs = self.read(root)
        assert docs["version"] == "v1.2.3"
        assert docs["approved"] == "2026-01-02T03:04:05"

    def test_keeps_only_the_most_recent_entries(self, root):
        for i in range(chart.MAX_VERSIONS + 5):
            chart.update_versions(
                root, "demo-app", "alpha", "v1.0.{}".format(i), now=self.now()
            )

        items = self.read(root)["items"]
        assert len(items) == chart.MAX_VERSIONS
        assert items[0]["version"] == "v1.0.{}".format(chart.MAX_VERSIONS + 4)
        assert items[-1]["version"] == "v1.0.5"

    def test_trims_a_file_that_is_already_too_long(self, root):
        filepath = chart.versions_path(root, "demo-app", "alpha")
        with open(filepath, "w") as file:
            json.dump(
                {
                    "version": "",
                    "items": [
                        {"version": "v0.0.{}".format(i), "updated": "2020-01-01T00:00:00"}
                        for i in range(30)
                    ],
                },
                file,
            )

        chart.update_versions(root, "demo-app", "alpha", "v1.2.3", now=self.now())

        items = self.read(root)["items"]
        assert len(items) == chart.MAX_VERSIONS
        assert items[0]["version"] == "v1.2.3"
        assert items[-1]["version"] == "v0.0.18"

    def test_short_history_is_untouched(self, root):
        for i in range(3):
            chart.update_versions(
                root, "demo-app", "alpha", "v1.0.{}".format(i), now=self.now()
            )

        assert len(self.read(root)["items"]) == 3

    def test_approved_version_survives_trimming(self, root):
        chart.update_versions(
            root, "demo-app", "alpha", "v0.0.1", action="approved", now=self.now()
        )
        for i in range(chart.MAX_VERSIONS + 5):
            chart.update_versions(
                root, "demo-app", "alpha", "v1.0.{}".format(i), now=self.now()
            )

        docs = self.read(root)
        assert docs["version"] == "v0.0.1"
        assert "v0.0.1" not in [i["version"] for i in docs["items"]]

    def test_plain_deploy_leaves_approved_version_alone(self, root):
        chart.update_versions(
            root, "demo-app", "alpha", "v1.2.3", action="approved", now=self.now()
        )
        chart.update_versions(root, "demo-app", "alpha", "v1.2.4", now=self.now())

        assert self.read(root)["version"] == "v1.2.3"
