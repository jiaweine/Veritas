from veritas.extraction import (
    ConformalCalibration,
    ConformalExtractionGate,
    ExtractionCandidate,
    ExtractionDecision,
)
from veritas.models import SourceLocation


def _candidate(parser_id: str, family: str, value: str, score: float) -> ExtractionCandidate:
    return ExtractionCandidate(
        parser_id=parser_id,
        parser_family=family,
        raw=value,
        normalized_value=value,
        nonconformity_score=score,
        source=SourceLocation(page=3, table="2"),
    )


def test_conformal_gate_accepts_cross_family_agreement():
    calibration = ConformalCalibration((0.01, 0.02, 0.03, 0.04, 0.05), alpha=0.2)
    gate = ConformalExtractionGate(calibration)

    result = gate.resolve(
        [
            _candidate("native", "native_pdf", "0.183", 0.02),
            _candidate("vlm", "vision_language", "0.183", 0.03),
        ]
    )

    assert result.decision is ExtractionDecision.ACCEPT
    assert result.normalized_value == "0.183"


def test_conformal_gate_refuses_conflicting_calibrated_values():
    calibration = ConformalCalibration((0.01, 0.02, 0.03, 0.04, 0.05), alpha=0.2)
    gate = ConformalExtractionGate(calibration)

    result = gate.resolve(
        [
            _candidate("native", "native_pdf", "0.183", 0.02),
            _candidate("vlm", "vision_language", "0.138", 0.02),
        ]
    )

    assert result.decision is ExtractionDecision.CONFLICT
    assert result.normalized_value is None


def test_shift_gate_abstains_on_extreme_input():
    calibration = ConformalCalibration(
        (0.01, 0.02, 0.03, 0.04, 0.05),
        alpha=0.2,
        shift_scores=tuple(float(i) for i in range(1, 200)),
        shift_alpha=0.01,
    )
    gate = ConformalExtractionGate(calibration)

    result = gate.resolve(
        [_candidate("native", "native_pdf", "0.183", 0.02)],
        shift_score=999.0,
    )

    assert result.decision is ExtractionDecision.DOMAIN_SHIFT
    assert result.shift_p_value is not None
    assert result.shift_p_value < 0.01
