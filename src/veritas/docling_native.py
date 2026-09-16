from __future__ import annotations

from hashlib import sha256
from importlib.metadata import PackageNotFoundError, version
from io import BytesIO
from typing import Any

from .pdf_native import NativePDFSnapshot, PDFBlock, PDFPageSnapshot, PDFTable


def _clean_cell(value: object) -> str | None:
    if value is None:
        return None
    text = " ".join(str(value).replace("\u00a0", " ").split())
    return text or None


def _distribution_version() -> str:
    for name in ("docling-slim", "docling"):
        try:
            return version(name)
        except PackageNotFoundError:
            continue
    return "unknown"


def _top_left_bbox(bbox: Any, page_height: float) -> tuple[float, float, float, float]:
    converted = bbox.to_top_left_origin(page_height=page_height)
    return tuple(round(float(value), 4) for value in converted.as_tuple())  # type: ignore[return-value]


def _table_rows(table: Any) -> tuple[tuple[str | None, ...], ...]:
    grid = getattr(getattr(table, "data", None), "grid", None) or []
    rows: list[tuple[str | None, ...]] = []
    for row in grid:
        cells = tuple(_clean_cell(getattr(cell, "text", cell)) for cell in row)
        if any(cell is not None for cell in cells):
            rows.append(cells)
    return tuple(rows)


class DoclingNativeParser:
    """Optional Docling adapter producing Veritas' immutable native snapshot shape.

    This adapter is deliberately not part of the default parser quorum. Operators
    opt into it with ``VERITAS_PDF_THIRD_PARSER=docling`` after installing the
    ``docling`` Veritas extra. It maps Docling's structured table/provenance model
    into the same snapshot contract consumed by Veritas' existing extraction gate.
    """

    parser_id = "docling_native"
    parser_family = "docling_layout"

    @property
    def parser_version(self) -> str:
        return _distribution_version()

    def parse_bytes(self, pdf_bytes: bytes, *, artifact_id: str = "paper") -> NativePDFSnapshot:
        if not pdf_bytes.startswith(b"%PDF"):
            raise ValueError("input does not appear to be a PDF")

        try:
            from docling.datamodel.base_models import DocumentStream, InputFormat
            from docling.datamodel.pipeline_options import PdfPipelineOptions
            from docling.document_converter import DocumentConverter, PdfFormatOption
        except ImportError as exc:
            raise RuntimeError(
                'Docling parser requested but unavailable; install Veritas with the "docling" extra'
            ) from exc

        pipeline_options = PdfPipelineOptions()
        pipeline_options.do_ocr = False
        pipeline_options.do_table_structure = True
        converter = DocumentConverter(
            allowed_formats=[InputFormat.PDF],
            format_options={
                InputFormat.PDF: PdfFormatOption(pipeline_options=pipeline_options),
            },
        )
        source = DocumentStream(name="paper.pdf", stream=BytesIO(pdf_bytes))
        result = converter.convert(
            source,
            max_file_size=len(pdf_bytes) + 1,
        )
        document = result.document

        page_sizes: dict[int, tuple[float, float]] = {}
        for raw_page_no, page in document.pages.items():
            page_no = int(raw_page_no)
            page_sizes[page_no] = (float(page.size.width), float(page.size.height))

        page_tables: dict[int, list[PDFTable]] = {page_no: [] for page_no in page_sizes}
        warnings: list[str] = []
        for table_index, table in enumerate(document.tables, start=1):
            provenance = list(getattr(table, "prov", ()) or ())
            if not provenance:
                warnings.append(f"table {table_index}: missing provenance")
                continue
            prov = provenance[0]
            page_no = int(prov.page_no)
            size = page_sizes.get(page_no)
            if size is None:
                warnings.append(f"table {table_index}: missing page {page_no}")
                continue
            rows = _table_rows(table)
            if not rows:
                warnings.append(f"table {table_index}: empty table grid")
                continue
            try:
                caption = _clean_cell(table.caption_text(document))
            except (AttributeError, RuntimeError, TypeError, ValueError):
                caption = None
            page_tables.setdefault(page_no, []).append(
                PDFTable(
                    page=page_no,
                    table_index=table_index,
                    bbox=_top_left_bbox(prov.bbox, size[1]),
                    rows=rows,
                    caption=caption,
                )
            )

        page_blocks: dict[int, list[PDFBlock]] = {page_no: [] for page_no in page_sizes}
        for item in getattr(document, "texts", ()):
            text = _clean_cell(getattr(item, "text", None))
            if not text:
                continue
            provenance = list(getattr(item, "prov", ()) or ())
            if not provenance:
                continue
            prov = provenance[0]
            page_no = int(prov.page_no)
            size = page_sizes.get(page_no)
            if size is None:
                continue
            page_blocks.setdefault(page_no, []).append(
                PDFBlock(
                    page=page_no,
                    text=text,
                    bbox=_top_left_bbox(prov.bbox, size[1]),
                )
            )

        pages = tuple(
            PDFPageSnapshot(
                page=page_no,
                width=size[0],
                height=size[1],
                words=(),
                blocks=tuple(page_blocks.get(page_no, ())),
                tables=tuple(page_tables.get(page_no, ())),
            )
            for page_no, size in sorted(page_sizes.items())
        )
        if not pages:
            raise RuntimeError("Docling returned no PDF pages")

        return NativePDFSnapshot(
            artifact_id=artifact_id,
            artifact_sha256=sha256(pdf_bytes).hexdigest(),
            parser_id=self.parser_id,
            parser_family=self.parser_family,
            parser_version=self.parser_version,
            pages=pages,
            warnings=tuple(warnings),
        )
