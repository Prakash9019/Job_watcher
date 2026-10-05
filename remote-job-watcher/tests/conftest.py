import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from config import Settings  # noqa: E402


@pytest.fixture
def settings(tmp_path):
    return Settings(state_file=tmp_path / "state" / "seen_jobs.json", log_file=tmp_path / "logs" / "new.log",
                    notify=False, backoff_base=0, enabled={"a": True, "b": True})
