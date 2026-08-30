import pytest

from veritas.protocol import AuditProtocol, ProtocolDriftError, ensure_protocol_lock


def test_protocol_lock_detects_drift(tmp_path):
    path = tmp_path / "audit.lock.json"
    first = AuditProtocol(detector_versions={"regression_consistency": "0.1.0"})
    ensure_protocol_lock(path, first)
    ensure_protocol_lock(path, first)

    changed = AuditProtocol(detector_versions={"regression_consistency": "0.2.0"})
    with pytest.raises(ProtocolDriftError):
        ensure_protocol_lock(path, changed)
