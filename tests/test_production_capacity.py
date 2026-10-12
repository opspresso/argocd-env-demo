"""Capacity contracts include simultaneous rollout generations and probe processes."""
from test_agent_platform import resource
import pytest


@pytest.mark.parametrize("platform", ["eks", "k3s"])
def test_database_budget_covers_application_growth_and_rollout_overlap(platform):
    def maximum_web_replicas(chart):
        if platform == "eks":
            return resource(chart, platform, "HorizontalPodAutoscaler", chart)["spec"]["maxReplicas"]
        return resource(chart, platform, "Deployment", chart)["spec"]["replicas"]

    studio = maximum_web_replicas("agent-studio")
    memory = maximum_web_replicas("agent-memory")
    worker = resource("agent-studio", platform, "Deployment", "agent-studio-workspace-worker")["spec"]["replicas"]
    audio = resource("agent-studio", platform, "Deployment", "agent-studio-audio-worker")["spec"]["replicas"]
    config = resource("agent-studio", platform, "ConfigMap", "agent-studio")["data"]
    pool = int(config["DATABASE_POOL_SIZE"])
    memory_config = resource("agent-memory", platform, "ConfigMap", "agent-memory")["data"]
    memory_workers = resource("agent-memory", platform, "Deployment", "agent-memory-worker")["spec"]["replicas"]
    memory_pool = int(memory_config["DATABASE_POOL_SIZE"]) + int(memory_config["DATABASE_QUEUE_POOL_SIZE"]) + 1
    # Studio: ordinary pool + isolated readiness + four content-lock connections.
    # Memory: application/pg-boss/readiness pools and one maintenance advisory lock per worker.
    application_connections = 2 * ((studio + worker + audio) * (pool + 1 + 4)
                                  + (memory + memory_workers) * memory_pool + memory_workers)
    readiness_connections = 2 * worker * pool
    postgres = resource("postgresql", platform, "StatefulSet", "postgres")["spec"]["template"]["spec"]["containers"][0]
    capacity = int(next(arg.split("=", 1)[1] for arg in postgres["args"] if arg.startswith("max_connections=")))
    assert capacity >= application_connections + readiness_connections + 20


def test_web_scales_on_both_execution_paths_and_app_cpu():
    metrics = resource("agent-studio", "eks", "HorizontalPodAutoscaler", "agent-studio")["spec"]["metrics"]
    assert metrics[0]["pods"]["metric"]["name"] == "agent_studio_active_execution_requests"
    assert metrics[1]["containerResource"]["container"] == "app"
    assert metrics[1]["containerResource"]["name"] == "cpu"
