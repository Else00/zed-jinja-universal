from __future__ import annotations

import os
import subprocess
import sys
from pathlib import Path

import pytest

RUN_INTEGRATION = os.getenv("RUN_SYNC_INTEGRATION") == "1"


@pytest.mark.integration
@pytest.mark.skipif(not RUN_INTEGRATION, reason="Set RUN_SYNC_INTEGRATION=1 to run real sync integration tests.")
def test_sync_real_list_native() -> None:
    scripts_dir = Path(__file__).resolve().parents[2]
    result = subprocess.run(
        [sys.executable, "sync_zed_languages.py", "--list", "--native"],
        cwd=scripts_dir,
        capture_output=True,
        text=True,
        timeout=300,
        check=False,
    )
    assert result.returncode == 0, result.stderr or result.stdout
    assert "Zed Native Languages" in result.stdout


@pytest.mark.integration
@pytest.mark.skipif(not RUN_INTEGRATION, reason="Set RUN_SYNC_INTEGRATION=1 to run real sync integration tests.")
def test_sync_real_diff() -> None:
    scripts_dir = Path(__file__).resolve().parents[2]
    result = subprocess.run(
        [sys.executable, "sync_zed_languages.py", "--diff"],
        cwd=scripts_dir,
        capture_output=True,
        text=True,
        timeout=300,
        check=False,
    )
    assert result.returncode == 0, result.stderr or result.stdout
    assert "COMPARISON: languages.toml vs Zed" in result.stdout
