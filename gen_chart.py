#!/usr/bin/env python3
# -*- coding: utf-8 -*-

import argparse
import json
import os
import yaml
import subprocess


REPONAME = "cluster-role"


def parse_args():
    p = argparse.ArgumentParser(description="Helm chart gen")
    p.add_argument("-r", "--reponame", default=REPONAME, help="reponame")
    return p.parse_args()


def get_app_version(chart, version):
    txt = os.popen(
        "helm search repo '{}' --version {} -o json".format(chart, version)
    ).read()

    doc = json.loads(txt)

    if len(doc) > 0:
        app_version = doc[0]["app_version"]
    else:
        app_version = version

    print("# app_version", app_version)

    return app_version


def gen_chart(args):
    os.makedirs("build", exist_ok=True)
    os.makedirs("charts", exist_ok=True)

    appset_path = "addons/{}.yaml".format(args.reponame)

    chart_path = "charts/{}/Chart.yaml".format(args.reponame)
    values_path = "charts/{}/values.yaml".format(args.reponame)

    if os.path.exists(appset_path):
        print("# gen_chart", appset_path)

        os.makedirs("charts/{}".format(args.reponame), exist_ok=True)

        chart = None
        values = None

        docs = None

        with open(appset_path, "r") as file:
            docs = yaml.safe_load(file)

            source = docs["spec"]["template"]["spec"]["source"]

            if "chart" in source:
                name = source["chart"]
                version = source["targetRevision"]

                hash = (
                    subprocess.check_output(["git", "rev-parse", "--short", "HEAD"])
                    .decode("ascii")
                    .strip()
                )

                print("# name", name)
                print("# version", version)

                # chart
                chart = {}
                chart["apiVersion"] = "v2"
                chart["description"] = "A Helm chart for Kubernetes"
                chart["name"] = args.reponame
                chart["type"] = "application"
                chart["dependencies"] = []
                chart["version"] = "{}-{}".format(version, hash)

                # app_version
                chart["appVersion"] = get_app_version(args.reponame, version)

                # dependencies
                dependency = {}
                dependency["repository"] = source["repoURL"]
                dependency["name"] = name
                dependency["version"] = version

                if name != args.reponame:
                    dependency["alias"] = args.reponame
                #     dependency["condition"] = "{}.enabled".format(args.reponame)
                # else:
                #     dependency["condition"] = "{}.enabled".format(name)

                chart["dependencies"].append(dependency)

                # create chart
                with open(chart_path, "w") as file:
                    yaml.safe_dump(chart, file)

                # values
                if "values" in source["helm"]:
                    doc = source["helm"]["values"]
                    values = {}
                    values[args.reponame] = yaml.safe_load(doc)
                    # values["enabled"] = True

                    # create values
                    with open(values_path, "w") as file:
                        yaml.safe_dump(values, file)


def main():
    args = parse_args()

    gen_chart(args)


if __name__ == "__main__":
    main()
