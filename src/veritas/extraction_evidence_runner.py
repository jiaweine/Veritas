from __future__ import annotations

import json
import math
import re
from dataclasses import dataclass
from hashlib import sha256
from pathlib import Path
from typing import Any

from .extraction import ExtractionCandidate, ExtractionDecision, ExtractionResolution
from .extraction_benchmark import ExtractionPrediction
from .extraction_evidence_workflow import ExtractionSplitTargetManifest
from .extraction_execution_evidence import extraction_prediction_artifact_bytes
from .extraction_input_artifacts import (
    ExtractionInputArtifactManifest,
    load_extraction_input_artifact_manifest,
    verify_extraction_input_artifact_manifest,
)
from .extraction_review_packet import ExtractionReviewPacketTarget, ExtractionReviewerPacket
from .pdf_native import parse_pdf_dual
from .pdf_regression import RegressionLocator, extract_regression_table
from .protocol import BenchmarkSplit

_SHA256_RE = re.compile(r"^[0-9a-f]{64}$")
_PACKET_KEYS = frozenset(
    {
        "schema_version",
        "reviewer_slot",
        "seed_manifest_sha256",
        "blinded_to_legacy_values",
        "blinded_to_other_reviews",
        "instructions",
        "targets",
        "submission_template",
    }
)
_PACKET_TARGET_KEYS = frozenset(
    {
        "target_id",
        "case_id",
        "paper_id",
        "article_family_id",
        "doi",
        "pdf_url",
        "object_type",
        "key",
        "expected_page",
        "table_label",
        "row_label",
        "critical_for_hard_audit",
    }
)
_SPLIT_TARGET_KEYS = frozenset(
    {
        "schema_version",
        "split",
        "gold_manifest_sha256",
        "split_lock_sha256",
        "article_family_ids",
        "target_ids",
    }
)
_FIELD_ALIASES = {
    "beta": "beta",
    "se": "se",
    "z_stat": "t_stat",
    "p_value": "p_value",
}


@dataclass(frozen=True)
class ExtractionEvidenceThresholdRun:
    split: BenchmarkSplit
    threshold_id: str
    threshold: float
    target_manifest_sha256: str
    review_packet_sha256: str
    prediction_artifact_sha256: str
    targets: int
    accepted: int
    abstained: int
    conflicts: int
    domain_shifts: int


def load_blinded_extraction_reviewer_packet(path: str | Path) -> ExtractionReviewerPacket:
    """Strict-load a blinded packet without opening the value-bearing seed manifest."""
    payload = _load_strict_json_file(path, label="blinded extraction reviewer packet")
    _require_exact_keys(payload, _PACKET_KEYS, label="blinded extraction reviewer packet")
    targets_payload = payload["targets"]
    if not isinstance(targets_payload, list) or not targets_payload:
        raise ValueError("blinded extraction reviewer packet requires non-empty targets")
    targets: list[ExtractionReviewPacketTarget] = []
    for index, item in enumerate(targets_payload):
        _require_exact_keys(item, _PACKET_TARGET_KEYS, label=f"blinded packet target {index}")
        targets.append(
            ExtractionReviewPacketTarget(
                target_id=item["target_id"],
                case_id=item["case_id"],
                paper_id=item["paper_id"],
                article_family_id=item["article_family_id"],
                doi=item["doi"],
                pdf_url=item["pdf_url"],
                object_type=item["object_type"],
                key=item["key"],
                expected_page=item["expected_page"],
                table_label=item["table_label"],
                row_label=item["row_label"],
                critical_for_hard_audit=item["critical_for_hard_audit"],
            )
        )
    packet = ExtractionReviewerPacket(
        reviewer_slot=payload["reviewer_slot"],
        seed_manifest_sha256=payload["seed_manifest_sha256"],
        targets=tuple(targets),
        blinded_to_legacy_values=payload["blinded_to_legacy_values"],
        blinded_to_other_reviews=payload["blinded_to_other_reviews"],
        schema_version=payload["schema_version"],
    )
    if payload != packet.to_payload():
        raise ValueError("blinded extraction reviewer packet differs from canonical packet payload")
    return packet


