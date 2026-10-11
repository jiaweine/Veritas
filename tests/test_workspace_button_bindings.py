"""Guard dynamic button and audit row query bindings against single-element selectors."""

from pathlib import Path


def test_workspace_actions_bind_collections_not_single_elements() -> None:
    app = Path("src/veritas/harness/static/app.js").read_text(encoding="utf-8")
    for selector in (
        '[data-action="new-audit"]',
        '[data-action="refresh"]',
        '[data-action="agent-open"]',
        '[data-action="open-pdf"]',
        "[data-audit-id]",
        "[data-table-page]",
    ):
        expected = "$$('" + selector + "', els.main).forEach("
        assert expected in app, f"Must use querySelectorAll before forEach: {selector}"
        accidental = "$('" + selector + "', els.main).forEach("
        assert not any(
            line.lstrip().startswith(accidental) for line in app.splitlines()
        ), f"Single-element query cannot be iterated: {selector}"


def test_workspace_and_source_inspector_tabs_have_distinct_selectors() -> None:
    harness = Path("src/veritas/harness/static/audit-harness.js").read_text(
        encoding="utf-8"
    )
    assert 'data-ah-workspace-tab="source"' in harness
    assert 'data-ah-tab="source"' not in harness.split('function renderHarness()')[1].split('function setPage(')[0]
    assert 'document.querySelectorAll("[data-ah-workspace-tab]")' in harness
