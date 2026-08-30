import pytest

from veritas.methodology import methodology_snapshot_sha256
from veritas.protocol import AuditProtocol, ProtocolDriftError, ensure_protocol_lock


def test_protocol_lock_detects_drift(tmp_path):
    path = tmp_path / "audit.lock.json"
    first = AuditProtocol(
        detector_versions={"regression_consistency": "0.1.0"},
        methodology_snapshot_sha256=methodology_snapshot_sha256(),
    )
    ensure_protocol_lock(path, first)
    ensure_protocol_lock(path, first)

    changed = AuditProtocol(
        detector_versions={"regression_consistency": "0.2.0"},
        methodology_snapshot_sha256=methodology_snapshot_sha256(),
    )
    with pytest.raises(ProtocolDriftError):
        ensure_protocol_lock(path, changed)


def test_protocol_lock_detects_methodology_snapshot_drift(tmp_path):
    path = tmp_path / "audit.lock.json"
    first = AuditProtocol(methodology_snapshot_sha256="a" * 64)
    ensure_protocol_lock(path, first)

    changed = AuditProtocol(methodology_snapshot_sha256="b" * 64)
    with pytest.raises(ProtocolDriftError):
        ensure_protocol_lock(path, changed)
