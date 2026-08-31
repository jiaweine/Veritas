from __future__ import annotations

import re
from collections.abc import Callable
from dataclasses import dataclass

from .pdf_native import NativePDFSnapshot, PDFTable, PDFWord, canonical_table_label

_TABLE_CAPTION_RE = re.compile(r"\btable\s*(?:[a-z]?\d+|[ivxlcdm]+)?\b", re.IGNORECASE)


@dataclass(frozen=True)
class _HeaderAnchor:
    role: str
    text: str
    x0: float


def _center_y(word: PDFWord) -> float:
    return (word.bbox[1] + word.bbox[3]) / 2.0


def _center_x(word: PDFWord) -> float:
    return (word.bbox[0] + word.bbox[2]) / 2.0


def _line_y(line: tuple[PDFWord, ...]) -> float:
    return sum(_center_y(word) for word in line) / len(line)


def _line_text(line: tuple[PDFWord, ...]) -> str:
    return " ".join(word.text for word in line).strip()


def _cluster_lines(words: tuple[PDFWord, ...], *, y_tolerance: float = 3.0) -> tuple[tuple[PDFWord, ...], ...]:
    if not words:
        return ()
    ordered = sorted(words, key=lambda item: (_center_y(item), item.bbox[0]))
    lines: list[list[PDFWord]] = []
    means: list[float] = []
    for word in ordered:
        y = _center_y(word)
        if lines and abs(y - means[-1]) <= y_tolerance:
            lines[-1].append(word)
            means[-1] = sum(_center_y(item) for item in lines[-1]) / len(lines[-1])
        else:
            lines.append([word])
            means.append(y)
    return tuple(tuple(sorted(line, key=lambda item: item.bbox[0])) for line in lines)


def _header_anchors(
    line: tuple[PDFWord, ...],
    role_resolver: Callable[[str | None], str | None],
    *,
    max_ngram: int = 3,
) -> dict[str, _HeaderAnchor]:
    anchors: dict[str, _HeaderAnchor] = {}
    for width in range(1, max_ngram + 1):
        for start in range(len(line) - width + 1):
            span = line[start : start + width]
            text = " ".join(word.text for word in span)
            role = role_resolver(text)
            if role is None or role in anchors:
                continue
            anchors[role] = _HeaderAnchor(role=role, text=text, x0=span[0].bbox[0])
    return anchors


def _column_bounds(anchors: tuple[_HeaderAnchor, ...]) -> tuple[tuple[float, float], ...]:
    """Build finite Voronoi-like column bounds from ordered header anchors."""
    if len(anchors) < 2:
        return ()
    first_gap = anchors[1].x0 - anchors[0].x0
    last_gap = anchors[-1].x0 - anchors[-2].x0
    if first_gap <= 0 or last_gap <= 0:
        return ()
    bounds: list[tuple[float, float]] = []
    for index, anchor in enumerate(anchors):
        if index == 0:
            left = anchor.x0 - first_gap / 2.0
        else:
            left = (anchors[index - 1].x0 + anchor.x0) / 2.0
        if index == len(anchors) - 1:
            right = anchor.x0 + last_gap / 2.0
        else:
            right = (anchor.x0 + anchors[index + 1].x0) / 2.0
        bounds.append((left, right))
    return tuple(bounds)


def _cells_for_line(line: tuple[PDFWord, ...], bounds: tuple[tuple[float, float], ...]) -> tuple[str | None, ...]:
    cells: list[str | None] = []
    for left, right in bounds:
        selected = [word for word in line if left <= _center_x(word) < right]
        text = " ".join(word.text for word in selected).strip()
        cells.append(text or None)
    return tuple(cells)


def _normalized_text(value: str) -> str:
    return " ".join(value.casefold().split())


def _bbox_for_lines(*lines: tuple[PDFWord, ...]) -> tuple[float, float, float, float]:
    words = tuple(word for line in lines for word in line)
    return (
        min(word.bbox[0] for word in words),
        min(word.bbox[1] for word in words),
        max(word.bbox[2] for word in words),
        max(word.bbox[3] for word in words),
    )


