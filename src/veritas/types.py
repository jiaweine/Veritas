from __future__ import annotations

from enum import Enum, IntEnum


class EvidenceGrade(IntEnum):
    """Strength of the evidence, not a judgment about author intent."""

    UNVERIFIABLE = 0
    WEAK_SIGNAL = 1
    METHODOLOGICAL_RISK = 2
    INTERNAL_CONTRADICTION = 3
    REPRODUCTION_CONTRADICTION = 4
    DATA_PROVENANCE_CONCERN = 5


class Materiality(IntEnum):
    FORMATTING = 0
    PERIPHERAL = 1
    SECONDARY_RESULT = 2
    MAIN_EMPIRICAL_CLAIM = 3
    CHANGES_SUBSTANTIVE_CONCLUSION = 4


class EvidenceFamily(str, Enum):
    NUMERICAL_CONSISTENCY = "numerical_consistency"
    SAMPLE_CONSISTENCY = "sample_consistency"
    DESIGN_VALIDITY = "design_validity"
    DATA_INTEGRITY = "data_integrity"
    REPRODUCTION = "reproduction"
    PREREGISTRATION = "preregistration"
    PROVENANCE = "provenance"


class CheckStatus(str, Enum):
    PASS = "pass"
    FAIL = "fail"
    REVIEW = "review"
    UNVERIFIABLE = "unverifiable"
    NOT_RELEVANT = "not_relevant"


class ComparisonOperator(str, Enum):
    EQ = "="
    LT = "<"
    LE = "<="
    GT = ">"
    GE = ">="
