#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Render every ApplicationSet the way Argo CD would, and fail on any error.

Reads apps/*.yaml, expands the git files generator against the env files it
names, and runs `helm template` with the exact valueFiles Argo CD passes -
including values-<phase>.yaml, whose phase comes from the env file. A broken
template or a missing values file then fails CI instead of surfacing as a
failed sync on the cluster.

Also enforces that every <env>/values-<cluster>.yaml has a values-template.yaml.j2
to come from - a hand-written one is indistinguishable from a render and drifts
without anyone noticing.

    ./validate.py                 # every ApplicationSet in apps/
    ./validate.py -r sample-node  # one chart

A chart with no ApplicationSet in apps/ is not deployed and is not checked.
"""

import argparse
import os
import re
import subprocess
import sys

import yaml


APPSET_DIR = "apps"
CHARTS_DIR = "charts"

TEMPLATE = "values-template.yaml.j2"
VALUES_RE = re.compile(r"^values-.+\.yaml$")

# ApplicationSet substitutes {{key}} from the env file the generator matched.
PLACEHOLDER = re.compile(r"\{\{(\w+)\}\}")


def parse_args():
    p = argparse.ArgumentParser(description="Helm render check")
    p.add_argument("-r", "--reponame", help="only this chart")
    p.add_argument(
        "-d", "--dir", action="append", dest="dirs",
        help="ApplicationSet directory (repeatable, default: {})".format(APPSET_DIR),
    )
    return p.parse_args()


def expand(text, env):
    def replace(match):
        key = match.group(1)
        if key not in env:
            raise KeyError("{{%s}} is not in the env file" % key)
        return str(env[key])

    return PLACEHOLDER.sub(replace, text)


def load_targets(dirs):
    """One entry per ApplicationSet: chart, env files and valueFiles."""
    targets = []

    for directory in dirs:
        for name in sorted(os.listdir(directory)):
            if not name.endswith(".yaml"):
                continue

            path = os.path.join(directory, name)
            with open(path, "r") as file:
                doc = yaml.safe_load(file)

            if not doc or doc.get("kind") != "ApplicationSet":
                continue

            template = doc["spec"]["template"]
            source = template["spec"]["source"]

            targets.append({
                "appset": path,
                "chart": source["path"],
                "value_files": source.get("helm", {}).get("valueFiles", []),
                "env_files": [
                    entry["path"]
                    for generator in doc["spec"]["generators"]
                    for entry in generator["git"]["files"]
                ],
                "name": template["metadata"]["name"],
                "namespace": template["spec"]["destination"]["namespace"],
            })

    return targets


def check_templates(only=None):
    """Every <env>/values-<cluster>.yaml has to be a render, never hand-written.

    A hand-maintained one looks exactly like a generated one, so it survives
    every build while quietly drifting from the template beside it.
    """
    failures = []

    for name in sorted(os.listdir(CHARTS_DIR)):
        chart = os.path.join(CHARTS_DIR, name)

        if only and name != only:
            continue

        if not os.path.isdir(chart) or os.path.exists(os.path.join(chart, TEMPLATE)):
            continue

        for entry in sorted(os.listdir(chart)):
            directory = os.path.join(chart, entry)

            if not os.path.isdir(directory):
                continue

            found = sorted(f for f in os.listdir(directory) if VALUES_RE.match(f))

            if found:
                failures.append((
                    directory,
                    "{} has no {}, so {} cannot be regenerated".format(
                        chart, TEMPLATE, ", ".join(found)
                    ),
                ))

    return failures


def update_dependencies(chart):
    """Fetch the upstream charts pinned in Chart.yaml."""
    print("# deps", chart, flush=True)

    result = subprocess.run(
        ["helm", "dependency", "update", chart], capture_output=True, text=True
    )

    if result.returncode != 0:
        return result.stderr.strip() or result.stdout.strip()

    return None


def render(target, env_file):
    """helm template one ApplicationSet against one env file."""
    with open(env_file, "r") as file:
        env = yaml.safe_load(file)

    args = ["helm", "template", expand(target["name"], env), target["chart"]]
    args += ["--namespace", expand(target["namespace"], env)]

    for value_file in target["value_files"]:
        path = os.path.join(target["chart"], expand(value_file, env))

        # Argo CD fails the sync when a listed valueFile is missing, so a
        # chart that was never rendered has to fail here too.
        if not os.path.exists(path):
            return "missing values file: {}".format(path)

        args += ["-f", path]

    result = subprocess.run(args, capture_output=True, text=True)

    if result.returncode != 0:
        return result.stderr.strip() or result.stdout.strip()

    return None


def main():
    args = parse_args()

    root = os.path.dirname(os.path.abspath(__file__))
    os.chdir(root)

    targets = load_targets(args.dirs or [APPSET_DIR])

    if args.reponame:
        wanted = "charts/{}".format(args.reponame)
        targets = [t for t in targets if t["chart"] == wanted]

        if not targets:
            print("no ApplicationSet uses {}".format(wanted))
            return 1

    failures = check_templates(args.reponame)
    rendered = 0
    prepared = set()

    for target in targets:
        if target["chart"] not in prepared:
            error = update_dependencies(target["chart"])
            prepared.add(target["chart"])

            if error:
                failures.append((target["chart"], error))
                continue

        for env_file in target["env_files"]:
            print("# render {} {}".format(target["appset"], env_file), flush=True)

            try:
                error = render(target, env_file)
            except (KeyError, IOError) as exception:
                error = str(exception)

            rendered += 1

            if error:
                failures.append(
                    ("{} {}".format(target["appset"], env_file), error)
                )

    print("\n{} renders, {} failures".format(rendered, len(failures)))

    for where, why in failures:
        print("\nFAIL {}\n{}".format(where, why))

    return 1 if failures else 0


if __name__ == "__main__":
    sys.exit(main())
