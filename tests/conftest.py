from pathlib import Path

import pytest

REPO = Path(__file__).resolve().parents[1]
TEST_MASTER_KEY = b"test-only-master-key-0123456789abcdef"


@pytest.fixture
def repo() -> Path:
    return REPO
