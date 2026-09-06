from __future__ import annotations

import json
import math
from dataclasses import asdict, dataclass
from hashlib import sha256
from pathlib import Path
from typing import Any

from .benchmark import BenchmarkSplit
from .extraction import ExtractionCandidate, ExtractionDecision, ExtractionResolution
from .extraction_benchmark import (
    ExtractionPrediction,
    build_extraction_selectivity_curve,
    evaluate_extraction_benchmark,
)
from .extraction_calibration import (
    ExtractionThresholdObservation,
    ExtractionThresholdPolicy,
    lock_test_evaluation,
    select_development_threshold,
)
from .extraction_evidence_workflow import (
    ExtractionEvidencePlan,
    ExtractionSamplingFrame,
    ExtractionSeedManifest,
    ExtractionThresholdGrid,
    build_extraction_evidence_plan,
    build_extraction_split_target_manifest,
)
from .extraction_execution_evidence import (
    AttestedExtractionEvidenceReleaseReceipt,
    ExtractionExecutionPlan,
    build_attested_extraction_evidence_release_receipt,
    build_extraction_execution_evidence,
    extraction_prediction_artifact_bytes,
)
from .extraction_review import (
    ExtractionAdjudication,
    ExtractionReviewRecord,
    ExtractionReviewSubmission,
    ExtractionReviewTarget,
    build_extraction_gold_manifest,
)
from .extraction_test_seal import seal_extraction_test_set
from .ingestion import EvidenceKind
from .models import SourceLocation

_BUNDLE_KEYS = frozenset(
    {
        "schema_version",
        "review_records",
        "threshold_policy",
        "development_runs",
        "test_runs",
        "production_authorized",
    }
)
_RUN_KEYS = frozenset(
    {"threshold_id", "threshold", "execution_id", "prediction_artifact_path"}
)
_POLICY_KEYS = frozenset(
    {
        "schema_version",
        "min_selective_coverage",
        "min_accepted_full_accuracy",
        "max_critical_family_wrong_accept_upper_bound",
    }
)
_REVIEW_RECORD_KEYS = frozenset(
    {
        "schema_version",
        "target",
        "submissions",
        "accepted_normalized_values",
        "source",
        "adjudication",
    }
)
_REVIEW_TARGET_KEYS = frozenset(
    {
        "target_id",
        "paper_id",
        "article_family_id",
        "object_type",
        "key",
        "kind",
        "critical_for_hard_audit",
    }
)
_REVIEW_SUBMISSION_KEYS = frozenset(
    {"target_id", "reviewer_id", "accepted_normalized_values", "source", "note"}
)
_ADJUDICATION_KEYS = frozenset(
    {
        "target_id",
        "adjudicator_id",
        "accepted_normalized_values",
        "source",
        "note",
    }
)
_SOURCE_KEYS = frozenset(
    {
        "artifact_id",
        "page",
        "section",
        "table",
        "figure",
        "row",
        "column",
        "char_start",
        "char_end",
        "bbox",
        "text_quote",
    }
)
_PREDICTION_ARTIFACT_KEYS = frozenset({"schema_version", "predictions"})
_PREDICTION_KEYS = frozenset({"target_id", "resolution"})
_RESOLUTION_KEYS = frozenset(
    {
        "decision",
        "normalized_value",
        "accepted_candidates",
        "calibration_threshold",
        "shift_p_value",
        "reason",
    }
)
_CANDIDATE_KEYS = frozenset(
    {
        "parser_id",
        "parser_family",
        "raw",
        "normalized_value",
        "nonconformity_score",
        "source",
    }
)


@dataclass(frozen=True)
class ExtractionArchivedThresholdRun:
    threshold_id: str
    threshold: float
    execution_id: str
    prediction_artifact_path: str

    def __post_init__(self) -> None:
        _require_nonempty_string(self.threshold_id, label="threshold_id")
        _require_finite_nonnegative_number(self.threshold, label="threshold")
        _require_nonempty_string(self.execution_id, label="execution_id")
        _require_safe_relative_path(self.prediction_artifact_path)


