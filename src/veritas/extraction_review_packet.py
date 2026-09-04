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
        for label, value in (
            ("target_id", self.target_id),
            ("case_id", self.case_id),
            ("paper_id", self.paper_id),
            ("article_family_id", self.article_family_id),
            ("pdf_url", self.pdf_url),
            ("object_type", self.object_type),
            ("key", self.key),
            ("table_label", self.table_label),
            ("row_label", self.row_label),
        ):
            _require_nonempty_string(value, label=label)
        if self.doi is not None and (not isinstance(self.doi, str) or not self.doi.strip()):
            raise ValueError("doi must be a non-empty string or None")
        if not self.pdf_url.startswith("https://"):
            raise ValueError("review packet pdf_url must use HTTPS")
        if isinstance(self.expected_page, bool) or not isinstance(self.expected_page, int):
            raise TypeError("expected_page must be an integer")
        if self.expected_page <= 0:
            raise ValueError("expected_page must be positive")
        if type(self.critical_for_hard_audit) is not bool:
            raise TypeError("critical_for_hard_audit must be boolean")


@dataclass(frozen=True)
class ExtractionReviewerPacket:
    reviewer_slot: str
    seed_manifest_sha256: str
    targets: tuple[ExtractionReviewPacketTarget, ...]
    blinded_to_legacy_values: bool = True
    blinded_to_other_reviews: bool = True
    schema_version: int = 1

    def __post_init__(self) -> None:
        _require_nonempty_string(self.reviewer_slot, label="reviewer_slot")
        if not isinstance(self.seed_manifest_sha256, str) or not _SHA256_RE.fullmatch(
            self.seed_manifest_sha256
        ):
            raise ValueError("seed_manifest_sha256 must be a lowercase SHA-256 digest")
        if not isinstance(self.targets, tuple) or not self.targets:
            raise ValueError("reviewer packet requires a non-empty tuple of targets")
        if any(not isinstance(target, ExtractionReviewPacketTarget) for target in self.targets):
            raise TypeError("reviewer packet targets must be ExtractionReviewPacketTarget values")
        target_ids = [target.target_id for target in self.targets]
        if len(set(target_ids)) != len(target_ids):
            raise ValueError("review packet target_id values must be unique")
        if type(self.blinded_to_legacy_values) is not bool or not self.blinded_to_legacy_values:
            raise ValueError("locked review packets must remain blinded to legacy values")
        if type(self.blinded_to_other_reviews) is not bool or not self.blinded_to_other_reviews:
            raise ValueError("locked review packets must remain blinded to other reviews")
        if isinstance(self.schema_version, bool) or not isinstance(self.schema_version, int):
            raise ValueError("reviewer packet schema_version must be integer 1")
        if self.schema_version != 1:
            raise ValueError("reviewer packet schema_version must be integer 1")

    def sha256(self) -> str:
        raw = json.dumps(
            self.to_payload(),
            ensure_ascii=False,
            sort_keys=True,
            separators=(",", ":"),
        ).encode("utf-8")
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
    if not isinstance(seed_manifest, dict):
        raise TypeError("seed manifest must be an object")
    if seed_manifest.get("status") != "seed_corpus_not_locked_gold":
        raise ValueError("review packets may only be built from an explicit seed corpus")
    if seed_manifest.get("production_hard_finding_authorized") is not False:
        raise ValueError("seed corpus must not carry production hard-finding authority")
    if not isinstance(reviewer_slots, tuple) or any(
        not isinstance(slot, str) or not slot.strip() for slot in reviewer_slots
    ):
        raise TypeError("reviewer_slots must be a tuple of non-empty strings")
    if len(set(reviewer_slots)) < 2:
        raise ValueError("at least two distinct reviewer slots are required")
    if not isinstance(seed_manifest_sha256, str) or not _SHA256_RE.fullmatch(seed_manifest_sha256):
        raise ValueError("seed_manifest_sha256 must be a lowercase SHA-256 digest")

    packet_targets: list[ExtractionReviewPacketTarget] = []
    cases = seed_manifest.get("cases")
    if not isinstance(cases, list) or not cases:
        raise ValueError("seed manifest requires non-empty cases")
    for case in cases:
        if not isinstance(case, dict):
            raise TypeError("seed cases must be objects")
        if case.get("split") is not None:
            raise ValueError("seed cases must remain unsplit before independent review")
        case_id = _required_mapping_string(case, "case_id")
        paper_id = _required_mapping_string(case, "paper_id")
        article_family_id = _required_mapping_string(case, "article_family_id")
        pdf_url = _required_mapping_string(case, "pdf_url")
        object_type = _required_mapping_string(case, "object_type")
        doi = case.get("doi")
        if doi is not None and (not isinstance(doi, str) or not doi.strip()):
            raise ValueError("seed case doi must be a non-empty string or null")

        locator = case.get("locator")
        fields = case.get("expected_fields")
        if not isinstance(locator, dict) or not isinstance(fields, dict) or not fields:
            raise ValueError("seed cases require locator and expected_fields metadata")
        if set(locator) != {"expected_page", "table_label", "row_label"}:
            raise ValueError("seed case locator must contain exactly expected_page/table_label/row_label")
        expected_page = locator["expected_page"]
        if isinstance(expected_page, bool) or not isinstance(expected_page, int):
            raise TypeError("seed case expected_page must be an integer")
        if expected_page <= 0:
            raise ValueError("seed case expected_page must be positive")
        table_label = _required_mapping_string(locator, "table_label", prefix="seed case locator")
        row_label = _required_mapping_string(locator, "row_label", prefix="seed case locator")
        if any(not isinstance(key, str) or not key.strip() for key in fields):
            raise ValueError("seed expected_fields keys must be non-empty strings")

        for key in sorted(fields):
            packet_targets.append(
                ExtractionReviewPacketTarget(
                    target_id=f"{case_id}:{key}",
                    case_id=case_id,
                    paper_id=paper_id,
                    article_family_id=article_family_id,
                    doi=doi,
                    pdf_url=pdf_url,
                    object_type=object_type,
                    key=key,
                    expected_page=expected_page,
                    table_label=table_label,
                    row_label=row_label,
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


def _require_nonempty_string(value: object, *, label: str) -> None:
    if not isinstance(value, str) or not value.strip():
        raise ValueError(f"{label} must be a non-empty string")


def _required_mapping_string(
    mapping: dict[str, object],
    key: str,
    *,
    prefix: str = "seed case",
) -> str:
    value = mapping.get(key)
    if not isinstance(value, str) or not value.strip():
        raise ValueError(f"{prefix} {key} must be a non-empty string")
    return value