from .base import Detector, DetectorRegistry
from .correlation import CorrelationPSDDetector
from .designs import DIDDesignDetector, WeakIVDesignDetector
from .regression import RegressionConsistencyDetector
from .sample import SampleAccountingDetector

__all__ = [
    "CorrelationPSDDetector",
    "DIDDesignDetector",
    "Detector",
    "DetectorRegistry",
    "RegressionConsistencyDetector",
    "SampleAccountingDetector",
    "WeakIVDesignDetector",
]
