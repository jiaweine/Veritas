from __future__ import annotations

import re
import shlex
from dataclasses import dataclass


@dataclass(frozen=True)
class AuditCommand:
    action: str
    row_label: str | None = None
    table_label: str | None = None
    expected_page: int | None = None


def parse_command(message: str) -> AuditCommand:
    text = message.strip()
    if not text:
        raise ValueError("message is empty")

    lowered = text.casefold()
    if lowered in {"/help", "help", "帮助"}:
        return AuditCommand("help")
    if lowered in {"/inspect", "inspect", "查看论文", "查看"}:
        return AuditCommand("inspect")

    if lowered.startswith("/audit"):
        body = text[len("/audit") :].strip()
        return _parse_audit_body(body)
    if lowered.startswith("audit "):
        return _parse_audit_body(text[6:].strip())
    if text.startswith("审计"):
        return _parse_audit_body(text[2:].strip())
    if text.startswith("检查"):
        return _parse_audit_body(text[2:].strip())

    return AuditCommand("chat")


def help_text() -> str:
    return (
        "Use `/inspect` to review detected paper structure, or run a regression audit with "
        '`/audit row="Treatment" table=2 page=1`. Table and page are optional when the '
        "row label is unique."
    )


def _parse_audit_body(body: str) -> AuditCommand:
    if not body:
        raise ValueError(
            'audit requires a row label, for example `/audit row="Treatment" table=2 page=1`'
        )

    try:
        tokens = shlex.split(body)
    except ValueError as exc:
        raise ValueError(f"could not parse audit command: {exc}") from exc

    values: dict[str, str] = {}
    free: list[str] = []
    for token in tokens:
        if "=" in token:
            key, value = token.split("=", 1)
            key = key.casefold().strip()
            if key in {"row", "variable", "table", "page"}:
                values[key] = value.strip()
                continue
        free.append(token)

    row_label = values.get("row") or values.get("variable")
    if row_label is None and free:
        row_label = " ".join(free).strip()
    if not row_label:
        raise ValueError("audit requires a non-empty row label")

    table_label = values.get("table")
    if table_label:
        normalized = table_label.strip()
        if not re.search(r"\btable\b", normalized, flags=re.IGNORECASE):
            normalized = f"Table {normalized}"
        table_label = normalized

    page_value = values.get("page")
    expected_page = None
    if page_value is not None:
        try:
            expected_page = int(page_value)
        except ValueError as exc:
            raise ValueError("page must be an integer") from exc
        if expected_page <= 0:
            raise ValueError("page must be positive")

    return AuditCommand(
        "audit_regression",
        row_label=row_label,
        table_label=table_label,
        expected_page=expected_page,
    )
