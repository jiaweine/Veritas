from __future__ import annotations

from pathlib import Path

from .extraction_input_artifacts import ExtractionInputArtifactManifest
from .extraction_release_archive import (
    ExtractionReleaseEvidenceBundle,
    load_extraction_prediction_artifact,
)


def verify_extraction_release_source_artifacts(
    bundle: ExtractionReleaseEvidenceBundle,
    input_artifact_manifest: ExtractionInputArtifactManifest,
    *,
    release_artifact_root: str | Path,
) -> None:
    """Require every review/prediction source to name a verified input artifact."""
    if not isinstance(bundle, ExtractionReleaseEvidenceBundle):
        raise TypeError("bundle must be an ExtractionReleaseEvidenceBundle")
    if not isinstance(input_artifact_manifest, ExtractionInputArtifactManifest):
        raise TypeError("input_artifact_manifest must be an ExtractionInputArtifactManifest")

    allowed = {artifact.artifact_id for artifact in input_artifact_manifest.artifacts}
    for record in bundle.review_records:
        _require_allowed_source(record.source.artifact_id, allowed, label="review record")
        for submission in record.submissions:
            _require_allowed_source(
                submission.source.artifact_id,
                allowed,
                label="review submission",
            )
        if record.adjudication is not None:
            _require_allowed_source(
                record.adjudication.source.artifact_id,
                allowed,
                label="review adjudication",
            )

    root = _validated_root(release_artifact_root)
    for run in (*bundle.development_runs, *bundle.test_runs):
        artifact_path = _resolve_regular_file(root, run.prediction_artifact_path)
        for prediction in load_extraction_prediction_artifact(artifact_path):
            for candidate in prediction.resolution.accepted_candidates:
                _require_allowed_source(
                    candidate.source.artifact_id,
                    allowed,
                    label="prediction candidate",
                )


def _require_allowed_source(
    artifact_id: str,
    allowed: set[str],
    *,
    label: str,
) -> None:
    if artifact_id not in allowed:
        raise ValueError(
            f"{label} source artifact_id is outside the verified input-artifact manifest: "
            f"{artifact_id!r}"
        )


def _validated_root(root: str | Path) -> Path:
    root_path = Path(root)
    if root_path.is_symlink():
        raise ValueError("release artifact root must not be a symbolic link")
    resolved = root_path.resolve(strict=True)
    if not resolved.is_dir():
        raise ValueError("release artifact root must be a directory")
    return resolved


def _resolve_regular_file(root: Path, relative_path: str) -> Path:
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