def load_extraction_split_target_manifest(path: str | Path) -> ExtractionSplitTargetManifest:
    payload = _load_strict_json_file(path, label="extraction split target manifest")
    _require_exact_keys(payload, _SPLIT_TARGET_KEYS, label="extraction split target manifest")
    try:
        split = BenchmarkSplit(payload["split"])
    except (TypeError, ValueError) as exc:
        raise ValueError("extraction split target manifest has an unsupported split") from exc
    article_family_ids = payload["article_family_ids"]
    target_ids = payload["target_ids"]
    if not isinstance(article_family_ids, list) or not isinstance(target_ids, list):
        raise TypeError("extraction split target manifest memberships must be arrays")
    manifest = ExtractionSplitTargetManifest(
        split=split,
        gold_manifest_sha256=payload["gold_manifest_sha256"],
        split_lock_sha256=payload["split_lock_sha256"],
        article_family_ids=tuple(article_family_ids),
        target_ids=tuple(target_ids),
        schema_version=payload["schema_version"],
    )
    if payload != manifest.to_payload():
        raise ValueError("extraction split target manifest differs from canonical payload")
    return manifest


def resolve_extraction_candidates_at_threshold(
    candidates: tuple[ExtractionCandidate, ...] | list[ExtractionCandidate],
    *,
    threshold: float,
    min_independent_families: int = 2,
) -> ExtractionResolution:
    candidates = tuple(candidates)
    if any(not isinstance(candidate, ExtractionCandidate) for candidate in candidates):
        raise TypeError("candidates must contain ExtractionCandidate values")
    if isinstance(threshold, bool) or not isinstance(threshold, (int, float)):
        raise TypeError("threshold must be a finite non-negative number")
    threshold = float(threshold)
    if not math.isfinite(threshold) or threshold < 0.0:
        raise ValueError("threshold must be a finite non-negative number")
    if isinstance(min_independent_families, bool) or not isinstance(min_independent_families, int):
        raise TypeError("min_independent_families must be an integer")
    if min_independent_families < 1:
        raise ValueError("min_independent_families must be positive")

    accepted = tuple(candidate for candidate in candidates if candidate.nonconformity_score <= threshold)
    if not accepted:
        return _abstention(
            threshold,
            reason="No extraction candidate passed the frozen nonconformity threshold.",
        )

    by_value: dict[str, list[ExtractionCandidate]] = {}
    for candidate in accepted:
        by_value.setdefault(candidate.normalized_value, []).append(candidate)
    if len(by_value) > 1:
        return ExtractionResolution(
            decision=ExtractionDecision.CONFLICT,
            normalized_value=None,
            accepted_candidates=accepted,
            calibration_threshold=threshold,
            reason="Multiple candidates below the frozen threshold disagree; extraction remains unresolved.",
        )

    value, supporters = next(iter(by_value.items()))
    families = {candidate.parser_family for candidate in supporters}
    if len(families) < min_independent_families:
        return ExtractionResolution(
            decision=ExtractionDecision.ABSTAIN,
            normalized_value=None,
            accepted_candidates=tuple(supporters),
            calibration_threshold=threshold,
            reason="Frozen-threshold value lacks support from enough independent parser families.",
        )
    return ExtractionResolution(
        decision=ExtractionDecision.ACCEPT,
        normalized_value=value,
        accepted_candidates=tuple(supporters),
        calibration_threshold=threshold,
        reason="Candidates from independent parser families agree below the frozen threshold.",
    )


