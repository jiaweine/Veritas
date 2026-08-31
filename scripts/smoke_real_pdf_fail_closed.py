from __future__ import annotations

import json

from smoke_real_pdf import CASES, SEED_MANIFEST_SHA256, _download
from veritas.pdf_native import parse_pdf_dual
from veritas.pdf_regression import RegressionLocator, extract_regression_table


def _has_any_fields(bundle: object) -> bool:
    fields = getattr(bundle, "field_candidates")
    return any(bool(candidates) for candidates in fields.values())


def main() -> None:
    by_id = {str(case["case_id"]): case for case in CASES}
    results: list[dict[str, object]] = []
    failures: list[str] = []

    # Real paper with the same row label in Table 1 and Table 2. Without display-item
    # identity, hard-audit extraction must fail closed rather than silently pick one.
    duplicate = by_id["plosone-0300960-table2-image-neutral"]
    duplicate_pdf = _download(str(duplicate["pdf_url"]))
    duplicate_snapshots = parse_pdf_dual(duplicate_pdf, artifact_id="real-negative-duplicate-display")
    ambiguous = extract_regression_table(
        duplicate_snapshots,
        variable_label=str(duplicate["variable"]),
    )
    ambiguous_ok = bool(ambiguous.ambiguities) and not _has_any_fields(ambiguous)
    results.append(
        {
            "control_id": "duplicate-display-item-without-locator",
            "passed": ambiguous_ok,
            "ambiguities": ambiguous.ambiguities,
            "field_candidate_counts": {
                key: len(value) for key, value in ambiguous.field_candidates.items()
            },
        }
    )
    if not ambiguous_ok:
        failures.append("duplicate-display-item-without-locator")

    # A correct publication label on the wrong physical page must not fall back to a nearby
    # table carrying the same row label.
    wrong_page = extract_regression_table(
        duplicate_snapshots,
        variable_label=str(duplicate["variable"]),
        locator=RegressionLocator(table_label="Table 2", expected_page=10),
    )
    wrong_page_ok = not wrong_page.ambiguities and not _has_any_fields(wrong_page)
    results.append(
        {
            "control_id": "correct-table-label-wrong-page",
            "passed": wrong_page_ok,
            "ambiguities": wrong_page.ambiguities,
            "field_candidate_counts": {
                key: len(value) for key, value in wrong_page.field_candidates.items()
            },
        }
    )
    if not wrong_page_ok:
        failures.append("correct-table-label-wrong-page")

    # On another real journal layout, an absent row inside the correctly located display item
    # must remain absent. This catches geometry routines that greedily bind nearby prose rows.
    absent_case = by_id["plosone-0318226-table2-age"]
    absent_pdf = _download(str(absent_case["pdf_url"]))
    absent_snapshots = parse_pdf_dual(absent_pdf, artifact_id="real-negative-absent-row")
    absent = extract_regression_table(
        absent_snapshots,
        variable_label="__veritas_absent_row_control__",
        locator=RegressionLocator(
            table_label=str(absent_case["table_label"]),
            expected_page=int(absent_case["expected_page"]),
        ),
    )
    absent_ok = not absent.ambiguities and not _has_any_fields(absent)
    results.append(
        {
            "control_id": "absent-row-correct-display-item",
            "passed": absent_ok,
            "ambiguities": absent.ambiguities,
            "field_candidate_counts": {
                key: len(value) for key, value in absent.field_candidates.items()
            },
        }
    )
    if not absent_ok:
        failures.append("absent-row-correct-display-item")

    report = {
        "scope": "real_open_access_fail_closed_controls_not_production_certification",
        "seed_manifest_sha256": SEED_MANIFEST_SHA256,
        "controls": len(results),
        "passed": len(results) - len(failures),
        "failed_control_ids": failures,
        "results": results,
    }
    print(json.dumps(report, ensure_ascii=False, sort_keys=True))
    if failures:
        raise SystemExit("one or more real-PDF fail-closed controls failed")


if __name__ == "__main__":
    main()
