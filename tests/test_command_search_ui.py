STATIC_DIR = "src/veritas/harness/static"


def read_static(name: str) -> str:
    with open(f"{STATIC_DIR}/{name}", encoding="utf-8") as handle:
        return handle.read()


def test_command_search_slice_is_loaded_after_app_state_bindings() -> None:
    html = read_static("index.html")
    app_script = '<script type="module" src="/static/app.js"></script>'
    search_script = '<script type="module" src="/static/command-search.js"></script>'
    assert app_script in html
    assert search_script in html
    assert html.index(app_script) < html.index(search_script)


def test_command_search_has_race_and_recovery_guards() -> None:
    source = read_static("command-search.js")
    assert "SEARCH_DEBOUNCE_MS" in source
    assert "AbortController" in source
    assert "searchSequence" in source
    assert 'error?.name === "AbortError"' in source
    assert "data-command-search-retry" in source
    assert 'target.searchParams.set("audit_open", auditId)' in source


def test_service_worker_caches_command_search_slice() -> None:
    source = read_static("sw.js")
    assert 'COMMAND_SEARCH_CACHE_REVISION = "command-search-1"' in source
    assert '"/static/command-search.js"' in source
