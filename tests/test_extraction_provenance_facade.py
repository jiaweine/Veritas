from veritas.extraction_provenance import (
    AttestedExtractionEvidenceReleaseReceipt,
    ExternallyVerifiedExtractionEvidenceReceipt,
    ExternallyVerifiedExtractionRunReceipt,
    ExtractionExecutionPlan,
    ExtractionExternalTrustPolicy,
    ExtractionExternalTrustRoot,
    PrecommittedExternalExtractionRunReceipt,
    build_attested_extraction_evidence_release_receipt,
    build_extraction_external_provenance_statement,
    build_extraction_external_trust_policy,
    load_extraction_external_trust_policy,
    load_extraction_external_trust_root,
    load_extraction_signed_external_provenance,
    verify_external_extraction_provenance,
    verify_external_extraction_provenance_for_run,
    verify_precommitted_external_extraction_provenance_for_run,
)


def test_extraction_provenance_facade_exports_stable_public_symbols() -> None:
    assert ExtractionExecutionPlan.__name__ == "ExtractionExecutionPlan"
    assert ExtractionExternalTrustRoot.__name__ == "ExtractionExternalTrustRoot"
    assert ExtractionExternalTrustPolicy.__name__ == "ExtractionExternalTrustPolicy"
    assert AttestedExtractionEvidenceReleaseReceipt.__name__.startswith("AttestedExtraction")
    assert ExternallyVerifiedExtractionEvidenceReceipt.__name__.startswith("ExternallyVerified")
    assert ExternallyVerifiedExtractionRunReceipt.__name__.startswith("ExternallyVerified")
    assert PrecommittedExternalExtractionRunReceipt.__name__.startswith("PrecommittedExternal")
    assert callable(build_attested_extraction_evidence_release_receipt)
    assert callable(build_extraction_external_provenance_statement)
    assert callable(build_extraction_external_trust_policy)
    assert callable(load_extraction_external_trust_policy)
    assert callable(load_extraction_external_trust_root)
    assert callable(load_extraction_signed_external_provenance)
    assert callable(verify_external_extraction_provenance)
    assert callable(verify_external_extraction_provenance_for_run)
    assert callable(verify_precommitted_external_extraction_provenance_for_run)
