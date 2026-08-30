from .algebra import LogitOddsRatioDetector, MediationProductDetector
from .base import Detector, DetectorRegistry
from .correlation import CorrelationPSDDetector
from .designs import DIDDesignDetector, WeakIVDesignDetector
from .discrete import DiscreteSummaryFeasibilityDetector
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
    "RDDDesignDetector",
    "RegressionConsistencyDetector",
    "SampleAccountingDetector",
    "StandardizedRegressionReconstructionDetector",
    "WeakIVDesignDetector",
]
