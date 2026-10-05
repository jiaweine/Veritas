from __future__ import annotations

import colorsys
import re
from pathlib import Path

from veritas.harness.planner import parse_command
from veritas.harness.service import _conversation_summary

ROOT = Path(__file__).resolve().parents[1]
STATIC = ROOT / "src/veritas/harness/static"


def test_natural_language_summary_and_inspect_intents() -> None:
    assert parse_command("What needs attention?").action == "summary"
    assert parse_command("有哪些问题？").action == "summary"
    assert parse_command("summarize this paper").action == "summary"
    assert parse_command("inspect this paper").action == "inspect"
    assert parse_command("tell me a joke").action == "chat"


def test_conversation_summary_uses_only_persisted_audit_state() -> None:
    record = {
        "paper_summary": {"pages": 12, "tables_detected": 4},
        "latest_result": {
            "status": "contradiction",
            "counts": {"verified": 2, "needs_review": 1, "contradictions": 1},
            "findings": [
                {
                    "title": "Regression reporting contradiction",
                    "explanation": "Reported p-value is incompatible with the statistic.",
                }
            ],
            "source": {"table": "Table 4", "page": 8, "row": "Minimum wage"},
        },
    }
    title, detail, status, payload = _conversation_summary(record)
    assert title == "Current audit summary"
    assert status == "danger"
    assert "2 verified" in detail
    assert "Regression reporting contradiction" in detail
    assert "Table 4" in detail and "p.8" in detail
    assert payload["counts"]["contradictions"] == 1
    assert payload["finding_count"] == 1


def test_conversation_summary_fails_closed_without_a_result() -> None:
    title, detail, status, payload = _conversation_summary(
        {"paper_summary": {"pages": 3, "tables_detected": 1}}
    )
    assert title == "No verification result yet"
    assert status == "review"
    assert "3 pages" in detail and "1 detected tables" in detail
    assert payload == {"conversation_intent": "summary", "has_result": False}


def _assert_not_blue_literal(path: Path, text: str) -> None:
    colors: list[tuple[int, int, int, str]] = []
    for match in re.finditer(r"#[0-9a-fA-F]{8}\b|#[0-9a-fA-F]{6}\b", text):
        value = match.group(0)
        digits = value[1:7]
        colors.append((*(int(digits[i : i + 2], 16) for i in (0, 2, 4)), value))
    for match in re.finditer(
        r"\b(?:rgb|rgba)\(\s*(\d{1,3})\s*,\s*(\d{1,3})\s*,\s*(\d{1,3})",
        text,
    ):
        colors.append((int(match.group(1)), int(match.group(2)), int(match.group(3)), match.group(0)))

    violations = []
    for r, g, b, literal in colors:
        h, s, _ = colorsys.rgb_to_hsv(r / 255, g / 255, b / 255)
        if s >= 0.12 and 180 <= h * 360 <= 285:
            violations.append(literal)
    assert not violations, f"blue/indigo literals remain in {path}: {violations[:12]}"


def test_active_product_palette_has_no_blue_or_indigo() -> None:
    html = (STATIC / "index.html").read_text()
    active_css = re.findall(r'<link[^>]+href="/static/([^"]+\.css)"', html)
    active_js = re.findall(r'<script[^>]+src="/static/([^"]+\.js)"', html)
    paths = [STATIC / name for name in active_css + active_js]
    paths += [STATIC / "index.html", STATIC / "manifest.webmanifest", STATIC / "icon.svg"]
    paths += sorted((ROOT / "mobile").glob("*.tsx"))
    for path in paths:
        _assert_not_blue_literal(path, path.read_text())


def test_conversation_is_the_default_product_entry_not_a_side_utility() -> None:
    html = (STATIC / "index.html").read_text()
    app = (STATIC / "app.js").read_text()
    assert 'id="conversation-nav"' in html
    assert "Research conversation" in html
    assert ">API</a>" not in html
    assert "await openConversation();" in app
    assert "els.agentMessage.value = message; showToast(`Conversation failed · ${error.message}`);" in app
