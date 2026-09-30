from pathlib import Path


def test_harness_stress_documentation_names_the_runtime_and_process_boundary() -> None:
    text = Path("docs/HARNESS_STRESS.md").read_text(encoding="utf-8")
    assert "scripts/stress_harness_runtime.py" in text
    assert "harness-stress" in text
    assert "single-process" in text
    assert "distributed database" in text
