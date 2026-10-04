"""Capacity contracts include simultaneous rollout generations and probe processes."""
from test_agent_platform import resource


def test_database_budget_covers_application_growth_and_rollout_overlap():
    studio = resource("agent-studio", "eks", "HorizontalPodAutoscaler", "agent-studio")["spec"]["maxReplicas"]
    memory = resource("agent-memory", "eks", "HorizontalPodAutoscaler", "agent-memory")["spec"]["maxReplicas"]
    worker = resource("agent-studio", "eks", "Deployment", "agent-studio-workspace-worker")["spec"]["replicas"]
    audio = resource("agent-studio", "eks", "Deployment", "agent-studio-audio-worker")["spec"]["replicas"]
    config = resource("agent-studio", "eks", "ConfigMap", "agent-studio")["data"]
    pool = int(config["DATABASE_POOL_SIZE"])
    # Studio: ordinary pool + isolated readiness + four content-lock connections.
    # Memory owns a 10-connection pool. Exec readiness also opens a temporary process.
    application_connections = 2 * ((studio + worker + audio) * (pool + 1 + 4) + memory * 10)
    readiness_connections = 2 * worker * pool
    postgres = resource("postgresql", "eks", "StatefulSet", "postgres")["spec"]["template"]["spec"]["containers"][0]
    capacity = int(next(arg.split("=", 1)[1] for arg in postgres["args"] if arg.startswith("max_connections=")))
    assert capacity >= application_connections + readiness_connections + 20


def test_web_scales_on_both_execution_paths_and_app_cpu():
    metrics = resource("agent-studio", "eks", "HorizontalPodAutoscaler", "agent-studio")["spec"]["metrics"]
    assert metrics[0]["pods"]["metric"]["name"] == "agent_studio_active_execution_requests"
    assert metrics[1]["containerResource"]["container"] == "app"
    assert metrics[1]["containerResource"]["name"] == "cpu"
