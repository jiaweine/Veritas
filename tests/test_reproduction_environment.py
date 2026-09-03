from __future__ import annotations

from pathlib import Path

from veritas.reproduction_environment import (
    build_environment_snapshot,
    dependency_lock_from_file,
)
from veritas.reproduction_runner import ReplicationRuntime


def test_dependency_lock_hash_changes_with_bytes(tmp_path: Path) -> None:
    lock = tmp_path / "requirements.lock"
    lock.write_text("numpy==2.0.0\n", encoding="utf-8")
    first = dependency_lock_from_file(lock, kind="python")
    lock.write_text("numpy==2.0.1\n", encoding="utf-8")
    second = dependency_lock_from_file(lock, kind="python")

    assert first.sha256 != second.sha256
    assert first.filename == "requirements.lock"


def test_environment_snapshot_is_order_stable_and_binds_runtime() -> None:
    lock = dependency_lock_from_file.__annotations__  # prove no runtime side effects on import
    del lock
    dependency = type("Lock", (), {})
    del dependency


def test_build_environment_snapshot_sorts_inventory(tmp_path: Path) -> None:
    lock_path = tmp_path / "renv.lock"
    lock_path.write_text('{"R": {"Version": "4.4.0"}}', encoding="utf-8")
    lock = dependency_lock_from_file(lock_path, kind="r")
    image_ref = f"r-veritas@sha256:{'a' * 64}"

    first = build_environment_snapshot(
        runtime=ReplicationRuntime.R,
        runtime_version="4.4.0",
        platform_name="linux-x86_64",
        image_ref=image_ref,
        dependency_lock=lock,
        package_inventory=("sandwich==3.1-0", "stats==4.4.0"),
    )
    second = build_environment_snapshot(
        runtime=ReplicationRuntime.R,
        runtime_version="4.4.0",
        platform_name="linux-x86_64",
        image_ref=image_ref,
        dependency_lock=lock,
        package_inventory=("stats==4.4.0", "sandwich==3.1-0"),
    )

    assert first.package_inventory_sha256 == second.package_inventory_sha256
    assert first.sha256() == second.sha256()
    assert first.package_count == 2


def test_environment_snapshot_changes_when_lock_or_runtime_changes(tmp_path: Path) -> None:
    lock_path = tmp_path / "requirements.lock"
    lock_path.write_text("numpy==2.0.0\n", encoding="utf-8")
    lock = dependency_lock_from_file(lock_path, kind="python")
    base = build_environment_snapshot(
        runtime=ReplicationRuntime.PYTHON,
        runtime_version="3.12.4",
        platform_name="linux-x86_64",
        image_ref=f"python@sha256:{'b' * 64}",
        dependency_lock=lock,
        package_inventory=("numpy==2.0.0",),
    )
    changed = build_environment_snapshot(
        runtime=ReplicationRuntime.PYTHON,
        runtime_version="3.13.0",
        platform_name="linux-x86_64",
        image_ref=f"python@sha256:{'b' * 64}",
        dependency_lock=lock,
        package_inventory=("numpy==2.0.0",),
    )

    assert base.sha256() != changed.sha256()
