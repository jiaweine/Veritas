from __future__ import annotations

import re
import unicodedata
from dataclasses import dataclass

from .extraction import ExtractionCandidate
from .models import SourceLocation
from .pdf_native import NativePDFSnapshot, PDFWord, canonical_table_label, parse_pdf_dual
from .pdf_regression import RegressionExtractionBundle, _canonical_number

_GROUP_QUALIFIER_RE = re.compile(r"^[a-z][a-z0-9_-]*$", re.IGNORECASE)


@dataclass(frozen=True)
class GroupedRegressionLocator:
    """Publication-visible identity for one regression block inside a grouped table."""

    table_label: str
    model_group_label: str
    expected_page: int | None = None

    def canonical_table_label(self) -> str:
        label = canonical_table_label(self.table_label)
        if label is None:
            raise ValueError(f"unsupported table label: {self.table_label!r}")
        return label


@dataclass(frozen=True)
class _PhraseSpan:
    text: str
    x0: float
    x1: float

    @property
    def center(self) -> float:
        return (self.x0 + self.x1) / 2.0


@dataclass(frozen=True)
class _RoleAnchor:
    role: str
    text: str
    x0: float
    x1: float

    @property
    def center(self) -> float:
        return (self.x0 + self.x1) / 2.0


@dataclass(frozen=True)
class _GroupedMatch:
    snapshot: NativePDFSnapshot
    page: int
    caption: str
    variable_text: str
    field_raw: dict[str, str]
    bbox: tuple[float, float, float, float]


def _center_y(word: PDFWord) -> float:
    return (word.bbox[1] + word.bbox[3]) / 2.0


def _center_x(word: PDFWord) -> float:
    return (word.bbox[0] + word.bbox[2]) / 2.0


def _line_y(line: tuple[PDFWord, ...]) -> float:
    return sum(_center_y(word) for word in line) / len(line)


def _line_text(line: tuple[PDFWord, ...]) -> str:
    return " ".join(word.text for word in line).strip()


def _cluster_lines(words: tuple[PDFWord, ...], *, y_tolerance: float = 3.0) -> tuple[tuple[PDFWord, ...], ...]:
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


def _token(value: str) -> str:
    normalized = unicodedata.normalize("NFKC", value).casefold().replace("\u00a0", " ")
    return "".join(character for character in normalized if character.isalnum() or character in {"_", "-"})


def _label_tokens(value: str) -> tuple[str, ...]:
    return tuple(token for token in (_token(part) for part in value.split()) if token)


def _find_exact_phrase(line: tuple[PDFWord, ...], label: str) -> tuple[_PhraseSpan, ...]:
    target = _label_tokens(label)
    if not target:
        return ()
    tokens = tuple(_token(word.text) for word in line)
    matches: list[_PhraseSpan] = []
    for start in range(len(tokens) - len(target) + 1):
        if tokens[start : start + len(target)] != target:
            continue
        span = line[start : start + len(target)]
        matches.append(_PhraseSpan(_line_text(span), span[0].bbox[0], span[-1].bbox[2]))
    return tuple(matches)


def _regression_group_spans(line: tuple[PDFWord, ...]) -> tuple[_PhraseSpan, ...]:
    """Recognize narrow publication labels such as 'Bivariable regression analysis'."""
    tokens = tuple(_token(word.text) for word in line)
    spans: list[_PhraseSpan] = []
    for index in range(2, len(tokens)):
        if tokens[index - 1] != "regression" or tokens[index] != "analysis":
            continue
        qualifier = tokens[index - 2]
        if not _GROUP_QUALIFIER_RE.fullmatch(qualifier):
            continue
        words = line[index - 2 : index + 1]
        spans.append(_PhraseSpan(_line_text(words), words[0].bbox[0], words[-1].bbox[2]))
    return tuple(spans)


def _subheader_role(text: str) -> str | None:
    stripped = unicodedata.normalize("NFKC", text).strip()
    compact = "".join(character for character in stripped.casefold() if character.isalnum())
    if stripped == "B":
        return "coefficient"
    if stripped in {"β", "ꞵ", "Β"} or compact in {"beta", "standardizedbeta"}:
        return "standardized_beta"
    if compact in {"se", "stderr", "stderror", "standarderror"}:
        return "se"
    if compact in {"t", "tvalue", "tstat", "tstatistic"}:
        return "t_stat"
    if compact in {"p", "pvalue"}:
        return "p_value"
    return None


def _subheader_anchors(line: tuple[PDFWord, ...]) -> tuple[_RoleAnchor, ...]:
    anchors: list[_RoleAnchor] = []
    for word in line:
        role = _subheader_role(word.text)
        if role is None:
            continue
        anchors.append(_RoleAnchor(role, word.text, word.bbox[0], word.bbox[2]))
    return tuple(sorted(anchors, key=lambda anchor: anchor.x0))


