from __future__ import annotations

import argparse
import json
from hashlib import sha256
from pathlib import Path

from veritas.extraction_review_packet import build_blinded_seed_review_packets

DEFAULT_SEED = Path("benchmark/extraction/seed_cases_v0.11.json")


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Build blinded independent-review packets from an unsplit extraction seed manifest."
    )
    parser.add_argument("--seed", type=Path, default=DEFAULT_SEED)
    parser.add_argument("--output-dir", type=Path, required=True)
    parser.add_argument("--reviewer-slots", nargs="+", default=("reviewer-a", "reviewer-b"))
    args = parser.parse_args()

    raw = args.seed.read_bytes()
    seed = json.loads(raw)
    seed_sha = sha256(raw).hexdigest()
    packets = build_blinded_seed_review_packets(
        seed,
        seed_manifest_sha256=seed_sha,
        reviewer_slots=tuple(args.reviewer_slots),
    )

    args.output_dir.mkdir(parents=True, exist_ok=True)
    manifest: list[dict[str, str]] = []
    for packet in packets:
        path = args.output_dir / f"{packet.reviewer_slot}.review-packet.json"
        path.write_text(
            json.dumps(packet.to_payload(), ensure_ascii=False, indent=2, sort_keys=True) + "\n",
            encoding="utf-8",
        )
        manifest.append(
            {
                "reviewer_slot": packet.reviewer_slot,
                "packet_sha256": packet.sha256(),
                "path": str(path),
            }
        )

    print(
        json.dumps(
            {
                "seed_manifest_sha256": seed_sha,
                "packet_count": len(packets),
                "targets_per_packet": len(packets[0].targets),
                "packets": manifest,
                "legacy_values_included": False,
                "other_reviewer_submissions_included": False,
            },
            ensure_ascii=False,
            sort_keys=True,
        )
    )


if __name__ == "__main__":
    main()
