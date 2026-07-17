import shutil
from pathlib import Path

import pytest

FIXTURE_ROOT = Path(__file__).parent / "fixtures" / "messy_project"


@pytest.fixture
def messy_root() -> Path:
    return FIXTURE_ROOT


@pytest.fixture
def copy_of_messy_root(tmp_path) -> Path:
    dest = tmp_path / "messy_project"
    shutil.copytree(FIXTURE_ROOT, dest)
    return dest