def _role_blocks(anchors: tuple[_RoleAnchor, ...]) -> tuple[tuple[_RoleAnchor, ...], ...]:
    signature = ("coefficient", "se", "t_stat", "standardized_beta", "p_value")
    blocks: list[tuple[_RoleAnchor, ...]] = []
    for start in range(len(anchors) - len(signature) + 1):
        candidate = anchors[start : start + len(signature)]
        if tuple(anchor.role for anchor in candidate) == signature:
            blocks.append(candidate)
    return tuple(blocks)


def _column_bounds(anchors: tuple[_RoleAnchor, ...]) -> tuple[tuple[float, float], ...]:
    if len(anchors) < 2:
        return ()
    centers = tuple(anchor.center for anchor in anchors)
    bounds: list[tuple[float, float]] = []
    for index, center in enumerate(centers):
        if index == 0:
            left = center - (centers[1] - center) / 2.0
        else:
            left = (centers[index - 1] + center) / 2.0
        if index == len(centers) - 1:
            right = center + (center - centers[index - 1]) / 2.0
        else:
            right = (center + centers[index + 1]) / 2.0
        bounds.append((left, right))
    return tuple(bounds)


def _cell_text(line: tuple[PDFWord, ...], left: float, right: float) -> str | None:
    words = [word for word in line if left <= _center_x(word) < right]
    text = _line_text(tuple(words))
    return text or None


def _nearby_caption(
    lines: tuple[tuple[PDFWord, ...], ...],
    *,
    group_line_index: int,
    requested_label: str,
    max_lines: int = 6,
    max_vertical_gap: float = 120.0,
) -> str | None:
    group_y = _line_y(lines[group_line_index])
    candidates: list[tuple[float, str]] = []
    for line in lines[max(0, group_line_index - max_lines) : group_line_index]:
        if group_y - _line_y(line) > max_vertical_gap:
            continue
        text = _line_text(line)
        if canonical_table_label(text) == requested_label:
            candidates.append((_line_y(line), text))
    if not candidates:
        return None
    return max(candidates, key=lambda item: item[0])[1]


def _bbox_for_lines(*lines: tuple[PDFWord, ...]) -> tuple[float, float, float, float]:
    words = tuple(word for line in lines for word in line)
    return (
        min(word.bbox[0] for word in words),
        min(word.bbox[1] for word in words),
        max(word.bbox[2] for word in words),
        max(word.bbox[3] for word in words),
    )


def _match_snapshot(
    snapshot: NativePDFSnapshot,
    *,
    variable_label: str,
    locator: GroupedRegressionLocator,
    max_header_gap: float = 14.0,
    max_data_lines: int = 45,
    max_data_vertical_gap: float = 190.0,
) -> tuple[_GroupedMatch | None, str | None]:
    requested_label = locator.canonical_table_label()
    matches: list[_GroupedMatch] = []
    for page in snapshot.pages:
        if locator.expected_page is not None and page.page != locator.expected_page:
            continue
        lines = _cluster_lines(page.words)
        for group_index, group_line in enumerate(lines[:-1]):
            target_spans = _find_exact_phrase(group_line, locator.model_group_label)
            if not target_spans:
                continue
            if len(target_spans) != 1:
                return None, f"{snapshot.parser_id}: model group label is not unique on page {page.page}"

            group_spans = _regression_group_spans(group_line)
            if not group_spans:
                continue
            target_key = _label_tokens(locator.model_group_label)
            matching_groups = [span for span in group_spans if _label_tokens(span.text) == target_key]
            if len(matching_groups) != 1:
                return None, (
                    f"{snapshot.parser_id}: requested model group {locator.model_group_label!r} is not a unique "
                    "publication-visible regression group"
                )

            caption = _nearby_caption(
                lines,
                group_line_index=group_index,
                requested_label=requested_label,
            )
            if caption is None:
                continue

            header_index = group_index + 1
            header_line = lines[header_index]
            if _line_y(header_line) - _line_y(group_line) > max_header_gap:
                continue
            anchors = _subheader_anchors(header_line)
            blocks = _role_blocks(anchors)
            ordered_groups = tuple(sorted(group_spans, key=lambda span: span.center))
            if len(blocks) != len(ordered_groups):
                return None, (
                    f"{snapshot.parser_id}: grouped header has {len(ordered_groups)} visible regression groups but "
                    f"{len(blocks)} complete B/SE/t/beta/p blocks"
                )

            target_position = next(
                index for index, span in enumerate(ordered_groups) if _label_tokens(span.text) == target_key
            )
            target_group = ordered_groups[target_position]
            target_block = blocks[target_position]
            block_left = target_block[0].center
            block_right = target_block[-1].center
            if not block_left <= target_group.center <= block_right:
                return None, (
                    f"{snapshot.parser_id}: model-group text is not horizontally aligned with its statistical block"
                )

            bounds = _column_bounds(anchors)
            if not bounds:
                continue
            anchor_to_bound = {id(anchor): bounds[index] for index, anchor in enumerate(anchors)}
            header_y = _line_y(header_line)
            stop = min(len(lines), header_index + 1 + max_data_lines)
            for data_line in lines[header_index + 1 : stop]:
                if _line_y(data_line) - header_y > max_data_vertical_gap:
                    break
                row_spans = _find_exact_phrase(data_line, variable_label)
                if len(row_spans) != 1:
                    continue
                row_span = row_spans[0]
                if row_span.x0 > target_block[0].x0:
                    continue

                raw: dict[str, str] = {}
                for anchor in target_block:
                    if anchor.role == "standardized_beta":
                        continue
                    left, right = anchor_to_bound[id(anchor)]
                    value = _cell_text(data_line, left, right)
                    if value is None:
                        break
                    key = "beta" if anchor.role == "coefficient" else anchor.role
                    raw[key] = value
                if {"beta", "se", "t_stat", "p_value"}.issubset(raw):
                    matches.append(
                        _GroupedMatch(
                            snapshot=snapshot,
                            page=page.page,
                            caption=caption,
                            variable_text=row_span.text,
                            field_raw=raw,
                            bbox=_bbox_for_lines(group_line, header_line, data_line),
                        )
                    )

    if not matches:
        return None, None
    signatures = {
        tuple((key, _canonical_number(match.field_raw[key])) for key in ("beta", "se", "t_stat", "p_value"))
        for match in matches
    }
    if len(signatures) != 1:
        return None, (
            f"{snapshot.parser_id}: grouped display item is ambiguous for variable {variable_label!r} and "
            f"model group {locator.model_group_label!r}"
        )
    return matches[0], None


