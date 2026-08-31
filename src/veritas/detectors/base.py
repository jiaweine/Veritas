from __future__ import annotations

import json
from abc import ABC, abstractmethod
from collections.abc import Iterable
from hashlib import sha256
from typing import Any

from ..models import CheckResult


class Detector(ABC):
    detector_id: str
    version: str

    @abstractmethod
    def supports(self, obj: Any) -> bool:
        raise NotImplementedError

    @abstractmethod
    def run(self, obj: Any) -> list[CheckResult]:
        raise NotImplementedError


class DetectorRegistry:
    def __init__(self, detectors: Iterable[Detector] = ()) -> None:
        self._detectors: list[Detector] = []
        for detector in detectors:
            self.register(detector)

    def register(self, detector: Detector) -> None:
        identity = (detector.detector_id, detector.version)
        if any((d.detector_id, d.version) == identity for d in self._detectors):
            raise ValueError(f"duplicate detector registration: {identity}")
        self._detectors.append(detector)

    def for_object(self, obj: Any) -> tuple[Detector, ...]:
        return tuple(detector for detector in self._detectors if detector.supports(obj))

    @property
    def detectors(self) -> tuple[Detector, ...]:
        return tuple(self._detectors)

    def sha256(self) -> str:
        """Stable identity of the registered detector ids and declared versions.

        Detector implementations are required to bump ``version`` whenever behavior changes. This
        registry hash is therefore suitable for binding held-out certification to the detector set
        that was actually evaluated, without depending on import order.
        """
        payload = sorted(
            {"detector_id": detector.detector_id, "version": detector.version}
            for detector in self._detectors
        )
        raw = json.dumps(payload, sort_keys=True, separators=(",", ":")).encode("utf-8")
        return sha256(raw).hexdigest()
