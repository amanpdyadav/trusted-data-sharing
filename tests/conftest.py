import os
from pathlib import Path

import pytest

REPO = Path(__file__).resolve().parents[1]
TEST_MASTER_KEY = b"test-only-master-key-0123456789abcdef"
# The challenge pack, where PETS_PACKAGE_ROOT says (as for the app), else inside the repo. Tests that need it skip
# when it is not there.
_pack = Path(os.environ.get("PETS_PACKAGE_ROOT", "TRUSTED_PETS_PROVING_GROUND_2026"))
PACKAGE = _pack if _pack.is_absolute() else REPO / _pack


@pytest.fixture
def repo() -> Path:
    return REPO
