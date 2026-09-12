from __future__ import annotations

import json
import re
from dataclasses import asdict, dataclass
from datetime import UTC, datetime
from hashlib import sha256

_SHA256_RE = re.compile(r"^[0-9a-f]{64}$")
_GIT_SHA_RE = re.compile(r"^[0-9a-f]{40}$")


@dataclass(frozen=True)
class ExtractionPostverificationExternalArchiveReceipt:
    handoff_sha256: str
    archived_object_set_sha256: str
    source_commit_sha: str
    bound_verification_file_sha256: str
    custodian_identity: str
    archive_channel_identity: str
    archive_record_id: str
    external_timestamp_utc: str | None
    external_sequence_position: str | None
    production_authorized: bool = False
    schema_version: int = 1

    def __post_init__(self) -> None:
        for label, value in (
            ("handoff_sha256", self.handoff_sha256),
            ("archived_object_set_sha256", self.archived_object_set_sha256),
            ("bound_verification_file_sha256", self.bound_verification_file_sha256),
        ):
            _require_sha256(value, label=label)
        _require_git_sha(self.source_commit_sha, label="source_commit_sha")
        for label, value in (
            ("custodian_identity", self.custodian_identity),
            ("archive_channel_identity", self.archive_channel_identity),
            ("archive_record_id", self.archive_record_id),
        ):
            _require_nonempty_string(value, label=label)
        _require_optional_utc_timestamp(self.external_timestamp_utc)
        if self.external_sequence_position is not None:
            _require_nonempty_string(
                self.external_sequence_position,
                label="external_sequence_position",
            )
        if self.external_timestamp_utc is None and self.external_sequence_position is None:
            raise ValueError(
                "post-verification external archive receipt requires an external timestamp "
                "or sequence position"
            )
        if type(self.production_authorized) is not bool or self.production_authorized:
            raise ValueError(
                "post-verification external archive receipts are non-production only"
            )
        _require_schema_version(
            self.schema_version,
            label="post-verification external archive receipt",
        )

    def sha256(self) -> str:
        return _stable_sha256(asdict(self))


@dataclass(frozen=True)
class VerifiedPostverificationExternalArchiveReceiptBinding:
    receipt_sha256: str
    receipt_file_sha256: str
    handoff_sha256: str
    archived_object_set_sha256: str
    source_commit_sha: str
    bound_verification_file_sha256: str
    custodian_identity: str
    archive_channel_identity: str
    archive_record_id: str
    external_timestamp_utc: str | None
    external_sequence_position: str | None
    independent_control_established: bool = False
    historical_channel_semantics_established: bool = False
    production_authorized: bool = False
    schema_version: int = 1

    def __post_init__(self) -> None:
        for label, value in (
            ("receipt_sha256", self.receipt_sha256),
            ("receipt_file_sha256", self.receipt_file_sha256),
            ("handoff_sha256", self.handoff_sha256),
            ("archived_object_set_sha256", self.archived_object_set_sha256),
            ("bound_verification_file_sha256", self.bound_verification_file_sha256),
        ):
            _require_sha256(value, label=label)
        _require_git_sha(self.source_commit_sha, label="source_commit_sha")
        for label, value in (
            ("custodian_identity", self.custodian_identity),
            ("archive_channel_identity", self.archive_channel_identity),
            ("archive_record_id", self.archive_record_id),
        ):
            _require_nonempty_string(value, label=label)
        _require_optional_utc_timestamp(self.external_timestamp_utc)
        if self.external_sequence_position is not None:
            _require_nonempty_string(
                self.external_sequence_position,
                label="external_sequence_position",
            )
        if self.external_timestamp_utc is None and self.external_sequence_position is None:
            raise ValueError(
                "verified post-verification receipt binding requires an external timestamp "
                "or sequence position"
            )
        for label, value in (
            ("independent_control_established", self.independent_control_established),
            (
                "historical_channel_semantics_established",
                self.historical_channel_semantics_established,
            ),
            ("production_authorized", self.production_authorized),
        ):
            if type(value) is not bool or value:
                raise ValueError(
                    f"{label} must remain false for repository-side post-verification binding"
                )
        _require_schema_version(
            self.schema_version,
            label="verified post-verification external archive receipt binding",
        )

    def sha256(self) -> str:
        return _stable_sha256(asdict(self))


