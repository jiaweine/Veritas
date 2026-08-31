from __future__ import annotations

import json
from dataclasses import asdict, dataclass
from hashlib import sha256
from importlib.metadata import version
from io import BytesIO
from typing import Any


BBox = tuple[float, float, float, float]


def _bbox(values: Any) -> BBox:
    x0, y0, x1, y1 = values
    return (round(float(x0), 4), round(float(y0), 4), round(float(x1), 4), round(float(y1), 4))


def _clean_cell(value: object) -> str | None:
    if value is None:
        return None
    text = " ".join(str(value).replace("\u00a0", " ").split())
    return text or None


def _clean_rows(rows: object) -> tuple[tuple[str | None, ...], ...]:
    if not isinstance(rows, (list, tuple)):
        return ()
    cleaned: list[tuple[str | None, ...]] = []
    for row in rows:
        if not isinstance(row, (list, tuple)):
            continue
        normalized = tuple(_clean_cell(cell) for cell in row)
        if any(cell is not None for cell in normalized):
            cleaned.append(normalized)
    return tuple(cleaned)


@dataclass(frozen=True)
class PDFWord:
    page: int
    text: str
    bbox: BBox


@dataclass(frozen=True)
class PDFBlock:
    page: int
    text: str
    bbox: BBox


@dataclass(frozen=True)
class PDFTable:
    page: int
    table_index: int
    bbox: BBox
    rows: tuple[tuple[str | None, ...], ...]

    @property
    def text(self) -> str:
        return "\n".join(" | ".join(cell or "" for cell in row) for row in self.rows)


@dataclass(frozen=True)
class PDFPageSnapshot:
    page: int
    width: float
    height: float
    words: tuple[PDFWord, ...]
    blocks: tuple[PDFBlock, ...]
    tables: tuple[PDFTable, ...]


@dataclass(frozen=True)
class NativePDFSnapshot:
    artifact_id: str
    artifact_sha256: str
    parser_id: str
    parser_family: str
    parser_version: str
    pages: tuple[PDFPageSnapshot, ...]
    warnings: tuple[str, ...] = ()

    def sha256(self) -> str:
        payload = asdict(self)
        raw = json.dumps(payload, ensure_ascii=False, sort_keys=True, separators=(",", ":")).encode("utf-8")
        return sha256(raw).hexdigest()

    @property
    def tables(self) -> tuple[PDFTable, ...]:
        return tuple(table for page in self.pages for table in page.tables)

    @property
    def words(self) -> tuple[PDFWord, ...]:
        return tuple(word for page in self.pages for word in page.words)


class PyMuPDFNativeParser:
    parser_id = "pymupdf_native"
    parser_family = "mupdf_native"

    @property
    def parser_version(self) -> str:
        return version("PyMuPDF")

    def parse_bytes(self, pdf_bytes: bytes, *, artifact_id: str = "paper") -> NativePDFSnapshot:
        if not pdf_bytes.startswith(b"%PDF"):
            raise ValueError("input does not appear to be a PDF")
        import pymupdf

        artifact_hash = sha256(pdf_bytes).hexdigest()
        pages: list[PDFPageSnapshot] = []
        warnings: list[str] = []
        doc = pymupdf.open(stream=pdf_bytes, filetype="pdf")
        try:
            for page_index, page in enumerate(doc, start=1):
                words = tuple(
                    PDFWord(page_index, str(item[4]), _bbox(item[:4]))
                    for item in page.get_text("words", sort=True)
                    if len(item) >= 5 and str(item[4]).strip()
                )
                blocks = tuple(
                    PDFBlock(page_index, str(item[4]).strip(), _bbox(item[:4]))
                    for item in page.get_text("blocks", sort=True)
                    if len(item) >= 5 and str(item[4]).strip()
                )
                tables: list[PDFTable] = []
                try:
                    finder = page.find_tables()
                    for table_index, table in enumerate(finder.tables, start=1):
                        rows = _clean_rows(table.extract())
                        if rows:
                            tables.append(
                                PDFTable(
                                    page=page_index,
                                    table_index=table_index,
                                    bbox=_bbox(table.bbox),
                                    rows=rows,
                                )
                            )
                except Exception as exc:  # table detection is non-critical to text extraction
                    warnings.append(f"page {page_index}: PyMuPDF table detection failed: {type(exc).__name__}")
                pages.append(
                    PDFPageSnapshot(
                        page=page_index,
                        width=float(page.rect.width),
                        height=float(page.rect.height),
                        words=words,
                        blocks=blocks,
                        tables=tuple(tables),
                    )
                )
        finally:
            doc.close()
        return NativePDFSnapshot(
            artifact_id=artifact_id,
            artifact_sha256=artifact_hash,
            parser_id=self.parser_id,
            parser_family=self.parser_family,
            parser_version=self.parser_version,
            pages=tuple(pages),
            warnings=tuple(warnings),
        )


