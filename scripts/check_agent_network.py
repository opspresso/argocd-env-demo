#!/usr/bin/env python3
"""Read-only cluster check: Studio may reach Docker; Memory must not.

Uses existing ready application Pods and Docker's /_ping endpoint. Creates no
Pods, reads no credentials, and fails if either an allowed or denied path differs.
"""
import argparse
import json
import subprocess

PROBE = """
const host = 'agent-studio-workspace-docker.agent-studio.svc.cluster.local';
const { lookup } = await import('node:dns/promises');
await lookup(host);
let response;
try {
  response = await fetch('http://' + host + ':2375/_ping', { signal: AbortSignal.timeout(4000) });
} catch (error) {
  if (error.name !== 'TimeoutError' && error.name !== 'TypeError') throw error;
  console.log(JSON.stringify({ reachable: false, error: error.name, code: error.cause?.code }));
}
if (response) {
  console.log(JSON.stringify({ reachable: true, status: response.status,
    docker: response.ok && (await response.text()).trim() === 'OK' && !!response.headers.get('api-version') }));
}
"""


def check(context=None):
    kubectl = ["kubectl", *(["--context", context] if context else []), "--request-timeout=15s"]

    def command(*args):
        result = subprocess.run(kubectl + list(args), check=True, capture_output=True, text=True, timeout=25)
        return json.loads(result.stdout)

    def ready_pods(namespace):
        pods = command("-n", namespace, "get", "pods", "-l", f"app.kubernetes.io/name={namespace}", "-o", "json")["items"]
        ready = [pod["metadata"]["name"] for pod in pods if not pod["metadata"].get("deletionTimestamp")
                 and any(condition["type"] == "Ready" and condition["status"] == "True"
                         for condition in pod.get("status", {}).get("conditions", []))]
        if not ready:
            raise RuntimeError(f"No ready {namespace} application Pods; network isolation was not tested")
        return ready

    def probe(namespace, pod):
        return command("-n", namespace, "exec", pod, "-c", "app", "--", "node", "--input-type=module", "-e", PROBE)

    studio = ready_pods("agent-studio")
    memory = ready_pods("agent-memory")
    for pod in studio:
        result = probe("agent-studio", pod)
        if not result.get("docker"):
            raise RuntimeError(f"Allowed Studio path failed for {pod}: {result}")
    for pod in memory:
        result = probe("agent-memory", pod)
        if result["reachable"]:
            reason = "Docker API is reachable" if result.get("docker") else "Unexpected HTTP response; inspect the network/mesh path"
            raise RuntimeError(f"{reason} from unrelated Memory Pod {pod}: {result}")
    # An unavailable endpoint must not be mistaken for successful isolation.
    if not probe("agent-studio", studio[0]).get("docker"):
        raise RuntimeError("Docker API became unavailable during the isolation check")
    print(f"PASS: {len(studio)} Studio Pods allowed, {len(memory)} Memory Pods blocked")


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--context", help="kubectl context; defaults to the current context")
    check(parser.parse_args().context)