def _nearby_table_caption(
    lines: tuple[tuple[PDFWord, ...], ...],
    *,
    header_index: int,
    max_caption_lines: int,
    max_caption_vertical_gap: float,
) -> str | None:
    header_y = _line_y(lines[header_index])
    start = max(0, header_index - max_caption_lines)
    candidates: list[tuple[float, str]] = []
    for candidate in lines[start:header_index]:
        candidate_y = _line_y(candidate)
        if header_y - candidate_y > max_caption_vertical_gap:
            continue
        text = _line_text(candidate)
        if _TABLE_CAPTION_RE.search(text) and canonical_table_label(text) is not None:
            candidates.append((candidate_y, text))
    if not candidates:
        return None
    return max(candidates, key=lambda item: item[0])[1]


def reconstruct_borderless_tables(
    snapshot: NativePDFSnapshot,
    *,
    variable_label: str,
    role_resolver: Callable[[str | None], str | None],
    table_label: str | None = None,
    required_roles: frozenset[str] = frozenset({"variable", "beta", "se", "t_stat"}),
    max_data_line_gap: int = 40,
    max_data_vertical_gap: float = 180.0,
    max_caption_lines: int = 5,
    max_caption_vertical_gap: float = 120.0,
) -> tuple[PDFTable, ...]:
    """Reconstruct all local caption-anchored tables containing a requested variable.

    Returning all matches is intentional: hard-audit callers must detect display-item ambiguity
    rather than silently selecting the first table when the same variable occurs multiple times.
    """
    requested_label = canonical_table_label(table_label) if table_label is not None else None
    matches: list[PDFTable] = []
    for page in snapshot.pages:
        lines = _cluster_lines(page.words)
        for header_index, header_line in enumerate(lines):
            anchors_by_role = _header_anchors(header_line, role_resolver)
            if not required_roles.issubset(anchors_by_role):
                continue
            caption = _nearby_table_caption(
                lines,
                header_index=header_index,
                max_caption_lines=max_caption_lines,
                max_caption_vertical_gap=max_caption_vertical_gap,
            )
            if caption is None:
                continue
            if requested_label is not None and canonical_table_label(caption) != requested_label:
                continue
            anchors = tuple(sorted(anchors_by_role.values(), key=lambda item: item.x0))
            if not anchors or anchors[0].role != "variable":
                continue
            bounds = _column_bounds(anchors)
            if not bounds:
                continue
            header_cells = tuple(anchor.text for anchor in anchors)
            target = _normalized_text(variable_label)
            header_y = _line_y(header_line)
            stop = min(len(lines), header_index + 1 + max_data_line_gap)
            for data_line in lines[header_index + 1 : stop]:
                if _line_y(data_line) - header_y > max_data_vertical_gap:
                    break
                cells = _cells_for_line(data_line, bounds)
                first = cells[0]
                if first is None or _normalized_text(first) != target:
                    continue
                if sum(cell is not None for cell in cells) < len(required_roles):
                    continue
                matches.append(
                    PDFTable(
                        page=page.page,
                        table_index=-(header_index + 1),
                        bbox=_bbox_for_lines(header_line, data_line),
                        rows=(header_cells, cells),
                        caption=caption,
                    )
                )
                break
    return tuple(matches)


def reconstruct_borderless_table(
    snapshot: NativePDFSnapshot,
    *,
    variable_label: str,
    role_resolver: Callable[[str | None], str | None],
    table_label: str | None = None,
    required_roles: frozenset[str] = frozenset({"variable", "beta", "se", "t_stat"}),
    max_data_line_gap: int = 40,
    max_data_vertical_gap: float = 180.0,
    max_caption_lines: int = 5,
    max_caption_vertical_gap: float = 120.0,
) -> PDFTable | None:
    """Backward-compatible single-table wrapper; ambiguity-aware callers use the plural API."""
    tables = reconstruct_borderless_tables(
        snapshot,
        variable_label=variable_label,
        role_resolver=role_resolver,
        table_label=table_label,
        required_roles=required_roles,
        max_data_line_gap=max_data_line_gap,
        max_data_vertical_gap=max_data_vertical_gap,
        max_caption_lines=max_caption_lines,
        max_caption_vertical_gap=max_caption_vertical_gap,
    )
    return tables[0] if tables else None
