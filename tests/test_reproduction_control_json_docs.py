from pathlib import Path


def test_strict_reproduction_control_json_policy_is_documented() -> None:
    text = Path("docs/reproduction-control-json.md").read_text(encoding="utf-8")

    for requirement in (
        "duplicate object keys are rejected",
        "`NaN`, `Infinity`, and `-Infinity`",
        "must be finite",
        "booleans are not accepted as numeric values",
        "single-target and target-set",
    ):
        assert requirement in text