@dataclass(frozen=True)
class ExtractionReleaseEvidenceBundle:
    review_records: tuple[ExtractionReviewRecord, ...]
    threshold_policy: ExtractionThresholdPolicy
    development_runs: tuple[ExtractionArchivedThresholdRun, ...]
    test_runs: tuple[ExtractionArchivedThresholdRun, ...]
    production_authorized: bool = False
    schema_version: int = 1

    def __post_init__(self) -> None:
        if not isinstance(self.review_records, tuple) or not self.review_records:
            raise ValueError("release evidence bundle requires review records")
        if any(not isinstance(record, ExtractionReviewRecord) for record in self.review_records):
            raise TypeError("release evidence bundle review_records are invalid")
        if not isinstance(self.threshold_policy, ExtractionThresholdPolicy):
            raise TypeError("release evidence bundle threshold_policy is invalid")
        for label, runs in (
            ("DEVELOPMENT", self.development_runs),
            ("TEST", self.test_runs),
        ):
            if not isinstance(runs, tuple) or not runs:
                raise ValueError(f"release evidence bundle requires {label} runs")
            if any(not isinstance(run, ExtractionArchivedThresholdRun) for run in runs):
                raise TypeError(f"release evidence bundle {label} runs are invalid")
            threshold_ids = [run.threshold_id for run in runs]
            execution_ids = [run.execution_id for run in runs]
            if len(set(threshold_ids)) != len(threshold_ids):
                raise ValueError(f"release evidence bundle {label} threshold ids must be unique")
            if len(set(execution_ids)) != len(execution_ids):
                raise ValueError(f"release evidence bundle {label} execution ids must be unique")
        paths = [
            run.prediction_artifact_path
            for run in (*self.development_runs, *self.test_runs)
        ]
        if len(set(paths)) != len(paths):
            raise ValueError("release evidence bundle prediction artifact paths must be unique")
        if type(self.production_authorized) is not bool or self.production_authorized:
            raise ValueError("release evidence bundles are non-production only")
        if isinstance(self.schema_version, bool) or not isinstance(self.schema_version, int):
            raise TypeError("release evidence bundle schema_version must be integer 1")
        if self.schema_version != 1:
            raise ValueError("release evidence bundle schema_version must be integer 1")

    def sha256(self) -> str:
        raw = json.dumps(
            extraction_release_evidence_bundle_payload(self),
            ensure_ascii=False,
            sort_keys=True,
            separators=(",", ":"),
        ).encode("utf-8")
        return sha256(raw).hexdigest()


def extraction_release_evidence_bundle_payload(
    bundle: ExtractionReleaseEvidenceBundle,
) -> dict[str, object]:
    if not isinstance(bundle, ExtractionReleaseEvidenceBundle):
        raise TypeError("bundle must be an ExtractionReleaseEvidenceBundle")
    return {
        "schema_version": bundle.schema_version,
        "review_records": [
            _review_record_payload(record)
            for record in sorted(bundle.review_records, key=lambda item: item.target.target_id)
        ],
        "threshold_policy": {
            "schema_version": bundle.threshold_policy.schema_version,
            "min_selective_coverage": bundle.threshold_policy.min_selective_coverage,
            "min_accepted_full_accuracy": bundle.threshold_policy.min_accepted_full_accuracy,
            "max_critical_family_wrong_accept_upper_bound": (
                bundle.threshold_policy.max_critical_family_wrong_accept_upper_bound
            ),
        },
        "development_runs": [
            asdict(run) for run in sorted(bundle.development_runs, key=lambda item: item.threshold_id)
        ],
        "test_runs": [
            asdict(run) for run in sorted(bundle.test_runs, key=lambda item: item.threshold_id)
        ],
        "production_authorized": bundle.production_authorized,
    }


