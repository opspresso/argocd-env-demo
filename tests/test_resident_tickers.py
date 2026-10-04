"""Tickers retain periodic HTTP work without creating a Pod for each occurrence."""
from pathlib import Path
import subprocess

import pytest
import yaml

ROOT = Path(__file__).resolve().parents[1]


def render(chart, platform):
    path = ROOT / 'charts' / chart
    definition = yaml.safe_load((path / 'Chart.yaml').read_text())
    if definition.get('dependencies') and not list((path / 'charts').glob('*.tgz')):
        pytest.skip(f"Run helm dependency update {path}")
    phase = 'prod' if platform == 'eks' else 'alpha'
    result = subprocess.run(['helm', 'template', chart, str(path), '--namespace', chart,
                             '-f', str(path / 'values.yaml'), '-f', str(path / f'values-{phase}.yaml'),
                             '-f', str(path / platform / f'values-{platform}-demo.yaml')],
                            capture_output=True, text=True, check=True)
    return [doc for doc in yaml.safe_load_all(result.stdout) if doc]


@pytest.mark.parametrize('platform', ['eks', 'k3s'])
@pytest.mark.parametrize('chart,name', [('agent-studio', 'agent-studio-ticker'), ('sample-node', 'sample-node-thumbs')])
def test_ticker_is_one_resident_unprivileged_deployment(platform, chart, name):
    docs = render(chart, platform)
    assert not any(doc['kind'] == 'CronJob' for doc in docs)
    deployment = next(doc for doc in docs if doc['kind'] == 'Deployment' and doc['metadata']['name'] == name)
    assert deployment['spec']['strategy']['type'] == 'Recreate'
    assert deployment['spec']['replicas'] == 1
    pod = deployment['spec']['template']
    assert pod['metadata']['annotations']['sidecar.istio.io/inject'] == 'false'
    assert pod['spec']['automountServiceAccountToken'] is False
    assert len(pod['spec']['containers']) == 1
    container = pod['spec']['containers'][0]
    assert not container.get('envFrom')
    security = container['securityContext']
    assert security['runAsNonRoot'] is True
    assert isinstance(security['runAsUser'], int) and security['runAsUser'] > 0
    assert security['runAsGroup'] > 0
    assert not container.get('livenessProbe')
    if chart == 'agent-studio':
        assert container['env'] == [{'name': 'SCHEDULE_SCAN_TOKEN', 'valueFrom': {
            'secretKeyRef': {'name': 'agent-studio-external', 'key': 'SCHEDULE_SCAN_TOKEN'}}}]
    else:
        assert container['env'][0]['name'] == 'COUNTER_URL'
        assert container['env'][0]['value'].startswith('https://sample-node.')


@pytest.mark.parametrize('platform', ['eks', 'k3s'])
def test_studio_separates_boot_liveness_and_database_readiness(platform):
    docs = render('agent-studio', platform)
    deployment = next(doc for doc in docs if doc['kind'] == 'Deployment' and doc['metadata']['name'] == 'agent-studio')
    container = deployment['spec']['template']['spec']['containers'][0]
    assert container['startupProbe']['httpGet']['path'] == '/api/health'
    assert container['startupProbe']['periodSeconds'] * container['startupProbe']['failureThreshold'] >= 120
    assert container['livenessProbe']['httpGet']['path'] == '/api/health'
    assert container['readinessProbe']['httpGet']['path'] == '/api/ready'
    assert container['readinessProbe']['timeoutSeconds'] > 2
