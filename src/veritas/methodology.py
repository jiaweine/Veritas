from __future__ import annotations

import json
from dataclasses import asdict, dataclass
from hashlib import sha256


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
        key="grim_2017",
        title="The GRIM Test: A Simple Technique Detects Numerous Anomalies in the Reporting of Results in Psychology",
        authors="Brown, Heathers",
        year=2017,
        venue="Social Psychological and Personality Science",
        status="published",
        url="https://journals.sagepub.com/doi/10.1177/1948550616673876",
        doi="10.1177/1948550616673876",
    ),
    MethodAnchor(
        key="grimmer_2018",
        title="Analytic-GRIMMER: a new way of testing the possibility of standard deviations",
        authors="Allard",
        year=2018,
        venue="methodology note",
        status="published-online",
        url="https://aurelienallard.netlify.app/post/anaytic-grimmer-possibility-standard-deviations/",
    ),
    MethodAnchor(
        key="scrutiny_grimmer_2026",
        title="scrutiny GRIMMER documentation",
        authors="scrutiny maintainers",
        year=2026,
        venue="CRAN software documentation",
        status="living-software-documentation",
        url="https://search.r-project.org/CRAN/refmans/scrutiny/help/grimmer.html",
    ),
    MethodAnchor(
        key="aea_data_code_policy_2026",
        title="Data and Code Availability Policy",
        authors="American Economic Association Data Editor",
        year=2026,
        venue="AEA reproducibility policy",
        status="current-policy",
        url="https://www.aeaweb.org/journals/data/data-code-policy",
    ),
    MethodAnchor(
        key="ssrp_acre_2026",
        title="Social Science Reproduction Platform and ACRe claim-level reproduction workflow",
        authors="BITSS and AEA Data Editor collaboration",
        year=2026,
        venue="Social Science Reproduction Platform",
        status="living-platform",
        url="https://www.socialsciencereproduction.org/about/",
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
    MethodAnchor(
        key="table_understanding_2025",
        title="Table Understanding and (Multimodal) LLMs: A Cross-Domain Case Study",
        authors="Borisova et al.",
        year=2025,
        venue="Table Representation Learning Workshop",
        status="published",
        url="https://aclanthology.org/2025.trl-1.10/",
        doi="10.18653/v1/2025.trl-1.10",
    ),
    MethodAnchor(
        key="sconu_acl_2025",
        title="SConU: Selective Conformal Uncertainty in Large Language Models",
        authors="Wang et al.",
        year=2025,
        venue="ACL",
        status="published",
        url="https://aclanthology.org/2025.acl-long.934/",
        doi="10.18653/v1/2025.acl-long.934",
    ),
    MethodAnchor(
        key="conformal_lvlm_2025",
        title="Towards Statistical Factuality Guarantee for Large Vision-Language Models",
        authors="ConfLVLM authors",
        year=2025,
        venue="EMNLP",
        status="published",
        url="https://aclanthology.org/2025.emnlp-main.576/",
        doi="10.18653/v1/2025.emnlp-main.576",
    ),
)


def get_method_anchor(key: str) -> MethodAnchor:
    for anchor in METHOD_ANCHORS:
        if anchor.key == key:
            return anchor
    raise KeyError(key)


def methodology_snapshot() -> dict[str, object]:
    return {
        "as_of": "2026-08-31",
        "anchors": [asdict(anchor) for anchor in METHOD_ANCHORS],
    }


def methodology_snapshot_sha256() -> str:
    raw = json.dumps(methodology_snapshot(), sort_keys=True, separators=(",", ":")).encode("utf-8")
    return sha256(raw).hexdigest()
