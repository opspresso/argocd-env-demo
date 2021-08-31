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


def replace_values(args):
    filepath = "{}/values-{}.yaml".format(args.reponame, args.phase)
    filehash = ""

    if os.path.exists(filepath):
        print("replace", filepath)

        doc = None

        with open(filepath, "r") as file:
            doc = yaml.load(file, Loader=yaml.FullLoader)

            # image tag
            doc["app"]["image"]["tag"] = args.version

            # configmap
            if "configmap" in doc["app"]:
                doc["app"]["configmap"]["data"]["VERSION"] = args.version

            # secret
            if "secret" in doc["app"]:
                doc["app"]["secret"]["data"]["SECRET_VERSION"] = base64.b64encode(args.version.encode('utf-8'))

        if doc != None:
            with open(filepath, "w") as file:
                yaml.dump(doc, file)

            with open(filepath, "rb") as file:
                filehash = hashlib.md5(file.read()).hexdigest()

    return filehash


def replace_hash(args, hash):
    filepath = "{}/values-{}.yaml".format(args.reponame, args.phase)
    filehash = ""

    if os.path.exists(filepath):
        print("replace", filepath)

        doc = None

        with open(filepath, "r") as file:
            doc = yaml.load(file, Loader=yaml.FullLoader)

            if "env" in doc["app"]:
                for i, env in enumerate(doc["app"]["env"]):
                    if env["name"] == "ENV_HASH":
                        env["value"] = hash

        if doc != None:
            with open(filepath, "w") as file:
                yaml.dump(doc, file)

            with open(filepath, "rb") as file:
                filehash = hashlib.md5(file.read()).hexdigest()

    return filehash


def main():
    args = parse_args()

    hash = replace_values(args)

    replace_hash(args, hash)


if __name__ == "__main__":
    main()
