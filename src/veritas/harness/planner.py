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


_SUMMARY_REQUESTS = {
    "summary",
    "summarize",
    "summarise",
    "summarize this paper",
    "summarise this paper",
    "summarize this audit",
    "summarise this audit",
    "what needs attention",
    "what should i review",
    "show findings",
    "show me the findings",
    "what are the findings",
    "current result",
    "audit result",
    "总结",
    "总结一下",
    "总结这篇论文",
    "总结这次审计",
    "有哪些问题",
    "有什么问题",
    "需要关注什么",
    "审计结果",
    "当前结果",
}

_INSPECT_REQUESTS = {
    "/inspect",
    "inspect",
    "inspect this paper",
    "show paper structure",
    "paper structure",
    "查看论文",
    "查看",
    "论文结构",
    "看看论文结构",
}


def _normalize_prompt(text: str) -> str:
    return re.sub(r"[?.!。！？]+$", "", text.strip().casefold()).strip()


def parse_command(message: str) -> AuditCommand:
    text = message.strip()
    if not text:
        raise ValueError("message is empty")

    lowered = _normalize_prompt(text)
    if lowered in {"/help", "help", "帮助"}:
        return AuditCommand("help")
    if lowered in _SUMMARY_REQUESTS:
        return AuditCommand("summary")
    if lowered in _INSPECT_REQUESTS:
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
        'Ask “What needs attention?” for a summary grounded in the latest persisted audit, '
        'or “inspect this paper” to review detected structure. For a specific regression row, '
        'run `/audit row="Treatment" table=2 page=1`; table and page are optional when the row label is unique.'
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
