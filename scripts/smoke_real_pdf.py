from __future__ import annotations

import json
import urllib.request

from veritas.pdf_native import parse_pdf_dual
from veritas.pdf_regression import extract_regression_table

CASES = (
    {
        "case_id": "plosone-0318226-table2-age",
        "doi": "10.1371/journal.pone.0318226",
        "pdf_url": "https://journals.plos.org/plosone/article/file?id=10.1371%2Fjournal.pone.0318226&type=printable",
        "variable": "Age (years)",
        "expected_page": 5,
        "expected": {
            "beta": "-0.016",
            "se": "0.004",
            "t_stat": "-3.650",
            "p_value": "<0.001",
        },
        "license": "CC BY",
        "adjudication_note": "Values manually checked against PLOS ONE Table 2; this is extraction gold, not a clean-paper label.",
    },
    {
        "case_id": "plosone-0300960-table2-image-neutral",
        "doi": "10.1371/journal.pone.0300960",
        "pdf_url": "https://journals.plos.org/plosone/article/file?id=10.1371%2Fjournal.pone.0300960&type=printable",
        "variable": "Image: neutral",
        "expected_page": 10,
        "expected": {
            "beta": "0.104",
            "se": "0.038",
            "t_stat": "2.735",
            "p_value": "0.006",
        },
        "license": "CC BY",
        "adjudication_note": "Values manually checked against PLOS ONE Table 2 (linear mixed regression); extraction gold only.",
    },
)


def _download(url: str) -> bytes:
    request = urllib.request.Request(
        url,
        headers={"User-Agent": "Veritas real-PDF smoke benchmark/0.9 (+research integrity audit)"},
    )
    with urllib.request.urlopen(request, timeout=30) as response:
        payload = response.read()
    if not payload.startswith(b"%PDF"):
        raise RuntimeError("download did not return a PDF")
    return payload


def main() -> None:
    results: list[dict[str, object]] = []
    failures: list[str] = []
    for case in CASES:
        case_id = str(case["case_id"])
        try:
            pdf = _download(str(case["pdf_url"]))
            snapshots = parse_pdf_dual(pdf, artifact_id=case_id)
            bundle = extract_regression_table(snapshots, variable_label=str(case["variable"]))
            field_results: dict[str, object] = {}
            for field, expected in dict(case["expected"]).items():
                candidates = bundle.field_candidates[field]
                normalized = [candidate.normalized_value for candidate in candidates]
                field_results[field] = {
                    "expected": expected,
                    "normalized": normalized,
                    "raw": [candidate.raw for candidate in candidates],
                    "source_pages": [candidate.source.page for candidate in candidates],
                    "dual_parser": len(candidates) == 2,
                    "exact_gold_match": len(candidates) == 2 and all(value == expected for value in normalized),
                }
            page_ok = bundle.source.page == case["expected_page"]
            fields_ok = all(bool(item["exact_gold_match"]) for item in field_results.values())
            passed = fields_ok and page_ok
            if not passed:
                failures.append(case_id)
            results.append(
                {
                    "case_id": case_id,
                    "doi": case["doi"],
                    "passed": passed,
                    "source_page": bundle.source.page,
                    "expected_page": case["expected_page"],
                    "page_ok": page_ok,
                    "fields": field_results,
                    "parser_versions": bundle.parser_versions,
                    "license": case["license"],
                    "adjudication_note": case["adjudication_note"],
                }
            )
        except Exception as exc:  # smoke harness must surface network/parser failures as data
            failures.append(case_id)
            results.append(
                {
                    "case_id": case_id,
                    "doi": case["doi"],
                    "passed": False,
                    "error_type": type(exc).__name__,
                    "error": str(exc),
                }
            )

    report = {
        "scope": "real_open_access_extraction_smoke_not_production_certification",
        "cases": len(CASES),
        "passed": len(CASES) - len(failures),
        "failed_case_ids": failures,
        "results": results,
    }
    print(json.dumps(report, ensure_ascii=False, sort_keys=True))
    if failures:
        raise SystemExit("one or more real-PDF smoke cases failed")


if __name__ == "__main__":
    main()