def load_extraction_release_evidence_bundle(
    path: str | Path,
) -> ExtractionReleaseEvidenceBundle:
    payload = _load_strict_json_file(path, label="extraction release evidence bundle")
    _require_exact_keys(payload, _BUNDLE_KEYS, label="extraction release evidence bundle")
    review_rows = payload["review_records"]
    development_rows = payload["development_runs"]
    test_rows = payload["test_runs"]
    if not isinstance(review_rows, list):
        raise TypeError("release evidence bundle review_records must be an array")
    if not isinstance(development_rows, list):
        raise TypeError("release evidence bundle development_runs must be an array")
    if not isinstance(test_rows, list):
        raise TypeError("release evidence bundle test_runs must be an array")
    policy_payload = payload["threshold_policy"]
    _require_exact_keys(policy_payload, _POLICY_KEYS, label="threshold policy")
    policy = ExtractionThresholdPolicy(
        min_selective_coverage=policy_payload["min_selective_coverage"],
        min_accepted_full_accuracy=policy_payload["min_accepted_full_accuracy"],
        max_critical_family_wrong_accept_upper_bound=policy_payload[
            "max_critical_family_wrong_accept_upper_bound"
        ],
        schema_version=policy_payload["schema_version"],
    )
    return ExtractionReleaseEvidenceBundle(
        review_records=tuple(
            _review_record_from_mapping(row, index=index)
            for index, row in enumerate(review_rows)
        ),
        threshold_policy=policy,
        development_runs=tuple(
            _run_from_mapping(row, label=f"development run {index}")
            for index, row in enumerate(development_rows)
        ),
        test_runs=tuple(
            _run_from_mapping(row, label=f"test run {index}")
            for index, row in enumerate(test_rows)
        ),
        production_authorized=payload["production_authorized"],
        schema_version=payload["schema_version"],
    )


def load_extraction_prediction_artifact(
    path: str | Path,
) -> tuple[ExtractionPrediction, ...]:
    source_path = Path(path)
    raw = source_path.read_bytes()
    payload = _loads_strict_json_bytes(raw, label="extraction prediction artifact")
    _require_exact_keys(payload, _PREDICTION_ARTIFACT_KEYS, label="prediction artifact")
    schema_version = payload["schema_version"]
    if isinstance(schema_version, bool) or not isinstance(schema_version, int):
        raise TypeError("prediction artifact schema_version must be integer 1")
    if schema_version != 1:
        raise ValueError("prediction artifact schema_version must be integer 1")
    rows = payload["predictions"]
    if not isinstance(rows, list):
        raise TypeError("prediction artifact predictions must be an array")
    predictions = tuple(
        _prediction_from_mapping(row, index=index) for index, row in enumerate(rows)
    )
    target_ids = [prediction.target_id for prediction in predictions]
    if len(set(target_ids)) != len(target_ids):
        raise ValueError("prediction artifact target_id values must be unique")
    if raw != extraction_prediction_artifact_bytes(predictions):
        raise ValueError("prediction artifact bytes do not use the canonical JSON contract")
    return predictions