def verify_postverification_external_archive_receipt_binding(
    *,
    receipt: ExtractionPostverificationExternalArchiveReceipt,
    receipt_file_sha256: str,
    expected_handoff_sha256: str,
    expected_archived_object_set_sha256: str,
    expected_source_commit_sha: str,
    expected_bound_verification_file_sha256: str,
    expected_custodian_identity: str,
    expected_archive_channel_identity: str,
    expected_archive_record_id: str,
) -> VerifiedPostverificationExternalArchiveReceiptBinding:
    if not isinstance(receipt, ExtractionPostverificationExternalArchiveReceipt):
        raise TypeError(
            "receipt must be an ExtractionPostverificationExternalArchiveReceipt"
        )
    for label, value in (
        ("receipt_file_sha256", receipt_file_sha256),
        ("expected_handoff_sha256", expected_handoff_sha256),
        (
            "expected_archived_object_set_sha256",
            expected_archived_object_set_sha256,
        ),
        (
            "expected_bound_verification_file_sha256",
            expected_bound_verification_file_sha256,
        ),
    ):
        _require_sha256(value, label=label)
    _require_git_sha(expected_source_commit_sha, label="expected_source_commit_sha")
    for label, value in (
        ("expected_custodian_identity", expected_custodian_identity),
        ("expected_archive_channel_identity", expected_archive_channel_identity),
        ("expected_archive_record_id", expected_archive_record_id),
    ):
        _require_nonempty_string(value, label=label)

    comparisons = (
        (receipt.handoff_sha256, expected_handoff_sha256, "handoff"),
        (
            receipt.archived_object_set_sha256,
            expected_archived_object_set_sha256,
            "archived object set",
        ),
        (receipt.source_commit_sha, expected_source_commit_sha, "source commit"),
        (
            receipt.bound_verification_file_sha256,
            expected_bound_verification_file_sha256,
            "bound verification bytes",
        ),
        (receipt.custodian_identity, expected_custodian_identity, "custodian identity"),
        (
            receipt.archive_channel_identity,
            expected_archive_channel_identity,
            "archive channel identity",
        ),
        (receipt.archive_record_id, expected_archive_record_id, "archive record id"),
    )
    for actual, expected, label in comparisons:
        if actual != expected:
            raise ValueError(
                "post-verification external archive receipt is bound to a different "
                f"{label}"
            )

    return VerifiedPostverificationExternalArchiveReceiptBinding(
        receipt_sha256=receipt.sha256(),
        receipt_file_sha256=receipt_file_sha256,
        handoff_sha256=receipt.handoff_sha256,
        archived_object_set_sha256=receipt.archived_object_set_sha256,
        source_commit_sha=receipt.source_commit_sha,
        bound_verification_file_sha256=receipt.bound_verification_file_sha256,
        custodian_identity=receipt.custodian_identity,
        archive_channel_identity=receipt.archive_channel_identity,
        archive_record_id=receipt.archive_record_id,
        external_timestamp_utc=receipt.external_timestamp_utc,
        external_sequence_position=receipt.external_sequence_position,
    )


def _require_optional_utc_timestamp(value: object) -> None:
    if value is None:
        return
    _require_nonempty_string(value, label="external_timestamp_utc")
    if not isinstance(value, str) or not value.endswith("Z"):
        raise ValueError("external_timestamp_utc must be an ISO-8601 UTC timestamp ending in Z")
    try:
        parsed = datetime.fromisoformat(value)
    except ValueError as exc:
        raise ValueError("external_timestamp_utc must be a valid ISO-8601 UTC timestamp") from exc
    if parsed.utcoffset() != UTC.utcoffset(parsed):
        raise ValueError("external_timestamp_utc must use UTC")


def _require_nonempty_string(value: object, *, label: str) -> None:
    if not isinstance(value, str) or not value.strip():
        raise ValueError(f"{label} must be a non-empty string")


def _require_sha256(value: object, *, label: str) -> None:
    if not isinstance(value, str) or not _SHA256_RE.fullmatch(value):
        raise ValueError(f"{label} must be a lowercase SHA-256 digest")


def _require_git_sha(value: object, *, label: str) -> None:
    if not isinstance(value, str) or not _GIT_SHA_RE.fullmatch(value):
        raise ValueError(f"{label} must be a lowercase 40-character git SHA")


def _require_schema_version(value: object, *, label: str) -> None:
    if isinstance(value, bool) or not isinstance(value, int) or value != 1:
        raise ValueError(f"{label} schema_version must be 1")


def _stable_sha256(value: object) -> str:
    raw = json.dumps(
        value,
        ensure_ascii=False,
        sort_keys=True,
        separators=(",", ":"),
    ).encode("utf-8")
    return sha256(raw).hexdigest()
