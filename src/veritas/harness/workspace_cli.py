from __future__ import annotations

import argparse
import json
import os
from pathlib import Path

from ..version import package_version
from .store import HarnessStore
from .workspace_retention import WORKSPACE_RETENTION_SCHEMA_VERSION, WorkspaceRetention


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="Inspect or prune completed Veritas replication workspaces."
    )
    parser.add_argument("--version", action="version", version=f"%(prog)s {package_version()}")
    parser.add_argument(
        "--data-dir",
        default=os.environ.get("VERITAS_HARNESS_DATA", "~/.veritas/harness"),
        help="Harness data directory (defaults to VERITAS_HARNESS_DATA or ~/.veritas/harness)",
    )
    subparsers = parser.add_subparsers(dest="command", required=True)
    subparsers.add_parser("list", help="List replication workspaces without modifying them.")

    prune = subparsers.add_parser(
        "prune",
        help="Select completed workspaces older than a retention cutoff; dry-run by default.",
    )
    prune.add_argument("--older-than-hours", required=True, type=int)
    prune.add_argument(
        "--apply",
        action="store_true",
        help="Actually delete eligible workspace copies. Without this flag the command is a dry-run.",
    )
    return parser


def run(args: argparse.Namespace) -> dict[str, object]:
    root = Path(args.data_dir).expanduser()
    retention = WorkspaceRetention(HarnessStore(root))
    if args.command == "list":
        workspaces = retention.list_workspaces()
        return {
            "schema_version": WORKSPACE_RETENTION_SCHEMA_VERSION,
            "automatic_cleanup": False,
            "workspace_count": len(workspaces),
            "workspaces": workspaces,
        }
    return retention.prune(
        older_than_hours=args.older_than_hours,
        apply=bool(args.apply),
    )


def main() -> None:
    parser = build_parser()
    args = parser.parse_args()
    try:
        payload = run(args)
    except (OSError, TypeError, ValueError) as exc:
        parser.error(str(exc))
    print(json.dumps(payload, ensure_ascii=False, sort_keys=True, indent=2))


if __name__ == "__main__":
    main()