def rebuild_attested_extraction_evidence_release_receipt_from_archive(
    bundle: ExtractionReleaseEvidenceBundle,
    *,
    release_artifact_root: str | Path,
    plan: ExtractionEvidencePlan,
    sampling_frame: ExtractionSamplingFrame,
    seed_manifest: ExtractionSeedManifest,
    threshold_grid: ExtractionThresholdGrid,
    execution_plan: ExtractionExecutionPlan,
) -> AttestedExtractionEvidenceReleaseReceipt:
    if not isinstance(bundle, ExtractionReleaseEvidenceBundle):
        raise TypeError("bundle must be an ExtractionReleaseEvidenceBundle")
    if not isinstance(plan, ExtractionEvidencePlan):
        raise TypeError("plan must be an ExtractionEvidencePlan")
    if not isinstance(sampling_frame, ExtractionSamplingFrame):
        raise TypeError("sampling_frame must be an ExtractionSamplingFrame")
    if not isinstance(seed_manifest, ExtractionSeedManifest):
        raise TypeError("seed_manifest must be an ExtractionSeedManifest")
    if not isinstance(threshold_grid, ExtractionThresholdGrid):
        raise TypeError("threshold_grid must be an ExtractionThresholdGrid")
    if not isinstance(execution_plan, ExtractionExecutionPlan):
        raise TypeError("execution_plan must be an ExtractionExecutionPlan")

    expected_plan = build_extraction_evidence_plan(
        sampling_frame,
        seed_manifest,
        threshold_grid,
        review_protocol_version=plan.review_protocol_version,
        split_salt=plan.split_salt,
        train_fraction=plan.train_fraction,
        development_fraction=plan.development_fraction,
        benchmark_confidence=plan.benchmark_confidence,
    )
    if expected_plan != plan:
        raise ValueError("evidence plan differs from supplied sampling/seed/grid source archives")

    gold_manifest = build_extraction_gold_manifest(
        bundle.review_records,
        split_salt=plan.split_salt,
        source_seed_manifest_sha256=seed_manifest.source_manifest_sha256,
        review_protocol_version=plan.review_protocol_version,
    )
    split_lock = gold_manifest.build_split_lock(
        train_fraction=plan.train_fraction,
        development_fraction=plan.development_fraction,
    )
    development_manifest = build_extraction_split_target_manifest(
        gold_manifest,
        split_lock,
        split=BenchmarkSplit.DEVELOPMENT,
    )
    test_manifest = build_extraction_split_target_manifest(
        gold_manifest,
        split_lock,
        split=BenchmarkSplit.TEST,
    )
    development_gold = _gold_subset(gold_manifest.targets, development_manifest.target_ids)
    test_gold = _gold_subset(gold_manifest.targets, test_manifest.target_ids)

    root = _validated_artifact_root(release_artifact_root)
    development_observations, development_execution = _rebuild_threshold_runs(
        bundle.development_runs,
        split=BenchmarkSplit.DEVELOPMENT,
        gold=development_gold,
        target_manifest_sha256=development_manifest.sha256(),
        threshold_grid=threshold_grid,
        execution_plan=execution_plan,
        benchmark_confidence=plan.benchmark_confidence,
        release_artifact_root=root,
    )
    test_observations, test_execution = _rebuild_threshold_runs(
        bundle.test_runs,
        split=BenchmarkSplit.TEST,
        gold=test_gold,
        target_manifest_sha256=test_manifest.sha256(),
        threshold_grid=threshold_grid,
        execution_plan=execution_plan,
        benchmark_confidence=plan.benchmark_confidence,
        release_artifact_root=root,
    )

    frozen_threshold = select_development_threshold(
        development_observations,
        policy=bundle.threshold_policy,
        development_manifest_sha256=development_manifest.sha256(),
    )
    test_seal = seal_extraction_test_set(gold_manifest, split_lock)
    test_evaluation_lock = lock_test_evaluation(
        frozen_threshold,
        test_manifest_sha256=test_manifest.sha256(),
    )
    development_curve = build_extraction_selectivity_curve(
        tuple(
            (observation.threshold, observation.report)
            for observation in development_observations
        )
    )
    test_curve = build_extraction_selectivity_curve(
        tuple((observation.threshold, observation.report) for observation in test_observations)
    )

    return build_attested_extraction_evidence_release_receipt(
        execution_plan=execution_plan,
        development_execution_evidence=development_execution,
        test_execution_evidence=test_execution,
        plan=plan,
        sampling_frame=sampling_frame,
        seed_manifest=seed_manifest,
        threshold_grid=threshold_grid,
        gold_manifest=gold_manifest,
        review_records=bundle.review_records,
        split_lock=split_lock,
        threshold_policy=bundle.threshold_policy,
        development_observations=development_observations,
        test_observations=test_observations,
        frozen_threshold=frozen_threshold,
        test_seal=test_seal,
        test_evaluation_lock=test_evaluation_lock,
        development_curve=development_curve,
        test_curve=test_curve,
    )


