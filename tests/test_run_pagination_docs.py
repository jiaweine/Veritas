from pathlib import Path


def test_run_pagination_docs_capture_integrity_and_cursor_contract() -> None:
    text = Path("docs/RUN_PAGINATION.md").read_text(encoding="utf-8")
    for expected in (
        "GET /api/v1/runs",
        "GET /api/v1/run-pages",
        "authoritative audit event journal",
        "opaque keyset cursor",
        "maximum page size is 200",
        "not detector verification or scientific evidence",
    ):
        assert expected in text