class PDFPlumberNativeParser:
    parser_id = "pdfplumber_native"
    parser_family = "pdfminer_native"

    @property
    def parser_version(self) -> str:
        return version("pdfplumber")

    def parse_bytes(self, pdf_bytes: bytes, *, artifact_id: str = "paper") -> NativePDFSnapshot:
        if not pdf_bytes.startswith(b"%PDF"):
            raise ValueError("input does not appear to be a PDF")
        import pdfplumber

        artifact_hash = sha256(pdf_bytes).hexdigest()
        pages: list[PDFPageSnapshot] = []
        warnings: list[str] = []
        with pdfplumber.open(BytesIO(pdf_bytes), unicode_norm="NFC") as doc:
            for page_index, page in enumerate(doc.pages, start=1):
                raw_words = page.extract_words(use_text_flow=False, keep_blank_chars=False) or []
                words = tuple(
                    PDFWord(
                        page=page_index,
                        text=str(item.get("text", "")),
                        bbox=_bbox((item["x0"], item["top"], item["x1"], item["bottom"])),
                    )
                    for item in raw_words
                    if str(item.get("text", "")).strip()
                )
                page_text = (page.extract_text(layout=False) or "").strip()
                blocks = (
                    PDFBlock(page_index, page_text, (0.0, 0.0, float(page.width), float(page.height))),
                ) if page_text else ()
                tables: list[PDFTable] = []
                try:
                    for table_index, table in enumerate(page.find_tables(), start=1):
                        rows = _clean_rows(table.extract())
                        if rows:
                            tables.append(
                                PDFTable(
                                    page=page_index,
                                    table_index=table_index,
                                    bbox=_bbox(table.bbox),
                                    rows=rows,
                                )
                            )
                except Exception as exc:  # keep the usable text layer if table finding fails
                    warnings.append(f"page {page_index}: pdfplumber table detection failed: {type(exc).__name__}")
                pages.append(
                    PDFPageSnapshot(
                        page=page_index,
                        width=float(page.width),
                        height=float(page.height),
                        words=words,
                        blocks=blocks,
                        tables=tuple(tables),
                    )
                )
        return NativePDFSnapshot(
            artifact_id=artifact_id,
            artifact_sha256=artifact_hash,
            parser_id=self.parser_id,
            parser_family=self.parser_family,
            parser_version=self.parser_version,
            pages=tuple(pages),
            warnings=tuple(warnings),
        )


def parse_pdf_dual(pdf_bytes: bytes, *, artifact_id: str = "paper") -> tuple[NativePDFSnapshot, NativePDFSnapshot]:
    """Parse one machine-generated PDF through two independent native parser families."""
    left = PyMuPDFNativeParser().parse_bytes(pdf_bytes, artifact_id=artifact_id)
    right = PDFPlumberNativeParser().parse_bytes(pdf_bytes, artifact_id=artifact_id)
    if left.artifact_sha256 != right.artifact_sha256:
        raise RuntimeError("parser snapshots disagree on source artifact identity")
    return left, right
