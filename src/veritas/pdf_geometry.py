from __future__ import annotations

import re
import unicodedata
from collections.abc import Callable
from dataclasses import dataclass

from .pdf_native import NativePDFSnapshot, PDFTable, PDFWord, canonical_table_label

_TABLE_CAPTION_RE = re.compile(r"\btable\s*(?:[a-z]?\d+|[ivxlcdm]+)?\b", re.IGNORECASE)


@dataclass(frozen=True)
class _HeaderAnchor:
    role: str
    text: str
    x0: float


@dataclass(frozen=True)
class _HeaderBand:
    anchors: dict[str, _HeaderAnchor]
    line_indices: tuple[int, ...]

    @property
    def start(self) -> int:
        return min(self.line_indices)

    @property
    def end(self) -> int:
        return max(self.line_indices)


def _center_y(word: PDFWord) -> float:
    return (word.bbox[1] + word.bbox[3]) / 2.0


def _center_x(word: PDFWord) -> float:
    return (word.bbox[0] + word.bbox[2]) / 2.0


def _line_y(line: tuple[PDFWord, ...]) -> float:
    return sum(_center_y(word) for word in line) / len(line)


def _line_text(line: tuple[PDFWord, ...]) -> str:
    return " ".join(word.text for word in line).strip()


def _cluster_lines(
    words: tuple[PDFWord, ...],
    *,
    y_tolerance: float = 3.0,
) -> tuple[tuple[PDFWord, ...], ...]:
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


def _compact_text(value: str) -> str:
    normalized = unicodedata.normalize("NFKC", value).casefold()
    return "".join(character for character in normalized if character.isalnum())


def _geometry_fallback_role(value: str) -> str | None:
    """Recognize geometry-only separators and common test-probability headers.

    These roles do not by themselves establish statistical semantics. They only preserve column
    boundaries or expose a p-value column after an already caption-anchored table is reconstructed.
    Directional CI anchors deliberately require the direction word first (for example `upper CI`),
    so an overlapping `CI upper` n-gram cannot steal the anchor from the true column heading.
    """
    compact = _compact_text(value)
    if compact in {"prz", "prt", "prchi2", "prchisq"}:
        return "p_value"
    if compact in {
        "lowerci",
        "lower95ci",
        "lowerconfidenceinterval",
        "lower95confidenceinterval",
    }:
        return "separator_ci_lower"
    if compact in {
        "upperci",
        "upper95ci",
        "upperconfidenceinterval",
        "upper95confidenceinterval",
    }:
        return "separator_ci_upper"
    return None


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
            role = role_resolver(text) or _geometry_fallback_role(text)
            if role is None or role in anchors:
                continue
            anchors[role] = _HeaderAnchor(role=role, text=text, x0=span[0].bbox[0])
    if "separator_ci_lower" in anchors or "separator_ci_upper" in anchors:
        anchors.pop("separator_ci", None)
    return anchors


def _header_band(
    lines: tuple[tuple[PDFWord, ...], ...],
    *,
    header_index: int,
    role_resolver: Callable[[str | None], str | None],
    required_roles: frozenset[str],
    max_header_line_gap: float,
    allow_implicit_variable: bool = False,
) -> _HeaderBand | None:
    """Build a bounded header band without changing global line clustering.

    Ordinarily the primary line must identify the variable column. For the deliberately narrow
    implicit-row-label path, the variable header may be absent, but all required statistical roles
    must still be present and later code must independently establish the first-column semantics
    from the publication caption and the exact requested row label.
    """
    primary = _header_anchors(lines[header_index], role_resolver)
    if "variable" not in primary and not allow_implicit_variable:
        return None

    anchors = dict(primary)
    line_indices = [header_index]
    primary_y = _line_y(lines[header_index])
    for neighbor_index in (header_index - 1, header_index + 1):
        if neighbor_index < 0 or neighbor_index >= len(lines):
            continue
        neighbor = lines[neighbor_index]
        if abs(_line_y(neighbor) - primary_y) > max_header_line_gap:
            continue
        neighbor_anchors = _header_anchors(neighbor, role_resolver)
        added = False
        for role, anchor in neighbor_anchors.items():
            if role not in anchors:
                anchors[role] = anchor
                added = True
        if added:
            line_indices.append(neighbor_index)

    needed = required_roles if "variable" in anchors else required_roles - {"variable"}
    if not needed.issubset(anchors):
        return None
    return _HeaderBand(anchors=anchors, line_indices=tuple(sorted(line_indices)))


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


def _cells_for_line(
    line: tuple[PDFWord, ...],
    bounds: tuple[tuple[float, float], ...],
) -> tuple[str | None, ...]:
    cells: list[str | None] = []
    for left, right in bounds:
        selected = [word for word in line if left <= _center_x(word) < right]
        text = " ".join(word.text for word in selected).strip()
        cells.append(text or None)
    return tuple(cells)


def normalized_row_label(value: str) -> str:
    """Normalize Unicode and repeated whitespace while preserving token boundaries."""
    normalized = unicodedata.normalize("NFKC", value).casefold().replace("\u00a0", " ")
    return " ".join(normalized.split())


def canonical_row_label(value: str) -> str:
    """Relax only parser-induced whitespace tokenization after exact identity is anchored."""
    return "".join(normalized_row_label(value).split())


def _row_label_matches(value: str, target: str, *, allow_token_boundary: bool) -> bool:
    if allow_token_boundary:
        return canonical_row_label(value) == canonical_row_label(target)
    return normalized_row_label(value) == normalized_row_label(target)


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


def _caption_declares_implicit_row_label(caption: str) -> bool:
    compact = _compact_text(caption)
    if "firstcolumn" not in compact:
        return False
    return any(
        phrase in compact
        for phrase in (
            "coefficientname",
            "variablename",
            "parametername",
            "predictorname",
            "termname",
        )
    )


