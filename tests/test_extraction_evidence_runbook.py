from pathlib import Path


def test_extraction_evidence_runbook_preserves_external_authority_boundaries() -> None:
    text = Path("docs/EXTRACTION_EVIDENCE_RUNBOOK.md").read_text(encoding="utf-8")

    for phrase in (
        "scripts/build_extraction_split_manifests.py",
        "Do not replace the frozen execution source commit with current",
        "not proof of human independence",
        "selected expected run context, not from the signed envelope",
        "`production_authorized` remains false",
        "TEST must not feed back",
        "independent historical channel before TEST",
        "scripts/verify_extraction_release_calibration_binding.py",
        "scripts/verify_extraction_release_execution_binding.py",
        "release-calibration-binding.json",
        "release-execution-binding.json",
        "There are no release-stage `--min-selective-coverage`",
        "caller-supplied",
        "execution-id arguments",
        "final repository-side v0.15 release check",
        "scripts/build_extraction_postverification_external_handoff.py",
        "repository_side_postverification_external_archive_handoff_ready_awaiting_independent_archive",
        "does **not** provide a command that generates the custodian receipt",
        "scripts/verify_extraction_postverification_external_archive_receipt.py",
        "verified-postverification-archive-receipt-binding.json",
        "`independent_control_established=false`",
        "`historical_channel_semantics_established=false`",
        "A green CI run, a Git commit, or a structurally valid receipt alone is not that evidence",
    ):
        assert phrase in text

    release_section = text.split(
        "## 7. Build a release bundle bound to calibration and execution attestations",
        maxsplit=1,
    )[1].split("## 8.", maxsplit=1)[0]
    assert (
        "--development-run nc-005 development/nc-005.json "
        "evidence/attestations/development/nc-005.json"
    ) in release_section
    assert (
        "--test-run nc-005 test/nc-005.json "
        "evidence/attestations/test/nc-005.json"
    ) in release_section
    assert "--development-run nc-005 '<execution-id>'" not in release_section
    assert "--test-run nc-005 '<execution-id>'" not in release_section
    assert "--development-run nc-005 0.005" not in release_section
    assert "--test-run nc-005 0.005" not in release_section

    bound_verification = text.index("scripts/verify_bound_extraction_external_provenance.py")
    handoff = text.index("scripts/build_extraction_postverification_external_handoff.py")
    receipt_verification = text.index(
        "scripts/verify_extraction_postverification_external_archive_receipt.py"
    )
    closure = text.index("## 10. What closes issue #26")
    assert bound_verification < handoff < receipt_verification < closure

    postverification_section = text.split(
        "## 9. Archive the post-verification replay set and verify the external receipt",
        maxsplit=1,
    )[1].split("## 10.", maxsplit=1)[0]
    assert "--bound-verification evidence/release/bound-cold-verification.json" in (
        postverification_section
    )
    assert "--expected-handoff-sha256 '<independently-recorded-handoff-sha256>'" in (
        postverification_section
    )
    assert "--expected-custodian-identity '<independently-expected-custodian>'" in (
        postverification_section
    )
    assert "production_authorized=false" in postverification_section
