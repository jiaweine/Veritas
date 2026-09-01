from __future__ import annotations

import json

from smoke_real_pdf import _cluster_page_lines, _download
from veritas.pdf_native import parse_pdf_dual
from veritas.pdf_regression import RegressionLocator, extract_regression_table

PDF_URL = "https://www.frontiersin.org/journals/public-health/articles/10.3389/fpubh.2025.1520668/pdf"
VARIABLE = "F01 (Group male vs. female)"
PAGE = 7
TABLE = "Table 2"


def main() -> None:
    pdf = _download(PDF_URL)
    snapshots = parse_pdf_dual(pdf, artifact_id="frontiers-1520668-probe")
    bundle = extract_regression_table(
        snapshots,
        variable_label=VARIABLE,
        locator=RegressionLocator(table_label=TABLE, expected_page=PAGE),
    )
    probes: list[dict[str, object]] = []
    for snapshot in snapshots:
        page = next(item for item in snapshot.pages if item.page == PAGE)
        lines = _cluster_page_lines(snapshot, PAGE)
        interesting = [
            line
            for line in lines
            if "coefficient" in str(line["text"]).casefold()
            or "f01" in str(line["text"]).casefold()
            or "table 2" in str(line["text"]).casefold()
        ]
        probes.append(
            {
                "parser_id": snapshot.parser_id,
                "parser_family": snapshot.parser_family,
                "page_native_tables": [
                    {
                        "table_index": table.table_index,
                        "caption": table.caption,
                        "publication_label": table.publication_label,
                        "bbox": table.bbox,
                        "rows_preview": table.rows[:8],
                    }
                    for table in page.tables
                ],
                "interesting_lines": interesting,
            }
        )
    report = {
        "artifact_bytes": len(pdf),
        "page": PAGE,
        "table": TABLE,
        "variable": VARIABLE,
        "field_candidates": {
            key: [
                {
                    "parser_id": candidate.parser_id,
                    "raw": candidate.raw,
                    "normalized": candidate.normalized_value,
                    "source_table": candidate.source.table,
                }
                for candidate in candidates
            ]
            for key, candidates in bundle.field_candidates.items()
        },
        "ambiguities": bundle.ambiguities,
        "probes": probes,
    }
    print(json.dumps(report, ensure_ascii=False, sort_keys=True))


if __name__ == "__main__":
    main()
