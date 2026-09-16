from __future__ import annotations

import argparse

import uvicorn

from ..version import package_version
from .web import create_app


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Run the local Veritas Research Audit Workbench.")
    parser.add_argument("--version", action="version", version=f"%(prog)s {package_version()}")
    parser.add_argument("--host", default="127.0.0.1")
    parser.add_argument("--port", type=int, default=8765)
    parser.add_argument("--data-dir")
    return parser


def main() -> None:
    args = build_parser().parse_args()
    uvicorn.run(
        create_app(args.data_dir),
        host=args.host,
        port=args.port,
        log_level="info",
    )


if __name__ == "__main__":
    main()
