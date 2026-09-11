from __future__ import annotations

import json
import urllib.error
import urllib.parse
import urllib.request
import xml.etree.ElementTree as ET

from smoke_real_pdf import _cluster_page_lines, _download
from veritas.pdf_grouped_regression import GroupedRegressionLocator, extract_grouped_regression_table
from veritas.pdf_native import parse_pdf_dual

DOI = "10.1186/s12889-025-21990-3"
PMCID = "PMC11863760"
PMC_BUCKET = "https://pmc-oa-opendata.s3.amazonaws.com"
PUBLISHER_PDF_URL = "https://link.springer.com/content/pdf/10.1186/s12889-025-21990-3.pdf"
PAGES = (8, 9)
TARGET_PAGE = 8
TARGET_VARIABLE = "Age"
TARGET_GROUP = "Multivariable regression analysis"
EXPECTED_FIELDS = {
    "beta": "0.02",
    "se": "0.01",
    "t_stat": "1.55",
    "p_value": "0.123",
}
EXPECTED_PARSER_FAMILIES = {"mupdf_native", "pdfminer_native"}


def _discover_pmc_pdf_url() -> str | None:
    query = urllib.parse.urlencode({"list-type": "2", "prefix": f"{PMCID}."})
    listing_url = f"{PMC_BUCKET}/?{query}"
    request = urllib.request.Request(
        listing_url,
        headers={"User-Agent": "Veritas PMC Cloud availability probe/0.11 (+research integrity audit)"},
    )
    with urllib.request.urlopen(request, timeout=30) as response:
        payload = response.read()
    root = ET.fromstring(payload)
    pdf_keys = sorted(
        element.text
        for element in root.findall(".//{*}Key")
        if element.text is not None
        and element.text.startswith(f"{PMCID}.")
        and element.text.casefold().endswith(".pdf")
    )
    if not pdf_keys:
        return None
    if len(pdf_keys) > 1:
        # Prefer the numerically latest article version rather than silently taking list order.
        def version_number(key: str) -> int:
            version_token = key.split("/", 1)[0].removeprefix(f"{PMCID}.")
            return int(version_token) if version_token.isdigit() else -1

        pdf_keys.sort(key=version_number, reverse=True)
    return f"{PMC_BUCKET}/{urllib.parse.quote(pdf_keys[0], safe='/')}"


def _retrieve_pdf() -> tuple[bytes, str, tuple[dict[str, str], ...]]:
    attempts: list[dict[str, str]] = []
    try:
        pmc_pdf_url = _discover_pmc_pdf_url()
    except (urllib.error.URLError, TimeoutError, ET.ParseError, ValueError) as exc:
        attempts.append({"source": "pmc_cloud_discovery", "status": "failed", "reason": str(exc)})
        pmc_pdf_url = None
    if pmc_pdf_url is not None:
        try:
            return _download(pmc_pdf_url), pmc_pdf_url, tuple(attempts)
        except (urllib.error.URLError, TimeoutError, RuntimeError) as exc:
            attempts.append({"source": "pmc_cloud_pdf", "status": "failed", "reason": str(exc)})
    else:
        attempts.append(
            {
                "source": "pmc_cloud_pdf",
                "status": "not_listed",
                "reason": f"no PDF object listed for prefix {PMCID}.",
            }
        )

    try:
        return _download(PUBLISHER_PDF_URL), PUBLISHER_PDF_URL, tuple(attempts)
    except (urllib.error.URLError, TimeoutError, RuntimeError) as exc:
        attempts.append({"source": "publisher_pdf", "status": "failed", "reason": str(exc)})
        raise RuntimeError(json.dumps(attempts, sort_keys=True)) from exc


def _network_unverified(exc: BaseException) -> None:
    print(
        json.dumps(
            {
                "adjudication_status": "pending",
                "doi": DOI,
                "network_retrieval_verified": False,
                "parser_executed": False,
                "pmcid": PMCID,
                "production_authorized": False,
                "reason": str(exc),
                "seed_promotion_authorized": False,
                "status": "network_unverified",
            },
            ensure_ascii=False,
            sort_keys=True,
        )
    )


def _interesting_lines(lines: list[dict[str, object]]) -> list[dict[str, object]]:
    needles = (
        "bivariable",
        "multivariable",
        "variables",
        "regression analysis",
        "table 2",
        "table 2 continued",
        "mean (sd)",
        "p-value",
        "age",
    )
    return [
        line
        for line in lines
        if any(needle in str(line["text"]).casefold() for needle in needles)
    ]


def _assert_candidate_extraction(bundle) -> None:
    assert not bundle.ambiguities, bundle.ambiguities
    for field, expected in EXPECTED_FIELDS.items():
        candidates = bundle.field_candidates[field]
        assert len(candidates) == 2, (field, candidates)
        assert {candidate.parser_family for candidate in candidates} == EXPECTED_PARSER_FAMILIES, field
        assert {candidate.normalized_value for candidate in candidates} == {expected}, field
        assert {candidate.source.page for candidate in candidates} == {TARGET_PAGE}, field
        assert all(TARGET_GROUP in (candidate.source.table or "") for candidate in candidates), field
    assert not bundle.semantic_candidates["inference_distribution"]


def main() -> None:
    try:
        pdf, resolved_pdf_url, retrieval_attempts = _retrieve_pdf()
    except RuntimeError as exc:
        # Network/CDN availability is separate from extraction correctness. Emit a machine-readable
        # candidate state; parser/extractor exceptions after verified PDF retrieval still surface.
        _network_unverified(exc)
        return

    snapshots = parse_pdf_dual(pdf, artifact_id="bmc-21990-3-probe")
    probes: list[dict[str, object]] = []
    for snapshot in snapshots:
        page_probes: list[dict[str, object]] = []
        for page_number in PAGES:
            page = next(item for item in snapshot.pages if item.page == page_number)
            lines = _cluster_page_lines(snapshot, page_number)
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
                    "interesting_lines": _interesting_lines(lines),
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
    _assert_candidate_extraction(bundle)

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
                "adjudication_status": "pending_independent_human_review",
                "ambiguities": bundle.ambiguities,
                "artifact_bytes": len(pdf),
                "candidate_exact_extraction_verified": True,
                "doi": DOI,
                "expected_fields_source": "manual_candidate_check_not_locked_gold",
                "field_candidates": field_candidates,
                "network_retrieval_verified": True,
                "pages": PAGES,
                "parser_executed": True,
                "pmcid": PMCID,
                "probes": probes,
                "production_authorized": False,
                "resolved_pdf_url": resolved_pdf_url,
                "retrieval_attempts": retrieval_attempts,
                "seed_promotion_authorized": False,
                "status": "candidate_exact_extraction_unadjudicated",
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
