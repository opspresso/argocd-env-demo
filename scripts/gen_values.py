#!/usr/bin/env python3
# -*- coding: utf-8 -*-

import argparse
import os
import yaml

from jinja2 import Environment, FileSystemLoader, StrictUndefined


PLATFORM = "eks"
PLATFORMS = {"eks", "k3s", "local"}


def parse_args():
    p = argparse.ArgumentParser(description="Helm chart gen")
    p.add_argument("-r", "--reponame", required=True, help="chart name")
    p.add_argument("-p", "--platform", choices=["eks", "k3s", "local"], default=PLATFORM)
    return p.parse_args()


def gen_repos(args):
    template_name = "values-template.yaml.j2"
    template_path = "charts/{}/{}".format(args.reponame, template_name)

    if not os.path.isfile(template_path):
        raise FileNotFoundError("template not found: {}".format(template_path))
    print("# gen_values", template_path)

    e = Environment(
        loader=FileSystemLoader("charts/{}/".format(args.reponame)),
        undefined=StrictUndefined,
    )
    t = e.get_template(template_name)

    gen_values(t, args.reponame, args.platform)


def gen_values(t, reponame, platform=PLATFORM):
    rendered = []
    for env_file in sorted(os.listdir("env")):
        if env_file.endswith(".yaml"):
            env_path = "env/{}".format(env_file)

            with open(env_path, "r") as file:
                v = yaml.safe_load(file)

                # The ApplicationSet reads "{{env}}/values-{{cluster}}.yaml",
                # so the directory has to follow the env field.
                if not isinstance(v, dict) or v.get("env") not in PLATFORMS:
                    raise ValueError("{} must declare a supported env".format(env_path))
                if v.get("cluster") != os.path.splitext(env_file)[0]:
                    raise ValueError("{} cluster must match its filename".format(env_path))
                for key in ("resources", "autoscaling"):
                    if key in v and not isinstance(v[key], bool):
                        raise ValueError("{} {} must be a boolean".format(env_path, key))

                if v.get("env") != platform:
                    continue

                d = t.render(v)
                if not isinstance(yaml.safe_load(d), dict):
                    raise ValueError("{} must render a values mapping".format(env_path))

                save_root = "charts/{}/{}".format(reponame, platform)
                save_path = "{}/values-{}".format(save_root, env_file)
                rendered.append((save_path, d))

    # Validate every selected environment before replacing any generated file.
    for save_path, content in rendered:
        os.makedirs(os.path.dirname(save_path), exist_ok=True)
        with open(save_path, "w") as file:
            print("# save", save_path)
            file.write(content)


def main():
    args = parse_args()

    os.chdir(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
    gen_repos(args)


if __name__ == "__main__":
    main()
