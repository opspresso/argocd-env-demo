"""Import the standalone automation modules from scripts/."""

from pathlib import Path
import sys

import pytest
import yaml

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "scripts"))


@pytest.fixture
def local_env():
    """Exercise reusable local templates without declaring a deployed cluster."""
    return yaml.safe_load((Path(__file__).parent / "fixtures/local-env.yaml").read_text())
