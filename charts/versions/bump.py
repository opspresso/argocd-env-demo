#!/usr/bin/env python3
# -*- coding: utf-8 -*-

import os
import sys
import json


def get_charts(chart):
    # print("load_charts : {}".format(chart))

    txt = os.popen("helm search repo '{}' -o json".format(chart)).read()

    return json.loads(txt)


def replace():
    filepath = "versions.tf.json"

    if os.path.exists(filepath):
        # print("filepath : {}".format(filepath))

        doc = None

        with open(filepath, "r") as file:
            doc = json.load(file)

            for k in doc["variable"]:
                desc = doc["variable"][k]["description"]
                chart = desc.split("/")

                # print("# ", chart[0], chart[1])

                old_ver = doc["variable"][k]["default"]
                new_ver = ""

                charts = get_charts(chart[1])

                for o in charts:
                    # print(o["name"], o["version"])

                    name = "{}/{}".format(chart[0], chart[1])

                    if o["name"] == name:
                        new_ver = o["version"]

                # replace
                if new_ver != "":
                    if new_ver != old_ver:
                        print("{:50} {:10} -> {:10}".format(desc, old_ver, new_ver))
                    else:
                        print("{:50} {:10}".format(desc, old_ver))

                    doc["variable"][k]["default"] = new_ver

        if doc != None:
            with open(filepath, "w") as file:
                json.dump(doc, file, sort_keys=True, indent=2)


def main():
    replace()


if __name__ == "__main__":
    main()
