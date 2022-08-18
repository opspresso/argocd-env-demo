#!/usr/bin/env python
# -*- coding: utf-8 -*-

import argparse
import base64
import hashlib
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
    return p.parse_args()


def replace_values(args):
    filepath = "{}/values-{}.yaml".format(args.reponame, args.phase)
    filehash = ""

    if os.path.exists(filepath):
        print("replace_values", filepath)

        docs = None

        with open(filepath, "r") as file:
            docs = yaml.load(file, Loader=yaml.FullLoader)

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
                    docs[doc]["secret"]["data"]["SECRET_VERSION"] = base64.b64encode(
                        args.version.encode("utf-8")
                    )

        if docs != None:
            with open(filepath, "w") as file:
                yaml.dump(docs, file)

            with open(filepath, "rb") as file:
                filehash = hashlib.md5(file.read()).hexdigest()

    return filehash


def replace_hash(args, hash):
    filepath = "{}/values-{}.yaml".format(args.reponame, args.phase)
    filehash = ""

    if os.path.exists(filepath):
        print("replace_hash", filepath)

        docs = None

        with open(filepath, "r") as file:
            docs = yaml.load(file, Loader=yaml.FullLoader)

            for i, doc in enumerate(docs):
                if args.container != "" and doc != args.container:
                    continue

                if "env" in docs[doc]:
                    for i, env in enumerate(docs[doc]["env"]):
                        if env["name"] == "ENV_HASH":
                            env["value"] = hash

        if docs != None:
            with open(filepath, "w") as file:
                yaml.dump(docs, file)

            with open(filepath, "rb") as file:
                filehash = hashlib.md5(file.read()).hexdigest()

    return filehash


def main():
    args = parse_args()

    hash = replace_values(args)

    replace_hash(args, hash)


if __name__ == "__main__":
    main()
