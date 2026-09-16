from __future__ import annotations

from pathlib import Path

import veritas.harness.web as harness_web


def test_overview_sparklines_only_use_persisted_coverage_history() -> None:
    app_js = Path(harness_web.__file__).with_name("static") / "app.js"
    source = app_js.read_text(encoding="utf-8")

    assert "state.audits.map((_,i)=>i+1)" not in source
    assert "checks_verified*.35" not in source
    assert "checks_contradictions*.4" not in source
    assert 'if (!values.length) return "";' in source
    assert source.count("sparkline(") == 2  # function definition + real coverage-series call
