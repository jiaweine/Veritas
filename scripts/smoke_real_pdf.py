from __future__ import annotations

import json
import urllib.request

from veritas.pdf_native import NativePDFSnapshot, parse_pdf_dual
from veritas.pdf_regression import RegressionLocator, extract_regression_table

CASES = (
    {
        "case_id": "plosone-0318226-table2-age",
        "doi": "10.1371/journal.pone.0318226",
        "pdf_url": "https://journals.plos.org/plosone/article/file?id=10.1371%2Fjournal.pone.0318226&type=printable",
        "variable": "Age (years)",
        "table_label": "Table 2",
        # 1-based physical PDF page, matching NativePDFSnapshot.page semantics.
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
        "table_label": "Table 2",
        # Table 1 is on PDF page 10; Table 2 starts on the following physical page (11 / 20).
        "expected_page": 11,
        "expected": {
            "beta": "0.104",
            "se": "0.038",
            "t_stat": "2.735",
            "p_value": "0.006",
        },
        "license": "CC BY",
        "adjudication_note": "Values manually checked against PLOS ONE Table 2 (linear mixed regression); extraction gold only.",
    },
    {
        "case_id": "plosone-0337826-table2-edtr",
        "doi": "10.1371/journal.pone.0337826",
        "pdf_url": "https://journals.plos.org/plosone/article/file?id=10.1371%2Fjournal.pone.0337826&type=printable",
        "variable": "EDTR",
        "table_label": "Table 2",
        # Table 2 is on the physical PDF page carrying the journal footer 10 / 16.
        "expected_page": 10,
        "expected": {
            "beta": "0.3596",
            "se": "0.1386",
            "t_stat": "2.5938",
            "p_value": "0.0095",
        },
        "license": "CC BY",
        "adjudication_note": "Values manually checked against PLOS ONE Table 2 (ordinal logistic regression); extraction gold only.",
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


def _center_y(word: object) -> float:
    bbox = getattr(word, "bbox")
    return (bbox[1] + bbox[3]) / 2.0


def _cluster_page_lines(snapshot: NativePDFSnapshot, page_number: int) -> list[dict[str, object]]:
    page = next(page for page in snapshot.pages if page.page == page_number)
    ordered = sorted(page.words, key=lambda item: (_center_y(item), item.bbox[0]))
    grouped: list[list[object]] = []
    means: list[float] = []
    for word in ordered:
        y = _center_y(word)
        if grouped and abs(y - means[-1]) <= 3.0:
            grouped[-1].append(word)
            means[-1] = sum(_center_y(item) for item in grouped[-1]) / len(grouped[-1])
        else:
            grouped.append([word])
            means.append(y)
    lines: list[dict[str, object]] = []
    for words, y in zip(grouped, means, strict=True):
        words.sort(key=lambda item: item.bbox[0])
        lines.append(
            {
                "y": round(y, 2),
                "text": " ".join(str(item.text) for item in words),
                "words": [
                    {
                        "text": str(item.text),
                        "x0": round(item.bbox[0], 2),
                        "x1": round(item.bbox[2], 2),
                    }
                    for item in words
                ],
            }
        )
    return lines


def _failure_probe(
    snapshots: tuple[NativePDFSnapshot, ...],
    *,
    page_number: int,
    variable: str,
    table_label: str,
) -> list[dict[str, object]]:
    probes: list[dict[str, object]] = []
    variable_casefold = variable.casefold()
    table_casefold = table_label.casefold()
    header_terms = ("independent", "variable", "beta", "β", "se", "z-value", "z value", "p-value", "p value")
    for snapshot in snapshots:
        lines = _cluster_page_lines(snapshot, page_number)
        interesting_indices = {
            index
            for index, line in enumerate(lines)
            if variable_casefold in str(line["text"]).casefold()
            or table_casefold in str(line["text"]).casefold()
            or sum(term in str(line["text"]).casefold() for term in header_terms) >= 3
        }
        expanded = sorted(
            {
                neighbor
                for index in interesting_indices
                for neighbor in range(max(0, index - 2), min(len(lines), index + 3))
            }
        )
        page = next(page for page in snapshot.pages if page.page == page_number)
        probes.append(
            {
                "parser_id": snapshot.parser_id,
                "parser_family": snapshot.parser_family,
                "page": page_number,
                "interesting_lines": [lines[index] for index in expanded],
                "native_tables": [
                    {
                        "table_index": table.table_index,
                        "caption": table.caption,
                        "publication_label": table.publication_label,
                        "bbox": table.bbox,
                        "rows_preview": table.rows[:4],
                    }
                    for table in page.tables
                ],
            }
        )
    return probes


def main() -> None:
    results: list[dict[str, object]] = []
    failures: list[str] = []
    for case in CASES:
        case_id = str(case["case_id"])
        try:
            pdf = _download(str(case["pdf_url"]))
            snapshots = parse_pdf_dual(pdf, artifact_id=case_id)
            locator = RegressionLocator(
                table_label=str(case["table_label"]),
                expected_page=int(case["expected_page"]),
            )
            bundle = extract_regression_table(
                snapshots,
                variable_label=str(case["variable"]),
                locator=locator,
            )
            field_results: dict[str, object] = {}
            for field, expected in dict(case["expected"]).items():
                candidates = bundle.field_candidates[field]
                normalized = [candidate.normalized_value for candidate in candidates]
                field_results[field] = {
                    "expected": expected,
                    "normalized": normalized,
                    "raw": [candidate.raw for candidate in candidates],
                    "source_pages": [candidate.source.page for candidate in candidates],
                    "source_tables": [candidate.source.table for candidate in candidates],
                    "dual_parser": len(candidates) == 2,
                    "exact_gold_match": len(candidates) == 2 and all(value == expected for value in normalized),
                }
            page_ok = bundle.source.page == case["expected_page"]
            fields_ok = all(bool(item["exact_gold_match"]) for item in field_results.values())
            passed = fields_ok and page_ok and not bundle.ambiguities
            if not passed:
                failures.append(case_id)
            result: dict[str, object] = {
                "case_id": case_id,
                "doi": case["doi"],
                "passed": passed,
                "table_label": case["table_label"],
                "source_page": bundle.source.page,
                "expected_page": case["expected_page"],
                "page_ok": page_ok,
                "fields": field_results,
                "ambiguities": bundle.ambiguities,
                "parser_versions": bundle.parser_versions,
                "license": case["license"],
                "adjudication_note": case["adjudication_note"],
            }
            if not passed:
                result["failure_probe"] = _failure_probe(
                    snapshots,
                    page_number=int(case["expected_page"]),
                    variable=str(case["variable"]),
                    table_label=str(case["table_label"]),
                )
            results.append(result)
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
