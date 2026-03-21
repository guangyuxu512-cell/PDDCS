from __future__ import annotations

import sys
from pathlib import Path

import pytest


TEST_ENCRYPTION_KEY = "Q4_WVdFO2N3mE6sI8vvQjz0jUKGwEuKXXSb9VjA36T0="
REPO_ROOT = Path(__file__).resolve().parents[1]

if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))


@pytest.fixture(autouse=True)
def encryption_env(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("ENCRYPTION_KEY", TEST_ENCRYPTION_KEY)