def _rebuild_threshold_runs(
    runs: tuple[ExtractionArchivedThresholdRun, ...],
    *,
    split: BenchmarkSplit,
    gold: tuple[Any, ...],
    target_manifest_sha256: str,
    threshold_grid: ExtractionThresholdGrid,
    execution_plan: ExtractionExecutionPlan,
    benchmark_confidence: float,
    release_artifact_root: Path,
) -> tuple[tuple[ExtractionThresholdObservation, ...], tuple[Any, ...]]:
    expected = {
        threshold_id: float(threshold) for threshold_id, threshold in threshold_grid.points
    }
    actual = {run.threshold_id: run for run in runs}
    if set(actual) != set(expected):
        missing = tuple(sorted(set(expected) - set(actual)))
        extra = tuple(sorted(set(actual) - set(expected)))
        raise ValueError(
            f"{split.value} threshold runs differ from precommitted grid; "
            f"missing={missing!r}, extra={extra!r}"
        )

    observations: list[ExtractionThresholdObservation] = []
    execution_evidence: list[Any] = []
    for threshold_id in sorted(expected):
        run = actual[threshold_id]
        if float(run.threshold) != expected[threshold_id]:
            raise ValueError(
                f"{split.value} threshold value differs from precommitted grid: "
                f"{threshold_id!r}"
            )
        artifact_path = _resolve_regular_file(
            release_artifact_root,
            run.prediction_artifact_path,
        )
        artifact_bytes = artifact_path.read_bytes()
        predictions = load_extraction_prediction_artifact(artifact_path)
        report = evaluate_extraction_benchmark(
            gold,
            predictions,
            confidence=benchmark_confidence,
        )
        observation = ExtractionThresholdObservation(
            threshold_id=run.threshold_id,
            threshold=run.threshold,
            split=split,
            report=report,
            predictions=predictions,
        )
        observations.append(observation)
        execution_evidence.append(
            build_extraction_execution_evidence(
                plan=execution_plan,
                execution_id=run.execution_id,
                split=split,
                threshold_id=run.threshold_id,
                threshold=run.threshold,
                target_manifest_sha256=target_manifest_sha256,
                predictions=predictions,
                prediction_artifact=artifact_bytes,
            )
        )
    return tuple(observations), tuple(execution_evidence)


def _gold_subset(gold: tuple[Any, ...], target_ids: tuple[str, ...]) -> tuple[Any, ...]:
    target_id_set = set(target_ids)
    return tuple(target for target in gold if target.target_id in target_id_set)


def _run_from_mapping(value: object, *, label: str) -> ExtractionArchivedThresholdRun:
    _require_exact_keys(value, _RUN_KEYS, label=label)
    return ExtractionArchivedThresholdRun(
        threshold_id=value["threshold_id"],
        threshold=value["threshold"],
        execution_id=value["execution_id"],
        prediction_artifact_path=value["prediction_artifact_path"],
    )


def _review_record_payload(record: ExtractionReviewRecord) -> dict[str, object]:
    return {
        "schema_version": record.schema_version,
        "target": {
            "target_id": record.target.target_id,
            "paper_id": record.target.paper_id,
            "article_family_id": record.target.article_family_id,
            "object_type": record.target.object_type,
            "key": record.target.key,
            "kind": record.target.kind.value,
            "critical_for_hard_audit": record.target.critical_for_hard_audit,
        },
        "submissions": [
            {
                "target_id": submission.target_id,
                "reviewer_id": submission.reviewer_id,
                "accepted_normalized_values": list(submission.accepted_normalized_values),
                "source": _source_payload(submission.source),
                "note": submission.note,
            }
            for submission in sorted(record.submissions, key=lambda item: item.reviewer_id)
        ],
        "accepted_normalized_values": list(record.accepted_normalized_values),
        "source": _source_payload(record.source),
        "adjudication": (
            {
                "target_id": record.adjudication.target_id,
                "adjudicator_id": record.adjudication.adjudicator_id,
                "accepted_normalized_values": list(
                    record.adjudication.accepted_normalized_values
                ),
                "source": _source_payload(record.adjudication.source),
                "note": record.adjudication.note,
            }
            if record.adjudication is not None
            else None
        ),
    }


