from pathlib import Path


def test_reproducibility_artifacts_documentation_locks_authority_boundaries() -> None:
    text = Path("docs/REPRODUCIBILITY_ARTIFACTS.md").read_text(encoding="utf-8")

    for phrase in (
        "--network none",
        "read-only at `/input`",
        "DependencyLock",
        "Optional licensed Stata adapter",
        "ReproductionProvenanceGraph",
        "comparison operator",
        "build_attested_reproduction_e4_check()",
        "does **not** accept a caller-constructed `ReproductionReport`",
        "does not copy reported or reproduced numeric answers",
        "Production authority remains governed",
    ):
        assert phrase in text
