#!/usr/bin/env python3
"""Exercise the shipped DinD network script in an isolated local Docker daemon.

Requires Docker with privileged containers. Pulls only the pinned official DinD
image and official Alpine/Python fixtures; removes its own container and volumes on exit.
"""
import json
from pathlib import Path
import subprocess
import time
import uuid

ROOT = Path(__file__).resolve().parents[1]
IMAGE = "docker:27.5.1-dind"
FIXTURE = "alpine:3.21"
SERVER = "python:3.14-alpine"
NETWORK = "agent-studio-public"


def run(*args, check=True, timeout=120):
    return subprocess.run(args, text=True, capture_output=True, check=check, timeout=timeout)


def main():
    name = f"studio-network-check-{uuid.uuid4().hex[:12]}"
    created = False

    def execute(*args, **kwargs):
        return run("docker", "exec", name, *args, **kwargs)

    def inner(*args, **kwargs):
        return execute("docker", *args, **kwargs)

    def ready():
        for _ in range(60):
            status = json.loads(run("docker", "inspect", name).stdout)[0]["State"]
            if not status["Running"]:
                raise RuntimeError(run("docker", "logs", "--tail", "20", name).stdout)
            if execute("sh", "-ec", "test -f /workspace-network/ready && docker info >/dev/null", check=False).returncode == 0:
                return
            time.sleep(0.5)
        raise RuntimeError("DinD did not become ready")

    def sandbox_get(url, success):
        result = inner("run", "--rm", "--network", NETWORK, "--cap-drop", "ALL",
                       "--security-opt", "no-new-privileges", FIXTURE,
                       "wget", "-q", "-T", "5", "-O", "/dev/null", url, check=False)
        if (result.returncode == 0) != success:
            raise RuntimeError(f"Unexpected sandbox access to {url}: {result.stderr}")

    try:
        run("docker", "run", "--detach", "--name", name, "--privileged",
            "--env", "DOCKER_TLS_CERTDIR=", "--env", f"WORKSPACE_NETWORK={NETWORK}",
            "--mount", f"type=bind,source={ROOT / 'charts/agent-studio/files'},target=/opt/workspace-network,readonly",
            "--tmpfs", "/workspace-network", "--entrypoint", "/bin/sh", IMAGE,
            "/opt/workspace-network/workspace-network.sh", "--host=unix:///var/run/docker.sock")
        created = True
        ready()
        inner("pull", FIXTURE)
        inner("pull", SERVER)
        # Reuse the persisted Docker network after daemon restart.
        run("docker", "restart", name)
        ready()
        network = json.loads(inner("network", "inspect", NETWORK).stdout)[0]
        assert network["EnableIPv6"] is False
        assert network["Options"]["com.docker.network.bridge.enable_icc"] == "false"
        gateway = network["IPAM"]["Config"][0]["Gateway"]
        serve = "mkdir -p /tmp/www; echo private-fixture >/tmp/www/index.html; exec python -m http.server 80 --directory /tmp/www"
        inner("run", "-d", "--name", "host-fixture", "--network", "host", SERVER, "sh", "-ec", serve)
        inner("run", "-d", "--name", "peer-fixture", "--network", NETWORK, SERVER, "sh", "-ec", serve)
        peer = json.loads(inner("inspect", "peer-fixture").stdout)[0]["NetworkSettings"]["Networks"][NETWORK]["IPAddress"]
        # Prove both blocked targets serve HTTP in their own network namespaces.
        # Sandbox response packets to the private gateway are also blocked.
        for fixture in ["host-fixture", "peer-fixture"]:
            for _ in range(20):
                response = inner("exec", fixture, "python", "-c",
                                 "from urllib.request import urlopen; print(urlopen('http://127.0.0.1/index.html', timeout=1).read().decode().strip())", check=False)
                if response.returncode == 0 and response.stdout.strip() == "private-fixture":
                    break
                time.sleep(0.2)
            else:
                raise RuntimeError(f"Private fixture is not serving in {fixture}")
        sandbox_get("https://registry.npmjs.org/is-number", True)
        sandbox_get(f"http://{gateway}/index.html", False)
        sandbox_get(f"http://{peer}/index.html", False)
        sandbox_get(f"http://{gateway}:2375/_ping", False)
        sandbox_get("http://169.254.169.254/latest/meta-data/", False)
        print("PASS: restart, DNS/public HTTPS, host/peer isolation, Docker API and metadata blocking")
    finally:
        if created:
            run("docker", "rm", "--force", "--volumes", name)


if __name__ == "__main__":
    main()
