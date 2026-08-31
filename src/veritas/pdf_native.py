from __future__ import annotations

import json
import re
from collections.abc import Sequence
from dataclasses import asdict, dataclass
from hashlib import sha256
from importlib.metadata import version
from io import BytesIO

BBox = tuple[float, float, float, float]
_TABLE_CAPTION_RE = re.compile(r"\btable\s*(?P<label>(?:[a-z]\s*)?\d+|[ivxlcdm]+)\b", re.IGNORECASE)


def _bbox(values: Sequence[object]) -> BBox:
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


def canonical_table_label(value: str | None) -> str | None:
    """Return a stable publication-visible table identity such as ``table2`` or ``tablea1``."""
    if value is None:
        return None
    match = _TABLE_CAPTION_RE.search(value)
    if match is None:
        return None
    label = re.sub(r"\s+", "", match.group("label").casefold())
    return f"table{label}"


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
    caption: str | None = None

    @property
    def text(self) -> str:
        return "\n".join(" | ".join(cell or "" for cell in row) for row in self.rows)

    @property
    def publication_label(self) -> str | None:
        return canonical_table_label(self.caption)


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


def _word_center_y(word: PDFWord) -> float:
    return (word.bbox[1] + word.bbox[3]) / 2.0


def _word_lines(words: tuple[PDFWord, ...], *, y_tolerance: float = 3.5) -> tuple[tuple[PDFWord, ...], ...]:
    ordered = sorted(words, key=lambda item: (_word_center_y(item), item.bbox[0]))
    lines: list[list[PDFWord]] = []
    means: list[float] = []
    for word in ordered:
        y = _word_center_y(word)
        if lines and abs(y - means[-1]) <= y_tolerance:
            lines[-1].append(word)
            means[-1] = sum(_word_center_y(item) for item in lines[-1]) / len(lines[-1])
        else:
            lines.append([word])
            means.append(y)
    return tuple(tuple(sorted(line, key=lambda item: item.bbox[0])) for line in lines)


def _nearest_table_caption(
    words: tuple[PDFWord, ...],
    table_bbox: BBox,
    *,
    max_vertical_gap: float = 140.0,
) -> str | None:
    """Find the closest publication table caption above a detected table region on the same page."""
    table_top = table_bbox[1]
    candidates: list[tuple[float, str]] = []
    for line in _word_lines(words):
        line_y = sum(_word_center_y(word) for word in line) / len(line)
        if line_y > table_top + 6.0:
            continue
        if table_top - line_y > max_vertical_gap:
            continue
        text = " ".join(word.text for word in line).strip()
        if canonical_table_label(text) is not None:
            candidates.append((line_y, text))
    if not candidates:
        return None
    return max(candidates, key=lambda item: item[0])[1]


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
                            table_bbox = _bbox(table.bbox)
                            tables.append(
                                PDFTable(
                                    page=page_index,
                                    table_index=table_index,
                                    bbox=table_bbox,
                                    rows=rows,
                                    caption=_nearest_table_caption(words, table_bbox),
                                )
                            )
                except (RuntimeError, TypeError, ValueError) as exc:
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
                            table_bbox = _bbox(table.bbox)
                            tables.append(
                                PDFTable(
                                    page=page_index,
                                    table_index=table_index,
                                    bbox=table_bbox,
                                    rows=rows,
                                    caption=_nearest_table_caption(words, table_bbox),
                                )
                            )
                except (RuntimeError, TypeError, ValueError) as exc:
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
