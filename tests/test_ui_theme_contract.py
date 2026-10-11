"""Keep desktop, offline PWA, and native dark palettes in sync."""

from __future__ import annotations

import json
import re
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
STATIC = ROOT / "src/veritas/harness/static"


def _css_tokens() -> dict[str, str]:
    css = (STATIC / "styles.css").read_text(encoding="utf-8")
    return {name: value.strip() for name, value in re.findall(
        r"^\s*--([a-z][a-z-]+):\s*([^;]+);", css, re.MULTILINE
    )}


def test_workbench_palette_is_default_for_every_web_route() -> None:
    tokens = _css_tokens()
    assert tokens["bg"] == "#0e0e0e"
    assert tokens["surface"] == "#121212"
    assert tokens["surface-soft"] == "#161616"
    assert tokens["surface-strong"] == "#1c1c1c"
    assert tokens["text"] == "#e9f1f3"
    assert tokens["accent"] == "#52d5cb"
    assert (STATIC / "styles.css").read_text(encoding="utf-8").count(
        "color-scheme: dark"
    ) == 1


def test_dark_theme_loads_last_and_is_cached_offline() -> None:
    shell = (STATIC / "index.html").read_text(encoding="utf-8")
    style_links = re.findall(r'<link rel="stylesheet" href="([^"]+)"', shell)
    assert style_links[-1] == "/static/workspace-theme.css"
    sw = (STATIC / "sw.js").read_text(encoding="utf-8")
    assert '"/static/workspace-theme.css"' in sw
    assert 'const CACHE = "veritas-shell-v36";' in sw
    assert (STATIC / "workspace-theme.css").is_file()
    assert '"/static/ndjson-stream.js"' in sw
    manifest = json.loads((STATIC / "manifest.webmanifest").read_text(encoding="utf-8"))
    assert manifest["background_color"] == "#0e0e0e"
    assert manifest["theme_color"] == "#0e0e0e"
    assert '<meta name="theme-color" content="#0e0e0e" />' in shell


def test_mobile_native_theme_matches_web_and_uses_dark_appearance() -> None:
    tokens = _css_tokens()
    native = (ROOT / "mobile/theme.ts").read_text(encoding="utf-8")
    key_pairs = [
        ("bg", "bg"), ("surface", "surface"), ("surface-soft", "surfaceSoft"),
        ("surface-strong", "surfaceStrong"), ("text", "text"),
        ("text-soft", "textSoft"), ("line", "line"), ("accent", "accent"),
        ("good", "good"), ("warn", "warn"), ("bad", "bad"),
    ]
    for css_key, native_key in key_pairs:
        assert re.search(
            rf"\b{native_key}:\s*\"{re.escape(tokens[css_key])}\"",
            native,
        ), (css_key, native_key)
    app_config = json.loads((ROOT / "mobile/app.json").read_text(encoding="utf-8"))
    assert app_config["expo"]["userInterfaceStyle"] == "dark"
    for filename in ("App.tsx", "ReplicationScreen.tsx"):
        source = (ROOT / "mobile" / filename).read_text(encoding="utf-8")
        assert 'import { workspaceColors } from "./theme";' in source
        style_block = source.split("const styles = StyleSheet.create({", 1)[1]
        assert "workspaceColors." in style_block
        assert not re.search(
            r"\b(?:backgroundColor|borderColor|borderBottomColor|"
            r"borderTopColor|color):\s*[\"']#(?:fff|f[0-9a-f]{5})\b",
            style_block,
            re.IGNORECASE,
        )


def test_reproduction_status_panels_have_dark_background_fallbacks() -> None:
    css = (STATIC / "workspace-theme.css").read_text(encoding="utf-8")
    for selector in (
        ".rep-permission", ".rep-composer", ".rep-diff-state.available",
        ".rep-diff-state.unavailable", ".rep-integrity-warning",
    ):
        assert selector in css


def test_audit_reference_sidebar_keeps_all_product_routes() -> None:
    html = (STATIC / "index.html").read_text(encoding="utf-8")
    reference_js = (STATIC / "reference-workbench.js").read_text(encoding="utf-8")
    primary = set(re.findall(r'data-view="([a-z]+)"', html))
    reference = set(re.findall(r'data-ref-view="([a-z]+)"', reference_js))
    assert {
        "overview", "audits", "findings", "runs", "evidence",
        "reproduction", "benchmarks", "settings",
    }.issubset(primary & reference)
