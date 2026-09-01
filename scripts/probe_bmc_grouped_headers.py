from __future__ import annotations

import json
import urllib.error

from smoke_real_pdf import _cluster_page_lines, _download
from veritas.pdf_grouped_regression import GroupedRegressionLocator, extract_grouped_regression_table
from veritas.pdf_native import parse_pdf_dual

DOI = "10.1186/s12889-025-21990-3"
PDF_URL = "https://link.springer.com/content/pdf/10.1186/s12889-025-21990-3.pdf"
PAGES = (8, 9)
TARGET_PAGE = 8
TARGET_VARIABLE = "Age"
TARGET_GROUP = "Multivariable regression analysis"


def _network_unverified(exc: BaseException) -> None:
    print(
        json.dumps(
            {
                "doi": DOI,
                "network_retrieval_verified": False,
                "parser_executed": False,
                "pdf_url": PDF_URL,
                "production_authorized": False,
                "reason": str(exc),
                "seed_promotion_authorized": False,
                "status": "network_unverified",
            },
            ensure_ascii=False,
            sort_keys=True,
        )
    )


def main() -> None:
    try:
        pdf = _download(PDF_URL)
    except (urllib.error.URLError, TimeoutError, RuntimeError) as exc:
        # Publisher/CDN behavior from hosted CI is an availability fact, not an extraction failure.
        # Emit a machine-readable state and exit successfully so a green step means only that the
        # observability probe ran. Parser/extractor exceptions after verified PDF retrieval still fail.
        _network_unverified(exc)
        return

    snapshots = parse_pdf_dual(pdf, artifact_id="bmc-21990-3-probe")
    probes: list[dict[str, object]] = []
    for snapshot in snapshots:
        page_probes: list[dict[str, object]] = []
        for page_number in PAGES:
            page = next(item for item in snapshot.pages if item.page == page_number)
            lines = _cluster_page_lines(snapshot, page_number)
            interesting = [
                line
                for line in lines
                if any(
                    needle in str(line["text"]).casefold()
                    for needle in (
                        "bivariable",
                        "multivariable",
                        "variables",
                        "regression analysis",
                        "table 2",
                        "table 2 continued",
                    )
                )
            ]
            page_probes.append(
                {
                    "page": page_number,
                    "native_tables": [
                        {
                            "table_index": table.table_index,
                            "caption": table.caption,
                            "publication_label": table.publication_label,
                            "bbox": table.bbox,
                            "rows_preview": table.rows[:12],
                        }
                        for table in page.tables
                    ],
                    "interesting_lines": interesting,
                }
            )
        probes.append(
            {
                "parser_id": snapshot.parser_id,
                "parser_family": snapshot.parser_family,
                "pages": page_probes,
            }
        )

    bundle = extract_grouped_regression_table(
        snapshots,
        variable_label=TARGET_VARIABLE,
        locator=GroupedRegressionLocator(
            table_label="Table 2",
            model_group_label=TARGET_GROUP,
            expected_page=TARGET_PAGE,
        ),
    )
    field_candidates = {
        key: [
            {
                "normalized": candidate.normalized_value,
                "parser_family": candidate.parser_family,
                "parser_id": candidate.parser_id,
                "raw": candidate.raw,
                "source_page": candidate.source.page,
                "source_table": candidate.source.table,
            }
            for candidate in candidates
        ]
        for key, candidates in bundle.field_candidates.items()
    }
    print(
        json.dumps(
            {
                "ambiguities": bundle.ambiguities,
                "artifact_bytes": len(pdf),
                "doi": DOI,
                "field_candidates": field_candidates,
                "network_retrieval_verified": True,
                "pages": PAGES,
                "parser_executed": True,
                "probes": probes,
                "production_authorized": False,
                "seed_promotion_authorized": False,
                "status": "parsed_observability_only",
                "target": {
                    "expected_page": TARGET_PAGE,
                    "model_group_label": TARGET_GROUP,
                    "table_label": "Table 2",
                    "variable": TARGET_VARIABLE,
                },
            },
            ensure_ascii=False,
            sort_keys=True,
        )
    )


if __name__ == "__main__":
    main()
