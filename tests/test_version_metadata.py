from __future__ import annotations

import tomllib
from pathlib import Path

import veritas


def test_package_metadata_version_matches_runtime_version() -> None:
    root = Path(__file__).resolve().parents[1]
    metadata = tomllib.loads((root / "pyproject.toml").read_text(encoding="utf-8"))

    assert metadata["project"]["version"] == veritas.__version__
    assert veritas.__version__ == "0.14.0"