def _review_record_from_mapping(value: object, *, index: int) -> ExtractionReviewRecord:
    label = f"review record {index}"
    _require_exact_keys(value, _REVIEW_RECORD_KEYS, label=label)
    target_payload = value["target"]
    _require_exact_keys(target_payload, _REVIEW_TARGET_KEYS, label=f"{label} target")
    target = ExtractionReviewTarget(
        target_id=target_payload["target_id"],
        paper_id=target_payload["paper_id"],
        article_family_id=target_payload["article_family_id"],
        object_type=target_payload["object_type"],
        key=target_payload["key"],
        kind=_evidence_kind(target_payload["kind"], label=f"{label} target kind"),
        critical_for_hard_audit=target_payload["critical_for_hard_audit"],
    )
    submissions_payload = value["submissions"]
    if not isinstance(submissions_payload, list):
        raise TypeError(f"{label} submissions must be an array")
    submissions: list[ExtractionReviewSubmission] = []
    for submission_index, submission_payload in enumerate(submissions_payload):
        submission_label = f"{label} submission {submission_index}"
        _require_exact_keys(
            submission_payload,
            _REVIEW_SUBMISSION_KEYS,
            label=submission_label,
        )
        submissions.append(
            ExtractionReviewSubmission(
                target_id=submission_payload["target_id"],
                reviewer_id=submission_payload["reviewer_id"],
                accepted_normalized_values=_string_tuple(
                    submission_payload["accepted_normalized_values"],
                    label=f"{submission_label} accepted_normalized_values",
                ),
                source=_source_from_mapping(
                    submission_payload["source"],
                    label=f"{submission_label} source",
                ),
                note=_string(submission_payload["note"], label=f"{submission_label} note"),
            )
        )
    adjudication_payload = value["adjudication"]
    adjudication = None
    if adjudication_payload is not None:
        _require_exact_keys(
            adjudication_payload,
            _ADJUDICATION_KEYS,
            label=f"{label} adjudication",
        )
        adjudication = ExtractionAdjudication(
            target_id=adjudication_payload["target_id"],
            adjudicator_id=adjudication_payload["adjudicator_id"],
            accepted_normalized_values=_string_tuple(
                adjudication_payload["accepted_normalized_values"],
                label=f"{label} adjudication accepted_normalized_values",
            ),
            source=_source_from_mapping(
                adjudication_payload["source"],
                label=f"{label} adjudication source",
            ),
            note=adjudication_payload["note"],
        )
    return ExtractionReviewRecord(
        target=target,
        submissions=tuple(submissions),
        accepted_normalized_values=_string_tuple(
            value["accepted_normalized_values"],
            label=f"{label} accepted_normalized_values",
        ),
        source=_source_from_mapping(value["source"], label=f"{label} source"),
        adjudication=adjudication,
        schema_version=value["schema_version"],
    )


