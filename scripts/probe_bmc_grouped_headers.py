from __future__ import annotations

import json

from smoke_real_pdf import _cluster_page_lines, _download
from veritas.pdf_native import parse_pdf_dual

PDF_URL = "https://bmcpublichealth.biomedcentral.com/counter/pdf/10.1186/s12889-025-21990-3.pdf"
PAGES = (8, 9)


def main() -> None:
    pdf = _download(PDF_URL)
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
    print(
        json.dumps(
            {
                "artifact_bytes": len(pdf),
                "pages": PAGES,
                "probes": probes,
            },
            ensure_ascii=False,
            sort_keys=True,
        )
    )


if __name__ == "__main__":
    main()
