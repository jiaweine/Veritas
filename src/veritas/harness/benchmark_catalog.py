from __future__ import annotations

from collections.abc import Iterable
from typing import Final

BENCHMARK_CATALOG_SCHEMA_VERSION: Final = "1"

_BENCHMARKS: Final[tuple[dict[str, object], ...]] = (
    {
        "benchmark_id": "pdf-regression",
        "title": "PDF regression benchmark",
        "kind": "benchmark",
        "gating": True,
        "command": "python scripts/benchmark_pdf_regression.py",
        "scope": "native PDF extraction and regression-table evidence",
        "source": "scripts/benchmark_pdf_regression.py",
    },
    {
        "benchmark_id": "pdf-geometry-holdout",
        "title": "PDF geometry holdout",
        "kind": "benchmark",
        "gating": True,
        "command": "python scripts/benchmark_pdf_geometry_holdout.py",
        "scope": "held-out geometry and layout extraction behavior",
        "source": "scripts/benchmark_pdf_geometry_holdout.py",
    },
    {
        "benchmark_id": "extraction-adversarial",
        "title": "Adversarial extraction fail-closed benchmark",
        "kind": "benchmark",
        "gating": True,
        "command": "python scripts/benchmark_extraction_adversarial.py",
        "scope": "negative controls and fail-closed extraction behavior",
        "source": "scripts/benchmark_extraction_adversarial.py",
    },
    {
        "benchmark_id": "bmc-grouped-headers",
        "title": "BMC grouped regression-header probe",
        "kind": "probe",
        "gating": False,
        "command": "python scripts/probe_bmc_grouped_headers.py",
        "scope": "grouped regression headers on external BMC-style material",
        "source": "scripts/probe_bmc_grouped_headers.py",
    },
    {
        "benchmark_id": "real-pdf-smoke",
        "title": "Real PDF extraction smoke",
        "kind": "probe",
        "gating": False,
        "command": "python scripts/smoke_real_pdf.py",
        "scope": "real-paper extraction smoke coverage",
        "source": "scripts/smoke_real_pdf.py",
    },
    {
        "benchmark_id": "real-pdf-fail-closed",
        "title": "Real PDF fail-closed controls",
        "kind": "probe",
        "gating": False,
        "command": "python scripts/smoke_real_pdf_fail_closed.py",
        "scope": "real-paper negative controls and conservative failure behavior",
        "source": "scripts/smoke_real_pdf_fail_closed.py",
    },
    {
        "benchmark_id": "real-pdf-promotion",
        "title": "Real PDF selective-promotion benchmark",
        "kind": "probe",
        "gating": False,
        "command": "python scripts/benchmark_real_pdf_promotion.py",
        "scope": "real-paper parser promotion behavior",
        "source": "scripts/benchmark_real_pdf_promotion.py",
    },
)


def benchmark_suite(benchmark_id: str) -> dict[str, object] | None:
    for item in _BENCHMARKS:
        if item["benchmark_id"] == benchmark_id:
            return dict(item)
    return None


def benchmark_catalog(
    *,
    results: Iterable[dict[str, object]] | None = None,
) -> dict[str, object]:
    """Return benchmark inventory plus real persisted execution provenance.

    The catalog mirrors repository CI commands. Persisted result objects are
    execution facts only; this function never invents benchmark scores.
    """

    result_list = [dict(item) for item in (results or [])]
    latest_by_id: dict[str, dict[str, object]] = {}
    for result in sorted(
        result_list,
        key=lambda item: (str(item.get("recorded_at") or ""), str(item.get("result_id") or "")),
        reverse=True,
    ):
        benchmark_id = str(result.get("benchmark_id") or "")
        if benchmark_id and benchmark_id not in latest_by_id:
            latest_by_id[benchmark_id] = result

    suites = []
    for item in _BENCHMARKS:
        suite = dict(item)
        suite["latest_result"] = latest_by_id.get(str(item["benchmark_id"]))
        suites.append(suite)

    gating = sum(bool(item["gating"]) for item in suites)
    recorded_at = [str(item.get("recorded_at") or "") for item in result_list]
    return {
        "schema_version": BENCHMARK_CATALOG_SCHEMA_VERSION,
        "result_persistence": True,
        "results_available": bool(result_list),
        "result_count": len(result_list),
        "latest_recorded_at": max(recorded_at) if recorded_at else None,
        "scores_available": False,
        "source_of_truth": ".github/workflows/ci.yml",
        "gating_count": gating,
        "non_gating_count": len(suites) - gating,
        "suites": suites,
    }
