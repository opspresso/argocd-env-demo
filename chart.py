#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Chart file operations for the GitOps pipeline.

A chart lives in ``charts/<project>/`` and holds one ``values-<phase>.yaml`` per
deployable phase, plus a ``versions-<phase>.json`` deployment log.
"""

import base64
import copy
import datetime
import hashlib
import json
import os
import re

import yaml


CHARTS_DIR = "charts"

VALUES_RE = re.compile(r"^values-([a-z][a-z0-9-]*)\.yaml$")

# values-template.yaml is the jinja2 source consumed by gen_values.py, not a
# deployable phase. Without this exclusion it is dispatched like any other
# phase - which is how charts/*/versions-template.json came to exist.
RESERVED_PHASES = frozenset({"template"})

ENV_HASH = "ENV_HASH"
VERSION = "VERSION"
SECRET_VERSION = "SECRET_VERSION"

# versions-<phase>.json lists the most recent deployments newest first; the
# full history stays in the git log.
MAX_VERSIONS = 20


def chart_dir(root, project):
    return os.path.join(root, CHARTS_DIR, project)


def values_path(root, project, phase):
    return os.path.join(chart_dir(root, project), "values-{}.yaml".format(phase))


def versions_path(root, project, phase):
    return os.path.join(chart_dir(root, project), "versions-{}.json".format(phase))


def discover_phases(root, project):
    """Return the deployable phases of a chart, sorted."""
    directory = chart_dir(root, project)

    phases = []
    for name in sorted(os.listdir(directory)):
        matched = VALUES_RE.match(name)
        if matched and matched.group(1) not in RESERVED_PHASES:
            phases.append(matched.group(1))

    return phases


def update_versions(root, project, phase, version, action="", now=None):
    """Record the version in versions-<phase>.json, keeping entries unique.

    Items are newest first and trimmed to the MAX_VERSIONS most recent.
    """
    filepath = versions_path(root, project, phase)
    timestamp = (now or datetime.datetime.now()).isoformat()

    if os.path.exists(filepath):
        with open(filepath, "r") as file:
            docs = json.load(file)
    else:
        docs = {"version": "", "items": []}

    if action == "approved":
        docs["version"] = version
        docs["approved"] = timestamp

    if not any(item.get("version") == version for item in docs["items"]):
        docs["items"].insert(0, {"version": version, "updated": timestamp})

    docs["items"] = docs["items"][:MAX_VERSIONS]

    with open(filepath, "w") as file:
        json.dump(docs, file, sort_keys=True, indent=2)

    return filepath


def update_values(root, project, phase, version, container=""):
    """Write the version into values-<phase>.yaml.

    Updates ``image.tag``, the configmap and secret version entries, and the
    ``VERSION`` / ``ENV_HASH`` environment variables. Running twice with the
    same version leaves the file byte-identical.
    """
    filepath = values_path(root, project, phase)

    with open(filepath, "r") as file:
        docs = yaml.safe_load(file)

    if not docs:
        return filepath

    sections = _sections(docs, container)

    for section in sections:
        if "image" in section:
            section["image"]["tag"] = version

        if "configmap" in section:
            section["configmap"]["data"][VERSION] = version

        if "secret" in section:
            section["secret"]["data"][SECRET_VERSION] = base64.b64encode(
                version.encode("utf-8")
            ).decode("ascii")

        if "env" in section:
            # Placeholder first so a freshly seeded env list keeps ENV_HASH
            # ahead of VERSION, matching the existing charts.
            _upsert_env(section["env"], ENV_HASH, "")
            _upsert_env(section["env"], VERSION, version)

    env_hash = _digest(docs)

    for section in sections:
        if "env" in section:
            _upsert_env(section["env"], ENV_HASH, env_hash)

    with open(filepath, "w") as file:
        yaml.safe_dump(docs, file)

    return filepath


def _sections(docs, container):
    """Top-level mappings to update, narrowed to `container` when given."""
    return [
        docs[name]
        for name in docs
        if (not container or name == container) and isinstance(docs[name], dict)
    ]


def _upsert_env(env, name, value):
    for entry in env:
        if entry.get("name") == name:
            entry["value"] = value
            return
    env.append({"name": name, "value": value})


def _digest(docs):
    """Digest the values excluding ENV_HASH itself.

    Hashing a document that carries the previous ENV_HASH never reaches a fixed
    point, so every re-run would rewrite the file and restart the pods.
    """
    stripped = copy.deepcopy(docs)

    for section in stripped.values():
        if isinstance(section, dict) and isinstance(section.get("env"), list):
            section["env"] = [
                entry for entry in section["env"] if entry.get("name") != ENV_HASH
            ]

    return hashlib.md5(yaml.safe_dump(stripped).encode("utf-8")).hexdigest()