def _leading_row_label(
    line: tuple[PDFWord, ...],
    *,
    first_stat_x0: float,
    target: str,
    allow_token_boundary: bool,
    minimum_gap: float = 6.0,
) -> tuple[PDFWord, ...] | None:
    prefix = tuple(word for word in line if word.bbox[2] <= first_stat_x0 - minimum_gap)
    if not prefix:
        return None
    text = _line_text(prefix)
    if not _row_label_matches(text, target, allow_token_boundary=allow_token_boundary):
        return None
    return prefix


def _deduplicate_tables(tables: list[PDFTable]) -> tuple[PDFTable, ...]:
    """Collapse only identical virtual reconstructions of the same publication display item."""
    unique: dict[tuple[object, ...], PDFTable] = {}
    for table in tables:
        key = (
            table.page,
            canonical_table_label(table.caption),
            table.rows,
        )
        unique.setdefault(key, table)
    return tuple(unique.values())


def _render_header_anchor(anchor: _HeaderAnchor) -> str:
    if anchor.role == "p_value" and _geometry_fallback_role(anchor.text) == "p_value":
        return "p"
    if anchor.role.startswith("separator_ci_"):
        return "CI"
    return anchor.text


def reconstruct_borderless_tables(
    snapshot: NativePDFSnapshot,
    *,
    variable_label: str,
    role_resolver: Callable[[str | None], str | None],
    table_label: str | None = None,
    allow_token_boundary: bool = True,
    required_roles: frozenset[str] = frozenset({"variable", "beta", "se", "t_stat"}),
    max_header_line_gap: float = 10.0,
    max_data_line_gap: int = 40,
    max_data_vertical_gap: float = 180.0,
    max_caption_lines: int = 5,
    max_caption_vertical_gap: float = 120.0,
) -> tuple[PDFTable, ...]:
    """Reconstruct local caption-anchored tables containing a requested row.

    The standard path requires an explicit variable-column header. A narrow implicit path is also
    supported when the publication caption explicitly declares that the first column contains a
    coefficient/variable/parameter name. The implicit path still requires an exact target label to
    the left of the first statistical column and never infers row identity from numeric position.
    """
    requested_label = canonical_table_label(table_label) if table_label is not None else None
    matches: list[PDFTable] = []
    for page in snapshot.pages:
        lines = _cluster_lines(page.words)
        for header_index in range(len(lines)):
            band = _header_band(
                lines,
                header_index=header_index,
                role_resolver=role_resolver,
                required_roles=required_roles,
                max_header_line_gap=max_header_line_gap,
                allow_implicit_variable=True,
            )
            if band is None:
                continue
            caption = _nearby_table_caption(
                lines,
                header_index=band.start,
                max_caption_lines=max_caption_lines,
                max_caption_vertical_gap=max_caption_vertical_gap,
            )
            if caption is None:
                continue
            if requested_label is not None and canonical_table_label(caption) != requested_label:
                continue

            implicit_variable = "variable" not in band.anchors
            if implicit_variable and not _caption_declares_implicit_row_label(caption):
                continue

            statistical_anchors = tuple(sorted(band.anchors.values(), key=lambda item: item.x0))
            if not statistical_anchors:
                continue
            if not implicit_variable and statistical_anchors[0].role != "variable":
                continue

            header_lines = tuple(lines[index] for index in band.line_indices)
            header_y = max(_line_y(line) for line in header_lines)
            stop = min(len(lines), band.end + 1 + max_data_line_gap)
            for data_line in lines[band.end + 1 : stop]:
                if _line_y(data_line) - header_y > max_data_vertical_gap:
                    break

                anchors = statistical_anchors
                if implicit_variable:
                    label_words = _leading_row_label(
                        data_line,
                        first_stat_x0=statistical_anchors[0].x0,
                        target=variable_label,
                        allow_token_boundary=allow_token_boundary,
                    )
                    if label_words is None:
                        continue
                    variable_anchor = _HeaderAnchor(
                        role="variable",
                        text="Variable",
                        x0=label_words[0].bbox[0],
                    )
                    anchors = (variable_anchor, *statistical_anchors)

                bounds = _column_bounds(anchors)
                if not bounds:
                    continue
                cells = _cells_for_line(data_line, bounds)
                first = cells[0]
                if first is None or not _row_label_matches(
                    first,
                    variable_label,
                    allow_token_boundary=allow_token_boundary,
                ):
                    continue
                if sum(cell is not None for cell in cells) < len(required_roles):
                    continue

                header_cells = tuple(_render_header_anchor(anchor) for anchor in anchors)
                matches.append(
                    PDFTable(
                        page=page.page,
                        table_index=-(header_index + 1),
                        bbox=_bbox_for_lines(*header_lines, data_line),
                        rows=(header_cells, cells),
                        caption=caption,
                    )
                )
    return _deduplicate_tables(matches)


def reconstruct_borderless_table(
    snapshot: NativePDFSnapshot,
    *,
    variable_label: str,
    role_resolver: Callable[[str | None], str | None],
    table_label: str | None = None,
    allow_token_boundary: bool = True,
    required_roles: frozenset[str] = frozenset({"variable", "beta", "se", "t_stat"}),
    max_header_line_gap: float = 10.0,
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
        allow_token_boundary=allow_token_boundary,
        required_roles=required_roles,
        max_header_line_gap=max_header_line_gap,
        max_data_line_gap=max_data_line_gap,
        max_data_vertical_gap=max_data_vertical_gap,
        max_caption_lines=max_caption_lines,
        max_caption_vertical_gap=max_caption_vertical_gap,
    )
    return tables[0] if tables else None
