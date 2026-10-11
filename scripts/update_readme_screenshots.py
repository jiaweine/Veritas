"""Install real Chromium acceptance screenshots in the README asset directory.

Provide the unpacked `veritas-ui-screenshots` artifact from a successful
`ui-visual-smoke` run. Images are copied byte-for-byte, not synthesized.
"""

from __future__ import annotations

import argparse
import shutil
import struct
from pathlib import Path


REPO_ROOT = Path(__file__).resolve().parents[1]
IMAGE_MAP = {
    "overview.png": "workspace-dark-overview.png",
    "audit-workbench.png": "audit-evidence-lens.png",
    "command-search.png": "command-search-authoritative-event.png",
    "runs.png": "workspace-dark-runs.png",
    "reproduction.png": "replication-diff.png",
}
PNG_MAGIC = b"\x89PNG\r\n\x1a\n"


def main() -> None:
    parser = argparse.ArgumentParser(description="Refresh README screenshots from real UI test results.")
    parser.add_argument("artifact_dir", type=Path, help="Unpacked Chromium screenshot artifact")
    parser.add_argument(
        "--dest",
        type=Path,
        default=REPO_ROOT / "docs/assets/product",
        help="Destination directory",
    )
    args = parser.parse_args()
    sources = []
    for target, source in IMAGE_MAP.items():
        filename = args.artifact_dir / source
        payload = filename.read_bytes()
        if not payload.startswith(PNG_MAGIC) or len(payload) < 32:
            raise ValueError(f"Invalid PNG screenshot: {filename}")
        width, height = struct.unpack(">II", payload[16:24])
        if width < 1200 or height < 700:
            raise ValueError(f"Unexpected screenshot geometry: {source}: {width}x{height}")
        sources.append((target, filename, len(payload), width, height))

    args.dest.mkdir(parents=True, exist_ok=True)
    for target, source, size, width, height in sources:
        dest = args.dest / target
        shutil.copyfile(source, dest)
        print(f"{target} ← {source.name} · {width}×{height} · {size:,} B")


if __name__ == "__main__":
    main()
