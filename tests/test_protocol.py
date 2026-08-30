import pytest

from veritas.methodology import methodology_snapshot_sha256
from veritas.protocol import AuditProtocol, ProtocolDriftError, ensure_protocol_lock


def test_protocol_lock_detects_drift(tmp_path):
    path = tmp_path / "audit.lock.json"
    first = AuditProtocol(
        detector_versions={"regression_consistency": "0.1.0"},
        parser_versions={"table_parser": "1.0.0"},
        solver_versions={"scs": "3.2.11"},
        methodology_snapshot_sha256=methodology_snapshot_sha256(),
        extraction_calibration_sha256="c" * 64,
        specification_space_sha256="d" * 64,
    )
    ensure_protocol_lock(path, first)
    ensure_protocol_lock(path, first)

    changed = AuditProtocol(
        detector_versions={"regression_consistency": "0.2.0"},
        parser_versions={"table_parser": "1.0.0"},
        solver_versions={"scs": "3.2.11"},
        methodology_snapshot_sha256=methodology_snapshot_sha256(),
        extraction_calibration_sha256="c" * 64,
        specification_space_sha256="d" * 64,
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


def test_protocol_lock_detects_parser_or_calibration_drift(tmp_path):
    path = tmp_path / "audit.lock.json"
    first = AuditProtocol(parser_versions={"parser": "1"}, extraction_calibration_sha256="a" * 64)
    ensure_protocol_lock(path, first)

    changed = AuditProtocol(parser_versions={"parser": "2"}, extraction_calibration_sha256="a" * 64)
    with pytest.raises(ProtocolDriftError):
        ensure_protocol_lock(path, changed)


def test_protocol_lock_detects_specification_space_drift(tmp_path):
    path = tmp_path / "audit.lock.json"
    first = AuditProtocol(specification_space_sha256="a" * 64)
    ensure_protocol_lock(path, first)

    changed = AuditProtocol(specification_space_sha256="b" * 64)
    with pytest.raises(ProtocolDriftError):
        ensure_protocol_lock(path, changed)


def test_protocol_lock_detects_solver_drift(tmp_path):
    path = tmp_path / "audit.lock.json"
    first = AuditProtocol(solver_versions={"scs": "3.2.11", "scipy": "1.17.1"})
    ensure_protocol_lock(path, first)

    changed = AuditProtocol(solver_versions={"scs": "3.3.0", "scipy": "1.17.1"})
    with pytest.raises(ProtocolDriftError):
        ensure_protocol_lock(path, changed)