def run_extraction_evidence_threshold(
    *,
    input_artifact_manifest_path: str | Path,
    input_artifact_root: str | Path,
    review_packet_path: str | Path,
    expected_review_packet_sha256: str,
    target_manifest_path: str | Path,
    paper_artifacts: dict[str, str],
    threshold_id: str,
    threshold: float,
    output_path: str | Path,
) -> ExtractionEvidenceThresholdRun:
    if not isinstance(threshold_id, str) or not threshold_id.strip():
        raise ValueError("threshold_id must be a non-empty string")
    _require_sha256(expected_review_packet_sha256, label="expected review packet")

    input_manifest = load_extraction_input_artifact_manifest(input_artifact_manifest_path)
    verify_extraction_input_artifact_manifest(input_manifest, input_artifact_root)
    packet = load_blinded_extraction_reviewer_packet(review_packet_path)
    if packet.sha256() != expected_review_packet_sha256:
        raise ValueError("blinded reviewer packet differs from the precommitted packet SHA-256")
    target_manifest = load_extraction_split_target_manifest(target_manifest_path)
    targets = _validate_target_universe(packet, target_manifest)
    artifact_by_paper = _validate_paper_artifact_mapping(packet, input_manifest, paper_artifacts)

    manifest_by_id = {artifact.artifact_id: artifact for artifact in input_manifest.artifacts}
    root = _validated_input_root(input_artifact_root)
    snapshot_cache: dict[str, tuple[object, ...]] = {}
    bundle_cache: dict[str, object] = {}
    predictions: list[ExtractionPrediction] = []

    for target in targets:
        artifact_id = artifact_by_paper[target.paper_id]
        if target.object_type != "RegressionResult":
            resolution = _abstention(
                threshold,
                reason=f"Unsupported extraction object type: {target.object_type}.",
            )
        else:
            snapshots = snapshot_cache.get(target.paper_id)
            if snapshots is None:
                artifact = manifest_by_id[artifact_id]
                pdf_bytes = _read_verified_input(root, artifact.relative_path)
                snapshots = tuple(parse_pdf_dual(pdf_bytes, artifact_id=artifact_id))
                snapshot_cache[target.paper_id] = snapshots

            bundle = bundle_cache.get(target.case_id)
            if bundle is None:
                bundle = extract_regression_table(
                    snapshots,
                    variable_label=target.row_label,
                    locator=RegressionLocator(
                        table_label=target.table_label,
                        expected_page=target.expected_page,
                    ),
                )
                bundle_cache[target.case_id] = bundle

            ambiguities = tuple(getattr(bundle, "ambiguities"))
            if ambiguities:
                resolution = _abstention(
                    threshold,
                    reason="Publication display identity is ambiguous; extraction failed closed.",
                )
            else:
                extractor_key = _FIELD_ALIASES.get(target.key)
                if extractor_key is None:
                    resolution = _abstention(
                        threshold,
                        reason=f"No frozen extractor mapping exists for target key: {target.key}.",
                    )
                else:
                    field_candidates = getattr(bundle, "field_candidates")
                    resolution = resolve_extraction_candidates_at_threshold(
                        tuple(field_candidates.get(extractor_key, ())),
                        threshold=threshold,
                    )
        predictions.append(ExtractionPrediction(target_id=target.target_id, resolution=resolution))

    ordered_predictions = tuple(sorted(predictions, key=lambda item: item.target_id))
    if tuple(item.target_id for item in ordered_predictions) != target_manifest.target_ids:
        raise RuntimeError("prediction target IDs differ from the frozen split target manifest")
    raw = extraction_prediction_artifact_bytes(ordered_predictions)
    output = Path(output_path)
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_bytes(raw)

    counts = {decision: 0 for decision in ExtractionDecision}
    for prediction in ordered_predictions:
        counts[prediction.resolution.decision] += 1
    return ExtractionEvidenceThresholdRun(
        split=target_manifest.split,
        threshold_id=threshold_id,
        threshold=float(threshold),
        target_manifest_sha256=target_manifest.sha256(),
        review_packet_sha256=packet.sha256(),
        prediction_artifact_sha256=sha256(raw).hexdigest(),
        targets=len(ordered_predictions),
        accepted=counts[ExtractionDecision.ACCEPT],
        abstained=counts[ExtractionDecision.ABSTAIN],
        conflicts=counts[ExtractionDecision.CONFLICT],
        domain_shifts=counts[ExtractionDecision.DOMAIN_SHIFT],
    )


def _validate_target_universe(
    packet: ExtractionReviewerPacket,
    target_manifest: ExtractionSplitTargetManifest,
) -> tuple[ExtractionReviewPacketTarget, ...]:
    packet_by_id = {target.target_id: target for target in packet.targets}
    unknown = tuple(sorted(set(target_manifest.target_ids) - set(packet_by_id)))
    if unknown:
        raise ValueError(f"split target manifest contains targets outside blinded packet: {unknown!r}")
    targets = tuple(packet_by_id[target_id] for target_id in target_manifest.target_ids)
    families = tuple(sorted({target.article_family_id for target in targets}))
    if families != target_manifest.article_family_ids:
        raise ValueError("split target manifest family membership differs from blinded packet targets")
    return targets


