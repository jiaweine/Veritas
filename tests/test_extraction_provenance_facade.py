from veritas.extraction_provenance import (
    AttestedExtractionEvidenceReleaseReceipt,
    ExternallyVerifiedExtractionEvidenceReceipt,
    ExternallyVerifiedExtractionRunReceipt,
    ExtractionExecutionPlan,
    ExtractionExternalTrustRoot,
    build_attested_extraction_evidence_release_receipt,
    build_extraction_external_provenance_statement,
    load_extraction_external_trust_root,
    load_extraction_signed_external_provenance,
    verify_external_extraction_provenance,
    verify_external_extraction_provenance_for_run,
)


def test_extraction_provenance_facade_exports_stable_public_symbols() -> None:
    assert ExtractionExecutionPlan.__name__ == "ExtractionExecutionPlan"
    assert ExtractionExternalTrustRoot.__name__ == "ExtractionExternalTrustRoot"
    assert AttestedExtractionEvidenceReleaseReceipt.__name__.startswith("AttestedExtraction")
    assert ExternallyVerifiedExtractionEvidenceReceipt.__name__.startswith("ExternallyVerified")
    assert ExternallyVerifiedExtractionRunReceipt.__name__.startswith("ExternallyVerified")
    assert callable(build_attested_extraction_evidence_release_receipt)
    assert callable(build_extraction_external_provenance_statement)
    assert callable(load_extraction_external_trust_root)
    assert callable(load_extraction_signed_external_provenance)
    assert callable(verify_external_extraction_provenance)
    assert callable(verify_external_extraction_provenance_for_run)
