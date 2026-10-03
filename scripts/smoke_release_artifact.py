from __future__ import annotations

import argparse
import configparser
import json
import re
import tarfile
import zipfile
from email.parser import BytesParser
from pathlib import Path

_DISTRIBUTION_NAME = "veritas-audit"
_EXPECTED_ENTRY_POINTS = {
    "veritas-harness": "veritas.harness.cli:main",
    "veritas-replication": "veritas.replication.cli:main",
    "veritas-benchmark-result": "veritas.harness.benchmark_cli:main",
    "veritas-workspace-retention": "veritas.harness.workspace_cli:main",
}
_EXPECTED_EXTRAS = {
    "attestation",
    "browser",
    "dev",
    "docling",
    "observability",
    "pdf",
    "replication",
    "web",
}
_REQUIRED_WHEEL_FILES = {
    "veritas/version.py",
    "veritas/harness/static/index.html",
    "veritas/harness/static/app.js",
    "veritas/harness/static/benchmarks.js",
    "veritas/harness/static/sw.js",
}
_REQUIRED_SDIST_SUFFIXES = {
    "pyproject.toml",
    "README.md",
    "src/veritas/version.py",
    "src/veritas/harness/static/index.html",
    "src/veritas/harness/static/app.js",
    "src/veritas/harness/static/benchmarks.js",
    "src/veritas/harness/static/sw.js",
}


def _normalized_distribution_name(value: str) -> str:
    return re.sub(r"[-_.]+", "-", value).lower()


def _single_member(names: list[str], suffix: str) -> str:
    matches = [name for name in names if name.endswith(suffix)]
    if len(matches) != 1:
        raise ValueError(f"expected exactly one {suffix!r} member, found {matches!r}")
    return matches[0]


def _validate_source_sha(value: str) -> str:
    if re.fullmatch(r"[0-9a-f]{40}", value) is None:
        raise ValueError("source SHA must be a lowercase 40-character Git commit SHA")
    return value


def inspect_wheel(path: Path, *, expected_version: str) -> dict[str, object]:
    with zipfile.ZipFile(path) as archive:
        names = archive.namelist()
        missing = sorted(_REQUIRED_WHEEL_FILES.difference(names))
        if missing:
            raise ValueError(f"wheel is missing required product files: {missing}")

        metadata_name = _single_member(names, ".dist-info/METADATA")
        metadata = BytesParser().parsebytes(archive.read(metadata_name))
        project_name = metadata.get("Name") or ""
        if _normalized_distribution_name(project_name) != _DISTRIBUTION_NAME:
            raise ValueError(f"unexpected wheel project name: {project_name!r}")
        version = metadata.get("Version") or ""
        if version != expected_version:
            raise ValueError(f"wheel version {version!r} != expected {expected_version!r}")
        if metadata.get("Requires-Python") != ">=3.11":
            raise ValueError("wheel Requires-Python must remain >=3.11")

        extras = set(metadata.get_all("Provides-Extra") or [])
        missing_extras = sorted(_EXPECTED_EXTRAS.difference(extras))
        if missing_extras:
            raise ValueError(f"wheel metadata is missing declared extras: {missing_extras}")

        entry_points_name = _single_member(names, ".dist-info/entry_points.txt")
        parser = configparser.ConfigParser(interpolation=None)
        parser.optionxform = str
        parser.read_string(archive.read(entry_points_name).decode("utf-8"))
        console_scripts = dict(parser.items("console_scripts")) if parser.has_section("console_scripts") else {}
        for command, target in _EXPECTED_ENTRY_POINTS.items():
            actual = console_scripts.get(command)
            if actual != target:
                raise ValueError(
                    f"console entry point {command!r} is {actual!r}; expected {target!r}"
                )

    return {
        "path": str(path),
        "version": expected_version,
        "required_product_files": len(_REQUIRED_WHEEL_FILES),
        "console_scripts": sorted(_EXPECTED_ENTRY_POINTS),
        "extras": sorted(extras),
    }


def inspect_sdist(path: Path) -> dict[str, object]:
    with tarfile.open(path, mode="r:gz") as archive:
        names = archive.getnames()
        roots = {name.split("/", 1)[0] for name in names if "/" in name}
        if len(roots) != 1:
            raise ValueError(f"sdist must contain one top-level project directory, found {sorted(roots)}")
        root = next(iter(roots))
        missing = sorted(
            suffix
            for suffix in _REQUIRED_SDIST_SUFFIXES
            if f"{root}/{suffix}" not in names
        )
        if missing:
            raise ValueError(f"sdist is missing required source files: {missing}")

    return {
        "path": str(path),
        "top_level_directory": root,
        "required_source_files": len(_REQUIRED_SDIST_SUFFIXES),
    }


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Fail closed if Veritas wheel/sdist release artifacts lose package contracts."
    )
    parser.add_argument("--wheel", type=Path, required=True)
    parser.add_argument("--sdist", type=Path, required=True)
    parser.add_argument("--expected-version", required=True)
    parser.add_argument("--source-sha", required=True)
    args = parser.parse_args()

    payload = {
        "schema_version": 1,
        "distribution": _DISTRIBUTION_NAME,
        "source_sha": _validate_source_sha(args.source_sha),
        "wheel": inspect_wheel(args.wheel, expected_version=args.expected_version),
        "sdist": inspect_sdist(args.sdist),
        "status": "success",
    }
    print(json.dumps(payload, sort_keys=True, indent=2))


if __name__ == "__main__":
    main()
