#!/usr/bin/env python
# -*- coding: utf-8 -*-

import argparse
import base64
import datetime
import hashlib
import json
import os
import yaml


REPONAME = "sample"
PHASE = "alpha"

IMAGENAME = "org/sample"
VERSION = "v0.0.0"


def parse_args():
    p = argparse.ArgumentParser(description="GitOps")
    p.add_argument("-r", "--reponame", default=REPONAME, help="reponame")
    p.add_argument("-p", "--phase", default=PHASE, help="phase")
    p.add_argument("-n", "--imagename", default=IMAGENAME, help="imagename")
    p.add_argument("-v", "--version", default=VERSION, help="version")
    p.add_argument("-c", "--container", default="", help="container")
    p.add_argument("-a", "--action", default="", help="action")
    return p.parse_args()


def update_versions(args):
    filepath = "charts/{}/versions-{}.json".format(args.reponame, args.phase)

    docs = None

    current_time = datetime.datetime.now()

    if os.path.exists(filepath):
        print("update_versions", filepath)

        with open(filepath, "r") as file:
            docs = json.load(file)

    else:
        docs = {}
        docs["version"] = ""
        docs["items"] = []

    if args.action == "approved":
        docs["version"] = args.version
        docs["approved"] = current_time.isoformat()

    isExists = False
    for i, doc in enumerate(docs["items"]):
        if doc["version"] == args.version:
            isExists = True
            break

    if isExists == False:
        docs["items"].append({"version": args.version, "updated": current_time.isoformat()})

    if docs != None:
        with open(filepath, "w") as file:
            json.dump(docs, file, sort_keys=True, indent=2)


def replace_values(args):
    filepath = "charts/{}/values-{}.yaml".format(args.reponame, args.phase)
    filehash = ""

    docs = None

    if os.path.exists(filepath):
        print("replace_values", filepath)

        with open(filepath, "r") as file:
            docs = yaml.safe_load(file)

            for i, doc in enumerate(docs):
                if args.container != "" and doc != args.container:
                    continue

                print("replace_values", doc)

                # image tag
                if "image" in docs[doc]:
                    docs[doc]["image"]["tag"] = args.version

                # configmap
                if "configmap" in docs[doc]:
                    docs[doc]["configmap"]["data"]["VERSION"] = args.version

                # secret
                if "secret" in docs[doc]:
                    docs[doc]["secret"]["data"]["SECRET_VERSION"] = base64.b64encode(args.version.encode("utf-8"))

    if docs != None:
        with open(filepath, "w") as file:
            yaml.safe_dump(docs, file)

        with open(filepath, "rb") as file:
            filehash = hashlib.md5(file.read()).hexdigest()

    return filehash


def replace_hash(args, hash):
    filepath = "charts/{}/values-{}.yaml".format(args.reponame, args.phase)
    filehash = ""

    docs = None

    if os.path.exists(filepath):
        print("replace_hash", filepath)

        with open(filepath, "r") as file:
            docs = yaml.safe_load(file)

            for i, doc in enumerate(docs):
                if args.container != "" and doc != args.container:
                    continue

                if "env" in docs[doc]:
                    for i, env in enumerate(docs[doc]["env"]):
                        if env["name"] == "ENV_HASH":
                            env["value"] = hash

    if docs != None:
        with open(filepath, "w") as file:
            yaml.safe_dump(docs, file)

        with open(filepath, "rb") as file:
            filehash = hashlib.md5(file.read()).hexdigest()

    return filehash


def main():
    args = parse_args()

    update_versions(args)

    hash = replace_values(args)

    replace_hash(args, hash)


if __name__ == "__main__":
    main()
