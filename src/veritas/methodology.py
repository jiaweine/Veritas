from __future__ import annotations

from dataclasses import asdict, dataclass
from hashlib import sha256
import json


@dataclass(frozen=True)
class MethodAnchor:
    key: str
    title: str
    authors: str
    year: int
    venue: str
    status: str
    url: str
    doi: str | None = None


METHOD_ANCHORS: tuple[MethodAnchor, ...] = (
    MethodAnchor(
        key="did_jel_2026",
        title="Difference-in-Differences Designs: A Practitioner's Guide",
        authors="Baker, Callaway, Cunningham, Goodman-Bacon, Sant'Anna",
        year=2026,
        venue="Journal of Economic Literature",
        status="published",
        url="https://www.aeaweb.org/articles?id=10.1257/jel.20251650",
        doi="10.1257/jel.20251650",
    ),
    MethodAnchor(
        key="did_bjs_2024",
        title="Revisiting Event-Study Designs: Robust and Efficient Estimation",
        authors="Borusyak, Jaravel, Spiess",
        year=2024,
        venue="Review of Economic Studies",
        status="published",
        url="https://academic.oup.com/restud/article/91/6/3253/7601390",
        doi="10.1093/restud/rdae007",
    ),
    MethodAnchor(
        key="did_continuous_2026",
        title="Difference-in-Differences with a Continuous Treatment",
        authors="Callaway, Goodman-Bacon, Sant'Anna",
        year=2026,
        venue="American Economic Review",
        status="forthcoming",
        url="https://www.aeaweb.org/articles?id=10.1257/aer.20240137",
        doi="10.1257/aer.20240137",
    ),
    MethodAnchor(
        key="weak_iv_jep_2026",
        title="Correct (and Incorrect) Inference with a Single Instrumental Variable",
        authors="Lee, Porter",
        year=2026,
        venue="Journal of Economic Perspectives",
        status="published",
        url="https://www.aeaweb.org/articles?id=10.1257/jep.20251464",
        doi="10.1257/jep.20251464",
    ),
    MethodAnchor(
        key="rdd_extensions_2024",
        title="A Practical Introduction to Regression Discontinuity Designs: Extensions",
        authors="Cattaneo, Idrobo, Titiunik",
        year=2024,
        venue="Cambridge Elements in Quantitative and Computational Methods",
        status="published",
        url="https://www.cambridge.org/core/books/practical-introduction-to-regression-discontinuity-designs/C6A70A32359115510AAC370A7869AE2F",
        doi="10.1017/9781009441896",
    ),
    MethodAnchor(
        key="rdd_density_2024",
        title="Local Regression Distribution Estimators",
        authors="Cattaneo, Jansson, Ma",
        year=2024,
        venue="Journal of Econometrics",
        status="published",
        url="https://rdpackages.github.io/rddensity/",
    ),
    MethodAnchor(
        key="rdd_hte_2025",
        title="rdhte: Conditional Average Treatment Effects in RD Designs",
        authors="Calonico, Cattaneo, Farrell, Palomba, Titiunik",
        year=2025,
        venue="software/methodology article",
        status="preprint-software",
        url="https://rdpackages.github.io/rdhte/",
    ),
    MethodAnchor(
        key="analytic_robustness_nature_2025",
        title="Investigating the analytical robustness of the social and behavioural sciences",
        authors="multi-analyst collaboration",
        year=2025,
        venue="Nature",
        status="published",
        url="https://www.nature.com/articles/s41586-025-09844-9",
        doi="10.1038/s41586-025-09844-9",
    ),
    MethodAnchor(
        key="omnidocbench_2025",
        title="OmniDocBench: A Comprehensive Benchmark for Document Parsing and Evaluation",
        authors="OpenDataLab collaboration",
        year=2025,
        venue="CVPR",
        status="living-benchmark",
        url="https://github.com/opendatalab/OmniDocBench",
    ),
)


def get_method_anchor(key: str) -> MethodAnchor:
    for anchor in METHOD_ANCHORS:
        if anchor.key == key:
            return anchor
    raise KeyError(key)


def methodology_snapshot() -> dict[str, object]:
    return {
        "as_of": "2026-08-30",
        "anchors": [asdict(anchor) for anchor in METHOD_ANCHORS],
    }


def methodology_snapshot_sha256() -> str:
    raw = json.dumps(methodology_snapshot(), sort_keys=True, separators=(",", ":")).encode("utf-8")
    return sha256(raw).hexdigest()
