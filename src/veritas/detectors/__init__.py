from .base import Detector, DetectorRegistry
from .correlation import CorrelationPSDDetector
from .designs import DIDDesignDetector, WeakIVDesignDetector
from .rdd import RDDDesignDetector
from .regression import RegressionConsistencyDetector
from .sample import SampleAccountingDetector

__all__ = [
    "CorrelationPSDDetector",
    "DIDDesignDetector",
    "Detector",
    "DetectorRegistry",
    "RDDDesignDetector",
    "RegressionConsistencyDetector",
    "SampleAccountingDetector",
    "WeakIVDesignDetector",
]