def _prediction_from_mapping(value: object, *, index: int) -> ExtractionPrediction:
    label = f"prediction {index}"
    _require_exact_keys(value, _PREDICTION_KEYS, label=label)
    target_id = _nonempty_string(value["target_id"], label=f"{label} target_id")
    resolution_payload = value["resolution"]
    _require_exact_keys(resolution_payload, _RESOLUTION_KEYS, label=f"{label} resolution")
    candidates_payload = resolution_payload["accepted_candidates"]
    if not isinstance(candidates_payload, list):
        raise TypeError(f"{label} accepted_candidates must be an array")
    candidates: list[ExtractionCandidate] = []
    for candidate_index, candidate_payload in enumerate(candidates_payload):
        candidate_label = f"{label} candidate {candidate_index}"
        _require_exact_keys(candidate_payload, _CANDIDATE_KEYS, label=candidate_label)
        candidates.append(
            ExtractionCandidate(
                parser_id=candidate_payload["parser_id"],
                parser_family=candidate_payload["parser_family"],
                raw=_string(candidate_payload["raw"], label=f"{candidate_label} raw"),
                normalized_value=candidate_payload["normalized_value"],
                nonconformity_score=candidate_payload["nonconformity_score"],
                source=_source_from_mapping(
                    candidate_payload["source"],
                    label=f"{candidate_label} source",
                ),
            )
        )
    decision_value = resolution_payload["decision"]
    if not isinstance(decision_value, str):
        raise TypeError(f"{label} resolution decision must be a string")
    try:
        decision = ExtractionDecision(decision_value)
    except ValueError as exc:
        raise ValueError(f"{label} resolution decision is unsupported") from exc
    normalized_value = resolution_payload["normalized_value"]
    if normalized_value is not None and not isinstance(normalized_value, str):
        raise TypeError(f"{label} resolution normalized_value must be a string or null")
    shift_p_value = resolution_payload["shift_p_value"]
    if shift_p_value is not None:
        _require_finite_number(shift_p_value, label=f"{label} resolution shift_p_value")
    resolution = ExtractionResolution(
        decision=decision,
        normalized_value=normalized_value,
        accepted_candidates=tuple(candidates),
        calibration_threshold=resolution_payload["calibration_threshold"],
        shift_p_value=shift_p_value,
        reason=_string(resolution_payload["reason"], label=f"{label} resolution reason"),
    )
    return ExtractionPrediction(target_id=target_id, resolution=resolution)


def _source_payload(source: SourceLocation) -> dict[str, object]:
    return {
        "artifact_id": source.artifact_id,
        "page": source.page,
        "section": source.section,
        "table": source.table,
        "figure": source.figure,
        "row": source.row,
        "column": source.column,
        "char_start": source.char_start,
        "char_end": source.char_end,
        "bbox": list(source.bbox) if source.bbox is not None else None,
        "text_quote": source.text_quote,
    }


def _source_from_mapping(value: object, *, label: str) -> SourceLocation:
    _require_exact_keys(value, _SOURCE_KEYS, label=label)
    artifact_id = _nonempty_string(value["artifact_id"], label=f"{label} artifact_id")
    page = _optional_int(value["page"], label=f"{label} page")
    char_start = _optional_int(value["char_start"], label=f"{label} char_start")
    char_end = _optional_int(value["char_end"], label=f"{label} char_end")
    bbox_payload = value["bbox"]
    bbox = None
    if bbox_payload is not None:
        if not isinstance(bbox_payload, list) or len(bbox_payload) != 4:
            raise TypeError(f"{label} bbox must be a four-number array or null")
        bbox_values = tuple(
            _finite_number(item, label=f"{label} bbox value") for item in bbox_payload
        )
        bbox = bbox_values
    return SourceLocation(
        artifact_id=artifact_id,
        page=page,
        section=_optional_string(value["section"], label=f"{label} section"),
        table=_optional_string(value["table"], label=f"{label} table"),
        figure=_optional_string(value["figure"], label=f"{label} figure"),
        row=_optional_string(value["row"], label=f"{label} row"),
        column=_optional_string(value["column"], label=f"{label} column"),
        char_start=char_start,
        char_end=char_end,
        bbox=bbox,
        text_quote=_optional_string(value["text_quote"], label=f"{label} text_quote"),
    )


def _load_strict_json_file(path: str | Path, *, label: str) -> dict[str, Any]:
    raw = Path(path).read_bytes()
    payload = _loads_strict_json_bytes(raw, label=label)
    if not isinstance(payload, dict):
        raise TypeError(f"{label} root must be an object")
    return payload


def _loads_strict_json_bytes(raw: bytes, *, label: str) -> Any:
    try:
        text = raw.decode("utf-8")
    except UnicodeDecodeError as exc:
        raise ValueError(f"{label} must be UTF-8 JSON") from exc

    def reject_duplicate(pairs: list[tuple[str, Any]]) -> dict[str, Any]:
        result: dict[str, Any] = {}
        for key, value in pairs:
            if key in result:
                raise ValueError(f"{label} contains duplicate JSON key: {key!r}")
            result[key] = value
        return result

    def reject_constant(value: str) -> None:
        raise ValueError(f"{label} contains non-standard JSON number: {value}")

    try:
        return json.loads(
            text,
            object_pairs_hook=reject_duplicate,
            parse_constant=reject_constant,
        )
    except json.JSONDecodeError as exc:
        raise ValueError(f"{label} must contain valid JSON") from exc


