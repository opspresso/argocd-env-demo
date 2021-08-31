#!/usr/bin/env python
# -*- coding: utf-8 -*-

import argparse
import base64
import hashlib
import os
import yaml


REPONAME = "sample-docs"
PHASE = "demo-dev"

IMAGENAME = "nalbam/docs"
VERSION = "v0.0.0"


def parse_args():
    p = argparse.ArgumentParser(description="GitOps")
    p.add_argument("-r", "--reponame", default=REPONAME, help="reponame")
    p.add_argument("-p", "--phase", default=PHASE, help="phase")
    p.add_argument("-n", "--imagename", default=IMAGENAME, help="imagename")
    p.add_argument("-v", "--version", default=VERSION, help="version")
    return p.parse_args()


def replace_deployment(args, cm_hasg, sec_hash):
    filepath = "{}/{}/deployment.yaml".format(args.reponame, args.phase)
    filehash = ""

    if os.path.exists(filepath):
        print("replace", filepath)

        doc = None

        with open(filepath, "r") as file:
            doc = yaml.load(file, Loader=yaml.FullLoader)

            # pod
            doc["spec"]["template"]["metadata"]["labels"]["version"] = args.version

            # datadog
            doc["metadata"]["labels"]["tags.datadoghq.com/version"] = args.version
            doc["spec"]["template"]["metadata"]["labels"][
                "tags.datadoghq.com/version"
            ] = args.version

            containers = doc["spec"]["template"]["spec"]["containers"]
            containers[0]["image"] = "{}:{}".format(args.imagename, args.version)

            if "env" in containers[0]:
                for i, env in enumerate(containers[0]["env"]):
                    if env["name"] == "CONFIGMAP_HASH":
                        env["value"] = cm_hasg
                    if env["name"] == "SECRET_HASH":
                        env["value"] = sec_hash

        if doc != None:
            with open(filepath, "w") as file:
                yaml.dump(doc, file)

    return filehash


def replace_service_preview(args):
    filepath = "{}/{}/service-preview.yaml".format(args.reponame, args.phase)
    filehash = ""

    if os.path.exists(filepath):
        print("replace", filepath)

        doc = None

        with open(filepath, "r") as file:
            doc = yaml.load(file, Loader=yaml.FullLoader)

            # replace
            doc["spec"]["selector"]["version"] = args.version

        if doc != None:
            with open(filepath, "w") as file:
                yaml.dump(doc, file)

            with open(filepath, "rb") as file:
                filehash = hashlib.md5(file.read()).hexdigest()

    return filehash


def replace_configmap(args):
    filepath = "{}/{}/configmap.yaml".format(args.reponame, args.phase)
    filehash = ""

    if os.path.exists(filepath):
        print("replace", filepath)

        doc = None

        with open(filepath, "r") as file:
            doc = yaml.load(file, Loader=yaml.FullLoader)

            # replace
            doc["data"]["VERSION"] = args.version

        if doc != None:
            with open(filepath, "w") as file:
                yaml.dump(doc, file)

            with open(filepath, "rb") as file:
                filehash = hashlib.md5(file.read()).hexdigest()

    return filehash


def replace_secret(args):
    filepath = "{}/{}/secret.yaml".format(args.reponame, args.phase)
    filehash = ""

    if os.path.exists(filepath):
        print("replace", filepath)

        doc = None

        with open(filepath, "r") as file:
            doc = yaml.load(file, Loader=yaml.FullLoader)

            # replace
            doc["data"]["SECRET_VERSION"] = base64.b64encode(args.version.encode('utf-8'))

        if doc != None:
            with open(filepath, "w") as file:
                yaml.dump(doc, file)

            with open(filepath, "rb") as file:
                filehash = hashlib.md5(file.read()).hexdigest()

    return filehash


def main():
    args = parse_args()

    chash = replace_configmap(args)
    shash = replace_secret(args)

    replace_deployment(args, chash, shash)

    replace_service_preview(args)


if __name__ == "__main__":
    main()
