from __future__ import annotations

import json
import re
from dataclasses import asdict, dataclass
from hashlib import sha256

_SHA256_RE = re.compile(r"^[0-9a-f]{64}$")


@dataclass(frozen=True)
class ExtractionReviewPacketTarget:
    target_id: str
    case_id: str
    paper_id: str
    article_family_id: str
    doi: str | None
    pdf_url: str
    object_type: str
    key: str
    expected_page: int
    table_label: str
    row_label: str
    critical_for_hard_audit: bool = True

    def __post_init__(self) -> None:
        required = (
            self.target_id,
            self.case_id,
            self.paper_id,
            self.article_family_id,
            self.pdf_url,
            self.object_type,
            self.key,
            self.table_label,
            self.row_label,
        )
        if any(not value.strip() for value in required):
            raise ValueError("review packet target identity fields cannot be empty")
        if not self.pdf_url.startswith("https://"):
            raise ValueError("review packet pdf_url must use HTTPS")
        if self.expected_page <= 0:
            raise ValueError("expected_page must be positive")


@dataclass(frozen=True)
class ExtractionReviewerPacket:
    reviewer_slot: str
    seed_manifest_sha256: str
    targets: tuple[ExtractionReviewPacketTarget, ...]
    blinded_to_legacy_values: bool = True
    blinded_to_other_reviews: bool = True
    schema_version: int = 1

    def __post_init__(self) -> None:
        if not self.reviewer_slot.strip():
            raise ValueError("reviewer_slot is required")
        if not _SHA256_RE.fullmatch(self.seed_manifest_sha256):
            raise ValueError("seed_manifest_sha256 must be a lowercase SHA-256 digest")
        if not self.targets:
            raise ValueError("reviewer packet requires at least one target")
        target_ids = [target.target_id for target in self.targets]
        if len(set(target_ids)) != len(target_ids):
            raise ValueError("review packet target_id values must be unique")
        if not self.blinded_to_legacy_values or not self.blinded_to_other_reviews:
            raise ValueError("locked review packets must remain blinded")

    def sha256(self) -> str:
        raw = json.dumps(self.to_payload(), ensure_ascii=False, sort_keys=True, separators=(",", ":")).encode(
            "utf-8"
        )
        return sha256(raw).hexdigest()

    def to_payload(self) -> dict[str, object]:
        return {
            "schema_version": self.schema_version,
            "reviewer_slot": self.reviewer_slot,
            "seed_manifest_sha256": self.seed_manifest_sha256,
            "blinded_to_legacy_values": self.blinded_to_legacy_values,
            "blinded_to_other_reviews": self.blinded_to_other_reviews,
            "instructions": (
                "Independently verify each requested field against the cited publication location. "
                "Do not use legacy benchmark values or another reviewer's submission."
            ),
            "targets": [asdict(target) for target in self.targets],
            "submission_template": {
                "target_id": "<target_id>",
                "reviewer_id": "<reviewer_id>",
                "accepted_normalized_values": ["<independently verified value>"],
                "source": {
                    "artifact_id": "<artifact_id or verified source identifier>",
                    "page": "<physical PDF page>",
                    "section": None,
                    "table": "<publication display identity>",
                    "figure": None,
                    "row": "<row identity>",
                    "column": "<column identity>",
                    "bbox": None,
                    "text_quote": "<short source quote/cell text if useful>",
                },
                "note": "<review notes>",
            },
        }


def build_blinded_seed_review_packets(
    seed_manifest: dict[str, object],
    *,
    seed_manifest_sha256: str,
    reviewer_slots: tuple[str, ...] = ("reviewer-a", "reviewer-b"),
) -> tuple[ExtractionReviewerPacket, ...]:
    if seed_manifest.get("status") != "seed_corpus_not_locked_gold":
        raise ValueError("review packets may only be built from an explicit seed corpus")
    if seed_manifest.get("production_hard_finding_authorized") is not False:
        raise ValueError("seed corpus must not carry production hard-finding authority")
    if len(set(reviewer_slots)) < 2:
        raise ValueError("at least two distinct reviewer slots are required")

    packet_targets: list[ExtractionReviewPacketTarget] = []
    cases = seed_manifest.get("cases")
    if not isinstance(cases, list) or not cases:
        raise ValueError("seed manifest requires non-empty cases")
    for case in cases:
        if not isinstance(case, dict):
            raise ValueError("seed cases must be objects")
        if case.get("split") is not None:
            raise ValueError("seed cases must remain unsplit before independent review")
        locator = case.get("locator")
        fields = case.get("expected_fields")
        if not isinstance(locator, dict) or not isinstance(fields, dict) or not fields:
            raise ValueError("seed cases require locator and expected_fields metadata")
        for key in sorted(fields):
            packet_targets.append(
                ExtractionReviewPacketTarget(
                    target_id=f"{case['case_id']}:{key}",
                    case_id=str(case["case_id"]),
                    paper_id=str(case["paper_id"]),
                    article_family_id=str(case["article_family_id"]),
                    doi=str(case["doi"]) if case.get("doi") is not None else None,
                    pdf_url=str(case["pdf_url"]),
                    object_type=str(case["object_type"]),
                    key=str(key),
                    expected_page=int(locator["expected_page"]),
                    table_label=str(locator["table_label"]),
                    row_label=str(locator["row_label"]),
                )
            )

    targets = tuple(sorted(packet_targets, key=lambda target: target.target_id))
    return tuple(
        ExtractionReviewerPacket(
            reviewer_slot=slot,
            seed_manifest_sha256=seed_manifest_sha256,
            targets=targets,
        )
        for slot in reviewer_slots
    )
