#!/usr/bin/env python3
"""Create missing EKS connection parameters without rotating existing credentials."""

import argparse
import json
from pathlib import Path
import secrets
import subprocess
import tempfile
from urllib.parse import quote

import yaml


def aws(region, *arguments, payload=None):
    command = ["aws", "--region", region, "--output", "json", *arguments]
    if payload is None:
        result = subprocess.run(command, capture_output=True, text=True)
    else:
        # Keep secret values out of process arguments with a seekable request file.
        # NamedTemporaryFile is private (0600) and removes the request on exit.
        with tempfile.NamedTemporaryFile(mode="w", suffix=".json") as request:
            json.dump(payload, request)
            request.flush()
            result = subprocess.run(command + ["--cli-input-json", f"file://{request.name}"],
                                    capture_output=True, text=True)
    if result.returncode:
        # AWS errors can include request values; never print secret-bearing output.
        raise RuntimeError(f"AWS {' '.join(arguments[:2])} failed (exit {result.returncode})")
    return json.loads(result.stdout)


def parameter_values(prefix, existing):
    postgres = existing.get(f"{prefix}/agent-studio/postgres-password") or secrets.token_hex(32)
    neo4j = existing.get(f"{prefix}/agent-memory/neo4j-password") or secrets.token_hex(32)
    connection = f"postgresql://agent_studio:{quote(postgres, safe='')}@postgres.agent-studio.svc.cluster.local:5432"
    return {
        f"{prefix}/agent-studio/postgres-password": postgres,
        f"{prefix}/agent-studio/database-url": f"{connection}/agent_studio",
        f"{prefix}/agent-memory/database-url": f"{connection}/agent_memory",
        f"{prefix}/agent-memory/neo4j-password": neo4j,
        f"{prefix}/agent-memory/neo4j-auth": f"neo4j/{neo4j}",
        f"{prefix}/agent-memory/metrics-bearer-token":
            existing.get(f"{prefix}/agent-memory/metrics-bearer-token") or secrets.token_hex(32),
    }


def bootstrap(cluster, region, apply=False):
    prefix = f"/k8s/{cluster}"
    names = list(parameter_values(prefix, {}))
    response = aws(region, "ssm", "get-parameters", "--names", *names, "--with-decryption")
    existing = {entry["Name"]: entry["Value"] for entry in response["Parameters"]}
    desired = parameter_values(prefix, existing)
    # A partially provisioned installation must not silently receive different passwords.
    mismatches = [name for name, value in existing.items() if value != desired[name]]
    if mismatches:
        raise RuntimeError("Inconsistent connection parameters; review without rotating: " + ", ".join(mismatches))
    missing = [name for name in names if name not in existing]
    for name in missing:
        if apply:
            aws(region, "ssm", "put-parameter", payload={
                "Name": name, "Value": desired[name], "Type": "SecureString", "Overwrite": False
            })
        print(f"{'Created' if apply else 'Missing'}: {name}")
    print(f"{len(existing)} existing, {len(missing)} {'created' if apply else 'missing'} parameters")
    return 0 if apply or not missing else 1


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--cluster", default="eks-demo")
    parser.add_argument("--apply", action="store_true", help="Create missing SecureStrings; never overwrite")
    args = parser.parse_args()
    env_path = Path(__file__).resolve().parent / "env" / f"{args.cluster}.yaml"
    env = yaml.safe_load(env_path.read_text())
    if env.get("env") != "eks" or env.get("cluster") != args.cluster:
        parser.error("Select an EKS cluster declared in env/<cluster>.yaml")
    account = aws(env["aws_region"], "sts", "get-caller-identity")["Account"]
    if account != str(env["aws_account_id"]):
        parser.error("AWS account does not match the selected cluster")
    return bootstrap(args.cluster, env["aws_region"], args.apply)


if __name__ == "__main__":
    raise SystemExit(main())
