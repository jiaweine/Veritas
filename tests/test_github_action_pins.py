from __future__ import annotations

import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


def test_active_github_actions_are_commit_pinned() -> None:
    result = subprocess.run(
        [sys.executable, "scripts/check_github_action_pins.py"],
        cwd=ROOT,
        check=False,
        capture_output=True,
        text=True,
    )
    assert result.returncode == 0, result.stdout + result.stderr
