from __future__ import annotations

import os
from importlib.util import find_spec

from veritas.pdf_native import NativePDFSnapshot, parse_pdf_dual


def parser_stack_capability() -> dict[str, object]:
    requested = os.environ.get("VERITAS_PDF_THIRD_PARSER", "").strip().casefold()
    return {
        "baseline": ["pymupdf_native", "pdfplumber_native"],
        "baseline_families": ["mupdf_native", "pdfminer_native"],
        "third_parser": requested or None,
        "third_parser_enabled": bool(requested),
        "docling_available": find_spec("docling") is not None,
        "consensus_policy_changed": False,
    }


def parse_product_pdf(
    pdf_bytes: bytes,
    *,
    artifact_id: str,
) -> tuple[NativePDFSnapshot, ...]:
    """Parse with the locked dual-parser baseline plus an explicit optional adapter.

    The two existing parser families always run and remain sufficient for the
    current consensus rule. A third parser is observational until benchmark data
    justifies changing promotion policy; enabling it must never remove a baseline
    parser from the quorum.
    """

    snapshots: list[NativePDFSnapshot] = list(parse_pdf_dual(pdf_bytes, artifact_id=artifact_id))
    requested = os.environ.get("VERITAS_PDF_THIRD_PARSER", "").strip().casefold()
    if not requested:
        return tuple(snapshots)
    if requested != "docling":
        raise ValueError(f"unsupported VERITAS_PDF_THIRD_PARSER: {requested}")

    from veritas.docling_native import DoclingNativeParser

    optional = DoclingNativeParser().parse_bytes(pdf_bytes, artifact_id=artifact_id)
    if optional.artifact_sha256 != snapshots[0].artifact_sha256:
        raise RuntimeError("optional parser snapshot disagrees on source artifact identity")
    existing_families = {snapshot.parser_family for snapshot in snapshots}
    if optional.parser_family in existing_families:
        raise RuntimeError("optional parser must contribute an independent parser family")
    snapshots.append(optional)
    return tuple(snapshots)
