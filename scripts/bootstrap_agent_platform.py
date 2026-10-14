#!/usr/bin/env python3
"""Create missing platform secrets without rotating credentials or changing databases."""

import argparse
import hashlib
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
        # Private request files keep credentials out of argv and error output.
        with tempfile.NamedTemporaryFile(mode="w", suffix=".json") as request:
            json.dump(payload, request)
            request.flush()
            result = subprocess.run(command + ["--cli-input-json", f"file://{request.name}"],
                                    capture_output=True, text=True)
    if result.returncode:
        raise RuntimeError(f"AWS {' '.join(arguments[:2])} failed (exit {result.returncode})")
    return json.loads(result.stdout)


def parameter_values(prefix, existing):
    values = {}

    def secret(path):
        key = f"{prefix}/{path}"
        values[key] = existing.get(key) or secrets.token_hex(32)
        return values[key]

    postgres = secret("agent-studio/postgres-password")
    values[f"{prefix}/agent-platform/database-url"] = (
        f"postgresql://agent_studio:{quote(postgres, safe='')}"
        "@postgres.agent-studio.svc.cluster.local:5432/agent_platform")
    for service in ("agent-memory", "agent-librio", "agent-forge"):
        secret(f"{service}/metrics-bearer-token")
        secret(f"{service}/delegation-secret")
    for path in ("agent-librio/better-auth-secret", "agent-librio/policy-secret",
                 "agent-forge/policy-secret", "agent-forge/checkpoint-secret",
                 "agent-forge/credential-secret", "agent-forge/model-secret"):
        secret(path)
    # Forge owns issuer-qualified principals; its organization is a configured namespace.
    # Memory/Librio organization IDs must instead come from their initialized installations.
    org = values[f"{prefix}/agent-forge/organization-id"] = existing.get(
        f"{prefix}/agent-forge/organization-id", f"agent-platform-{prefix.rsplit('/', 1)[-1]}")
    issuer = "https://studio.agrt.dev"
    scopes = ["workspace:read", "workspace:write", "run:write", "git:write", "git:connect", "git:publish-protected"]
    values[f"{prefix}/agent-forge/delegators"] = json.dumps([{
        "issuer": issuer, "organizationId": org, "scopes": scopes,
        "secret": values[f"{prefix}/agent-forge/delegation-secret"], "policyRequired": True
    }], separators=(",", ":"))
    for service in ("forge", "librio"):
        policy = {"issuer": issuer,
                  "url": f"http://agent-studio.agent-studio.svc.cluster.local:3000/api/services/{service}/model-policy",
                  "secret": values[f"{prefix}/agent-{service}/policy-secret"]}
        if service == "librio":
            policy["mode"] = "required"
        values[f"{prefix}/agent-{service}/issuer-policies"] = json.dumps([policy], separators=(",", ":"))
    values[f"{prefix}/agent-forge/credentials"] = json.dumps([{
        "issuer": "agent-platform-monitoring", "subject": "metrics", "organizationId": org,
        "scopes": ["workspace:read"], "tokenSha256": hashlib.sha256(
            values[f"{prefix}/agent-forge/metrics-bearer-token"].encode()).hexdigest()
    }], separators=(",", ":"))
    return values


def read_parameters(region, names):
    entries = []
    # SSM GetParameters accepts at most ten names per request.
    for offset in range(0, len(names), 10):
        response = aws(region, "ssm", "get-parameters", "--names", *names[offset:offset + 10], "--with-decryption")
        entries.extend(response["Parameters"])
    return {entry["Name"]: entry["Value"] for entry in entries}


def bootstrap(cluster, region, apply=False):
    prefix = f"/k8s/{cluster}"
    names = list(parameter_values(prefix, {}))
    existing = read_parameters(region, names)
    desired = parameter_values(prefix, existing)
    # JSON whitespace is irrelevant, but identity, scope and signing keys must agree.
    def same(name, left, right):
        if name.endswith(("/delegators", "/issuer-policies", "/credentials")):
            try:
                return json.loads(left) == json.loads(right)
            except ValueError:
                return False
        return left == right
    mismatches = [name for name, value in existing.items() if not same(name, value, desired[name])]
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
    # These are operator-validated service configuration, never random secret material.
    for path in ("agent-memory/organization-id", "agent-librio/organization-id",
                 "agent-forge/model-channels", "agent-librio/audio-models"):
        print(f"Prepare and validate separately: {prefix}/{path}")
    return 0 if apply or not missing else 1


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--cluster", default="k3s-demo")
    parser.add_argument("--apply", action="store_true", help="Create missing SecureStrings; never overwrite")
    args = parser.parse_args()
    env_path = Path(__file__).resolve().parents[1] / "env" / f"{args.cluster}.yaml"
    env = yaml.safe_load(env_path.read_text())
    if env.get("env") not in {"eks", "k3s"} or env.get("cluster") != args.cluster:
        parser.error("Select a cluster declared in env/<cluster>.yaml")
    account = aws(env["aws_region"], "sts", "get-caller-identity")["Account"]
    if account != str(env["aws_account_id"]):
        parser.error("AWS account does not match the selected cluster")
    return bootstrap(args.cluster, env["aws_region"], args.apply)


if __name__ == "__main__":
    raise SystemExit(main())
