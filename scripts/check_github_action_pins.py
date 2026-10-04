#!/usr/bin/env python3
from __future__ import annotations

import re
from pathlib import Path

ACTIVE_WORKFLOWS = (
    ".github/workflows/ci.yml",
    ".github/workflows/package-release.yml",
    ".github/workflows/ui-visual-smoke.yml",
    ".github/workflows/projects-ui-smoke.yml",
    ".github/workflows/replication-permission-ui-smoke.yml",
    ".github/workflows/mobile.yml",
    ".github/workflows/harness-stress.yml",
)

USES_RE = re.compile(r"^\s*(?:-\s*)?uses:\s*([^\s#]+)")
FULL_SHA_RE = re.compile(r"[0-9a-f]{40}")


def find_unpinned_actions(root: Path) -> list[str]:
    violations: list[str] = []
    for relative in ACTIVE_WORKFLOWS:
        path = root / relative
        for line_number, line in enumerate(path.read_text(encoding="utf-8").splitlines(), start=1):
            match = USES_RE.match(line)
            if match is None:
                continue
            target = match.group(1)
            if target.startswith(("./", "docker://")):
                continue
            if "@" not in target:
                violations.append(f"{relative}:{line_number}: missing action ref: {target}")
                continue
            _, ref = target.rsplit("@", 1)
            if FULL_SHA_RE.fullmatch(ref) is None:
                violations.append(
                    f"{relative}:{line_number}: external action must use a full commit SHA: {target}"
                )
    return violations


def main() -> int:
    root = Path(__file__).resolve().parents[1]
    violations = find_unpinned_actions(root)
    if violations:
        print("Active GitHub Actions must be pinned to immutable 40-character commit SHAs:")
        for violation in violations:
            print(f"- {violation}")
        return 1
    print(f"Verified immutable action pins in {len(ACTIVE_WORKFLOWS)} active workflows.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
