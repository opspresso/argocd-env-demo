#!/usr/bin/env python3
# -*- coding: utf-8 -*-

import argparse
import os
import yaml

from jinja2 import Environment, FileSystemLoader


REPONAME = "sample-app"


def parse_args():
    p = argparse.ArgumentParser(description="Helm chart gen")
    p.add_argument("-r", "--reponame", default=REPONAME, help="reponame")
    return p.parse_args()


def gen_repos(args):
    os.makedirs("build", exist_ok=True)
    os.makedirs("charts", exist_ok=True)

    template_name = "values-template.yaml.j2"
    template_path = "charts/{}/{}".format(args.reponame, template_name)

    if os.path.exists(template_path):
        print("# gen_values", template_path)

        e = Environment(loader=FileSystemLoader("charts/{}/".format(args.reponame)))
        t = e.get_template(template_name)

        gen_values(t, args.reponame)


def gen_values(t, reponame):
    for env_file in os.listdir("env"):
        if env_file.endswith(".yaml"):
            env_path = "env/{}".format(env_file)

            with open(env_path, "r") as vars:
                v = yaml.safe_load(vars)

                # The ApplicationSet reads "{{env}}/values-{{cluster}}.yaml",
                # so the directory has to follow the env field.
                if "env" not in v:
                    raise KeyError("{} has no 'env' field".format(env_path))

                d = t.render(v)

                if d != None:
                    save_root = "charts/{}/{}".format(reponame, v["env"])
                    save_path = "{}/values-{}".format(save_root, env_file)

                    os.makedirs(save_root, exist_ok=True)

                    with open(save_path, "w") as file:
                        print("# save", save_path)
                        file.write(d)


def main():
    args = parse_args()

    gen_repos(args)


if __name__ == "__main__":
    main()
