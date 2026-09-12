from __future__ import annotations

import pymupdf

from veritas.harness.planner import parse_command
from veritas.harness.service import AuditHarness


def _make_regression_pdf(*, p_value: str = "0.046") -> bytes:
    doc = pymupdf.open()
    page = doc.new_page(width=612, height=792)
    page.insert_text((60, 72), "Synthetic Social Science Article", fontsize=14)
    page.insert_text((60, 112), "Table 2. Main regression", fontsize=11)

    xs = (72, 220, 300, 380, 460, 540)
    ys = (140, 170, 200)
    for x in xs:
        page.draw_line((x, ys[0]), (x, ys[-1]), width=0.8)
    for y in ys:
        page.draw_line((xs[0], y), (xs[-1], y), width=0.8)

    header = ("Variable", "Coef.", "SE", "z", "p")
    data = ("Treatment", "0.100", "0.050", "2.000", p_value)
    for column, text in enumerate(header):
        page.insert_text((xs[column] + 4, 160), text, fontsize=9)
    for column, text in enumerate(data):
        page.insert_text((xs[column] + 4, 190), text, fontsize=9)

    payload = doc.tobytes(garbage=4, deflate=True)
    doc.close()
    return payload


def test_audit_command_parser_preserves_locator() -> None:
    command = parse_command('/audit row="Minimum wage" table=4 page=12')
    assert command.action == "audit_regression"
    assert command.row_label == "Minimum wage"
    assert command.table_label == "Table 4"
    assert command.expected_page == 12


def test_harness_runs_existing_pdf_extraction_and_detector(tmp_path) -> None:
    harness = AuditHarness(tmp_path)
    record = harness.create_audit(
        title="Synthetic paper",
        filename="synthetic.pdf",
        pdf_bytes=_make_regression_pdf(p_value="0.500"),
    )

    assert record["paper_summary"]["pages"] == 1
    assert record["paper_summary"]["tables_detected"] >= 1
    assert len(record["paper_summary"]["parser_snapshots"]) == 2

    events = list(
        harness.stream_message(
            record["audit_id"],
            '/audit row="Treatment" table=2 page=1',
        )
    )
    result_events = [event for event in events if event.get("payload", {}).get("result")]
    assert result_events

    result = result_events[-1]["payload"]["result"]
    assert result["status"] == "contradiction"
    assert result["source"]["page"] == 1
    assert result["consensus"]["beta"] == "0.100"
    assert result["counts"]["contradictions"] >= 1
    assert result["findings"]

    persisted = harness.get_audit(record["audit_id"])
    assert persisted["latest_result"]["status"] == "contradiction"
    assert persisted["status"] == "ready"


def test_harness_inspect_command_returns_detected_structure(tmp_path) -> None:
    harness = AuditHarness(tmp_path)
    record = harness.create_audit(
        title="Synthetic paper",
        filename="synthetic.pdf",
        pdf_bytes=_make_regression_pdf(),
    )
    events = list(harness.stream_message(record["audit_id"], "/inspect"))
    final = events[-1]
    assert final["kind"] == "assistant_message"
    assert final["payload"]["paper_summary"]["tables_detected"] >= 1