def _validated_artifact_root(root: str | Path) -> Path:
    root_path = Path(root)
    if root_path.is_symlink():
        raise ValueError("release artifact root must not be a symbolic link")
    resolved = root_path.resolve(strict=True)
    if not resolved.is_dir():
        raise ValueError("release artifact root must be a directory")
    return resolved


def _resolve_regular_file(root: Path, relative_path: str) -> Path:
    _require_safe_relative_path(relative_path)
    current = root
    for part in relative_path.split("/"):
        current = current / part
        if current.is_symlink():
            raise ValueError("release artifact paths must not contain symbolic links")
    resolved = current.resolve(strict=True)
    if not resolved.is_relative_to(root):
        raise ValueError("release artifact path escapes the configured root")
    if not resolved.is_file():
        raise ValueError("release artifact path must reference a regular file")
    return resolved


def _require_safe_relative_path(value: object) -> None:
    if not isinstance(value, str) or not value:
        raise ValueError("release artifact path must be a non-empty string")
    if "\\" in value or value.startswith("/"):
        raise ValueError("release artifact path must be a safe POSIX relative path")
    parts = value.split("/")
    if any(part in {"", ".", ".."} for part in parts):
        raise ValueError("release artifact path must be a safe POSIX relative path")


def _require_exact_keys(value: object, expected: frozenset[str], *, label: str) -> None:
    if not isinstance(value, dict):
        raise TypeError(f"{label} must be an object")
    actual = frozenset(value)
    if actual != expected:
        missing = tuple(sorted(expected - actual))
        unknown = tuple(sorted(actual - expected))
        raise ValueError(
            f"{label} keys differ from schema; missing={missing!r}, unknown={unknown!r}"
        )


def _require_nonempty_string(value: object, *, label: str) -> None:
    _nonempty_string(value, label=label)


def _nonempty_string(value: object, *, label: str) -> str:
    if not isinstance(value, str) or not value.strip():
        raise ValueError(f"{label} must be a non-empty string")
    return value


def _string(value: object, *, label: str) -> str:
    if not isinstance(value, str):
        raise TypeError(f"{label} must be a string")
    return value


def _optional_string(value: object, *, label: str) -> str | None:
    if value is None:
        return None
    if not isinstance(value, str):
        raise TypeError(f"{label} must be a string or null")
    return value


def _optional_int(value: object, *, label: str) -> int | None:
    if value is None:
        return None
    if isinstance(value, bool) or not isinstance(value, int):
        raise TypeError(f"{label} must be an integer or null")
    return value


def _string_tuple(value: object, *, label: str) -> tuple[str, ...]:
    if not isinstance(value, list) or not value:
        raise ValueError(f"{label} must be a non-empty string array")
    if any(not isinstance(item, str) or not item.strip() for item in value):
        raise ValueError(f"{label} must contain non-empty strings")
    return tuple(value)


def _evidence_kind(value: object, *, label: str) -> EvidenceKind:
    if not isinstance(value, str):
        raise TypeError(f"{label} must be a string")
    try:
        return EvidenceKind(value)
    except ValueError as exc:
        raise ValueError(f"{label} is unsupported") from exc


def _require_finite_nonnegative_number(value: object, *, label: str) -> None:
    number = _finite_number(value, label=label)
    if float(number) < 0.0:
        raise ValueError(f"{label} must be non-negative")


def _require_finite_number(value: object, *, label: str) -> None:
    _finite_number(value, label=label)


def _finite_number(value: object, *, label: str) -> int | float:
    if (
        isinstance(value, bool)
        or not isinstance(value, (int, float))
        or not math.isfinite(float(value))
    ):
        raise ValueError(f"{label} must be a finite number")
    return value
