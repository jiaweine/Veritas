from __future__ import annotations

from collections.abc import Iterable, Mapping
from typing import Final

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


def benchmark_definition(benchmark_id: str) -> dict[str, object]:
    """Return one locked product-visible benchmark definition."""

    for item in _BENCHMARKS:
        if item["benchmark_id"] == benchmark_id:
            return dict(item)
    raise ValueError(f"unknown benchmark id: {benchmark_id}")


def benchmark_catalog(
    results: Iterable[Mapping[str, object]] | None = None,
) -> dict[str, object]:
    """Return the CI benchmark inventory plus persisted result availability.

    Result persistence stores versioned execution envelopes. It deliberately does
    not normalize heterogeneous benchmark metrics into a synthetic score or trend.
    """

    suites = [dict(item) for item in _BENCHMARKS]
    gating = sum(bool(item["gating"]) for item in suites)
    persisted = [dict(item) for item in (results or ())]
    persisted.sort(key=lambda item: str(item.get("finished_at") or ""), reverse=True)

    latest_results: dict[str, dict[str, object]] = {}
    for result in persisted:
        benchmark_id = str(result.get("benchmark_id") or "")
        if benchmark_id and benchmark_id not in latest_results:
            latest_results[benchmark_id] = result

    return {
        "schema_version": "2",
        "result_schema_version": "1",
        "result_persistence": True,
        "results_available": bool(persisted),
        "result_count": len(persisted),
        "scores_available": False,
        "source_of_truth": ".github/workflows/ci.yml",
        "gating_count": gating,
        "non_gating_count": len(suites) - gating,
        "latest_results": latest_results,
        "suites": suites,
    }
