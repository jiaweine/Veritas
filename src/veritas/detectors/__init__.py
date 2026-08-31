from .algebra import LogitOddsRatioDetector, MediationProductDetector
from .anova import OneWayAnovaSummaryDetector
from .base import Detector, DetectorRegistry
from .correlation import CorrelationPSDDetector
from .designs import DIDDesignDetector, WeakIVDesignDetector
from .discrete import DiscreteSummaryFeasibilityDetector
from .group_stats import TwoGroupSummaryDetector
from .rdd import RDDDesignDetector
from .regression import RegressionConsistencyDetector
from .sample import SampleAccountingDetector
from .standardized_regression import StandardizedRegressionReconstructionDetector

__all__ = [
    "CorrelationPSDDetector",
    "DIDDesignDetector",
    "Detector",
    "DetectorRegistry",
    "DiscreteSummaryFeasibilityDetector",
    "LogitOddsRatioDetector",
    "MediationProductDetector",
    "OneWayAnovaSummaryDetector",
    "RDDDesignDetector",
    "RegressionConsistencyDetector",
    "SampleAccountingDetector",
    "StandardizedRegressionReconstructionDetector",
    "TwoGroupSummaryDetector",
    "WeakIVDesignDetector",
]
