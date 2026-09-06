from veritas.extraction_provenance import (
    ExtractionSignedSourceArchiveProvenance,
    ExtractionSourceArchiveProvenanceStatement,
    ExtractionSourceArchiveTrustPolicy,
    PrecommittedExtractionSourceArchiveReceipt,
    build_extraction_source_archive_provenance_statement,
    build_extraction_source_archive_trust_policy,
    extraction_signed_source_archive_provenance_json_payload,
    extraction_source_archive_provenance_statement_bytes,
    extraction_source_archive_trust_policy_json_payload,
    load_extraction_signed_source_archive_provenance,
    load_extraction_source_archive_trust_policy,
    verify_precommitted_extraction_source_archive_provenance_for_run,
)


def test_source_archive_provenance_facade_exports_public_symbols() -> None:
    assert ExtractionSignedSourceArchiveProvenance.__name__.startswith("ExtractionSigned")
    assert ExtractionSourceArchiveProvenanceStatement.__name__.endswith("Statement")
    assert ExtractionSourceArchiveTrustPolicy.__name__.endswith("TrustPolicy")
    assert PrecommittedExtractionSourceArchiveReceipt.__name__.startswith("Precommitted")
    assert callable(build_extraction_source_archive_provenance_statement)
    assert callable(build_extraction_source_archive_trust_policy)
    assert callable(extraction_signed_source_archive_provenance_json_payload)
    assert callable(extraction_source_archive_provenance_statement_bytes)
    assert callable(extraction_source_archive_trust_policy_json_payload)
    assert callable(load_extraction_signed_source_archive_provenance)
    assert callable(load_extraction_source_archive_trust_policy)
    assert callable(verify_precommitted_extraction_source_archive_provenance_for_run)
