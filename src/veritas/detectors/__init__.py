from .algebra import LogitOddsRatioDetector, MediationProductDetector
from .anova import OneWayAnovaSummaryDetector
from .base import Detector, DetectorRegistry
from .correlation import CorrelationPSDDetector
from .designs import DIDDesignDetector, WeakIVDesignDetector
from .discrete import DiscreteSummaryFeasibilityDetector
from .group_stats import TwoGroupSummaryDetector
from .meta_analysis import MetaAnalysisArithmeticDetector
from .rdd import RDDDesignDetector
from .regression import RegressionConsistencyDetector
from .sample import SampleAccountingDetector
from .sem import SEMFitArithmeticDetector, SEMNestedDifferenceDetector
from .standardized_regression import StandardizedRegressionReconstructionDetector

__all__ = [
    "CorrelationPSDDetector",
    "DIDDesignDetector",
    "Detector",
    "DetectorRegistry",
    "DiscreteSummaryFeasibilityDetector",
    "LogitOddsRatioDetector",
    "MediationProductDetector",
    "MetaAnalysisArithmeticDetector",
    "OneWayAnovaSummaryDetector",
    "RDDDesignDetector",
    "RegressionConsistencyDetector",
    "SEMFitArithmeticDetector",
    "SEMNestedDifferenceDetector",
    "SampleAccountingDetector",
    "StandardizedRegressionReconstructionDetector",
    "TwoGroupSummaryDetector",
    "WeakIVDesignDetector",
]