def extract_grouped_regression_table(
    snapshots: tuple[NativePDFSnapshot, ...],
    *,
    variable_label: str,
    locator: GroupedRegressionLocator,
) -> RegressionExtractionBundle:
    if not snapshots:
        raise ValueError("at least one parser snapshot is required")
    artifact_ids = {snapshot.artifact_id for snapshot in snapshots}
    artifact_hashes = {snapshot.artifact_sha256 for snapshot in snapshots}
    if len(artifact_ids) != 1 or len(artifact_hashes) != 1:
        raise ValueError("all parser snapshots must refer to the same source artifact")

    fields: dict[str, list[ExtractionCandidate]] = {"beta": [], "se": [], "t_stat": [], "p_value": []}
    ambiguities: list[str] = []
    source: SourceLocation | None = None

    for snapshot in snapshots:
        match, ambiguity = _match_snapshot(
            snapshot,
            variable_label=variable_label,
            locator=locator,
        )
        if ambiguity is not None:
            ambiguities.append(ambiguity)
            continue
        if match is None:
            continue
        source = source or SourceLocation(
            artifact_id=snapshot.artifact_id,
            page=match.page,
            table=f"{match.caption} [group:{locator.model_group_label}]",
            row=match.variable_text,
            bbox=match.bbox,
            text_quote=match.variable_text,
        )
        for key, raw in match.field_raw.items():
            try:
                normalized = _canonical_number(raw)
            except ValueError:
                continue
            fields[key].append(
                ExtractionCandidate(
                    parser_id=f"{snapshot.parser_id}:grouped_word_geometry_v1",
                    parser_family=snapshot.parser_family,
                    raw=raw,
                    normalized_value=normalized,
                    nonconformity_score=0.02,
                    source=SourceLocation(
                        artifact_id=snapshot.artifact_id,
                        page=match.page,
                        table=f"{match.caption} [group:{locator.model_group_label}]",
                        row=match.variable_text,
                        bbox=match.bbox,
                        text_quote=raw,
                    ),
                )
            )

    parser_versions = [(snapshot.parser_id, snapshot.parser_version) for snapshot in snapshots]
    parser_versions.append(("veritas_grouped_regression_geometry", "0.1.0"))
    return RegressionExtractionBundle(
        artifact_id=next(iter(artifact_ids)),
        artifact_sha256=next(iter(artifact_hashes)),
        parser_versions=tuple(sorted(parser_versions)),
        field_candidates={key: tuple(value) for key, value in fields.items()},
        semantic_candidates={"inference_distribution": ()},
        source=source or SourceLocation(artifact_id=next(iter(artifact_ids))),
        ambiguities=tuple(ambiguities),
    )


def prepare_grouped_regression_extraction(
    pdf_bytes: bytes,
    *,
    variable_label: str,
    locator: GroupedRegressionLocator,
    artifact_id: str = "paper",
) -> RegressionExtractionBundle:
    """Parse one PDF through both native word streams, without inferring test-distribution semantics."""
    snapshots = parse_pdf_dual(pdf_bytes, artifact_id=artifact_id)
    return extract_grouped_regression_table(
        snapshots,
        variable_label=variable_label,
        locator=locator,
    )