def _validate_paper_artifact_mapping(
    packet: ExtractionReviewerPacket,
    manifest: ExtractionInputArtifactManifest,
    paper_artifacts: dict[str, str],
) -> dict[str, str]:
    if not isinstance(paper_artifacts, dict) or any(
        not isinstance(key, str)
        or not key.strip()
        or not isinstance(value, str)
        or not value.strip()
        for key, value in paper_artifacts.items()
    ):
        raise TypeError("paper_artifacts must map non-empty paper IDs to non-empty artifact IDs")
    expected_papers = {target.paper_id for target in packet.targets}
    if set(paper_artifacts) != expected_papers:
        raise ValueError("paper-artifact mapping must cover exactly the blinded packet paper universe")
    if len(set(paper_artifacts.values())) != len(paper_artifacts):
        raise ValueError("paper-artifact mapping artifact IDs must be unique")
    manifest_ids = {artifact.artifact_id for artifact in manifest.artifacts}
    missing = tuple(sorted(set(paper_artifacts.values()) - manifest_ids))
    if missing:
        raise ValueError(f"paper-artifact mapping references unknown input artifacts: {missing!r}")
    return dict(paper_artifacts)


def _abstention(threshold: float, *, reason: str) -> ExtractionResolution:
    return ExtractionResolution(
        decision=ExtractionDecision.ABSTAIN,
        normalized_value=None,
        accepted_candidates=(),
        calibration_threshold=float(threshold),
        reason=reason,
    )


def _validated_input_root(root: str | Path) -> Path:
    root_path = Path(root)
    if root_path.is_symlink():
        raise ValueError("input artifact root must not be a symbolic link")
    resolved = root_path.resolve(strict=True)
    if not resolved.is_dir():
        raise ValueError("input artifact root must be a directory")
    return resolved


def _read_verified_input(root: Path, relative_path: str) -> bytes:
    current = root
    for part in relative_path.split("/"):
        if part in {"", ".", ".."}:
            raise ValueError("input artifact relative path is unsafe")
        current = current / part
        if current.is_symlink():
            raise ValueError("input artifact paths must not contain symbolic links")
    resolved = current.resolve(strict=True)
    if not resolved.is_relative_to(root) or not resolved.is_file():
        raise ValueError("input artifact path escapes the verified root or is not a regular file")
    return resolved.read_bytes()


def _load_strict_json_file(path: str | Path, *, label: str) -> dict[str, Any]:
    raw = Path(path).read_bytes()
    try:
        payload = json.loads(
            raw.decode("utf-8"),
            object_pairs_hook=_reject_duplicate_object_keys,
            parse_constant=_reject_json_constant,
        )
    except UnicodeDecodeError as exc:
        raise ValueError(f"{label} must be UTF-8 JSON") from exc
    except json.JSONDecodeError as exc:
        raise ValueError(f"{label} must contain valid JSON") from exc
    if not isinstance(payload, dict):
        raise TypeError(f"{label} root must be an object")
    return payload


def _require_exact_keys(value: object, expected: frozenset[str], *, label: str) -> None:
    if not isinstance(value, dict):
        raise TypeError(f"{label} must be an object")
    actual = frozenset(value)
    if actual != expected:
        missing = tuple(sorted(expected - actual))
        unknown = tuple(sorted(actual - expected))
        raise ValueError(f"{label} keys differ from schema; missing={missing!r}, unknown={unknown!r}")


def _require_sha256(value: object, *, label: str) -> None:
    if not isinstance(value, str) or not _SHA256_RE.fullmatch(value):
        raise ValueError(f"{label} SHA-256 must be lowercase hexadecimal")


def _reject_duplicate_object_keys(pairs: list[tuple[str, Any]]) -> dict[str, Any]:
    result: dict[str, Any] = {}
    for key, value in pairs:
        if key in result:
            raise ValueError(f"duplicate object key is not allowed: {key!r}")
        result[key] = value
    return result


def _reject_json_constant(value: str) -> None:
    raise ValueError(f"non-standard JSON numeric constant is not allowed: {value}")
