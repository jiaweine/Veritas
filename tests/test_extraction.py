from dataclasses import replace

import pytest

from veritas.extraction import (
    ConformalCalibration,
    ConformalExtractionGate,
    ExtractionCandidate,
    ExtractionDecision,
    ExtractionResolution,
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


@pytest.mark.parametrize("score", [True, float("nan"), float("inf"), -float("inf"), -0.01])
def test_candidate_rejects_boolean_nonfinite_or_negative_scores(score):
    with pytest.raises(ValueError, match="nonconformity_score"):
        _candidate("native", "native_pdf", "0.183", score)


def test_candidate_identity_and_source_are_strictly_typed():
    candidate = _candidate("native", "native_pdf", "0.183", 0.02)
    with pytest.raises(ValueError, match="parser_id"):
        replace(candidate, parser_id="")
    with pytest.raises(ValueError, match="normalized_value"):
        replace(candidate, normalized_value="")
    with pytest.raises(TypeError, match="SourceLocation"):
        replace(candidate, source="Table 2")


@pytest.mark.parametrize("score", [True, float("nan"), float("inf"), -0.01])
def test_calibration_rejects_invalid_nonconformity_scores(score):
    with pytest.raises(ValueError, match="calibration nonconformity score"):
        ConformalCalibration((0.01, score, 0.03))


@pytest.mark.parametrize("value", [True, float("nan"), float("inf"), 0.0, 1.0])
def test_calibration_rejects_invalid_alpha(value):
    with pytest.raises(ValueError, match="alpha"):
        ConformalCalibration((0.01, 0.02), alpha=value)


def test_resolution_rejects_internally_inconsistent_accept_and_conflict_states():
    first = _candidate("native", "native_pdf", "0.183", 0.02)
    second = _candidate("vlm", "vision_language", "0.138", 0.02)

    with pytest.raises(ValueError, match="requires accepted candidates"):
        ExtractionResolution(
            decision=ExtractionDecision.ACCEPT,
            normalized_value="0.183",
            accepted_candidates=(),
            calibration_threshold=0.05,
        )
    with pytest.raises(ValueError, match="agree with normalized_value"):
        ExtractionResolution(
            decision=ExtractionDecision.ACCEPT,
            normalized_value="0.183",
            accepted_candidates=(second,),
            calibration_threshold=0.05,
        )
    with pytest.raises(ValueError, match="at least two candidate values"):
        ExtractionResolution(
            decision=ExtractionDecision.CONFLICT,
            normalized_value=None,
            accepted_candidates=(first,),
            calibration_threshold=0.05,
        )
    with pytest.raises(ValueError, match="DOMAIN_SHIFT"):
        ExtractionResolution(
            decision=ExtractionDecision.DOMAIN_SHIFT,
            normalized_value=None,
            accepted_candidates=(first, second),
            calibration_threshold=0.05,
        )


def test_gate_rejects_boolean_family_count_and_nonfinite_shift_score():
    calibration = ConformalCalibration((0.01, 0.02, 0.03))
    with pytest.raises(TypeError, match="min_independent_families"):
        ConformalExtractionGate(calibration, min_independent_families=True)

    gate = ConformalExtractionGate(calibration)
    with pytest.raises(ValueError, match="shift_score"):
        gate.resolve([_candidate("native", "native_pdf", "0.183", 0.01)], shift_score=float("nan"))
