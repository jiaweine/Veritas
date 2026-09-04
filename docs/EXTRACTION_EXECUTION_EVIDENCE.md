# Extraction execution evidence contract

The extraction evidence workflow has two internal software receipts plus an optional signed external-provenance layer.

1. `ExtractionEvidenceReleaseReceipt` proves that the precommitted sampling/seed/split/threshold chain is internally consistent and that benchmark reports are recomputed from exact `ExtractionPrediction` / `ExtractionResolution` provenance.
2. `AttestedExtractionEvidenceReleaseReceipt` additionally binds that prediction provenance to persisted canonical prediction-artifact bytes and a frozen execution contract.
3. `ExternallyVerifiedExtractionEvidenceReceipt`, from `extraction_external_provenance.py`, can additionally bind the attested release to an Ed25519-signed trusted-runner statement when the public key is genuinely pretrusted.

All receipts remain explicitly non-production.

## Pre-TEST execution plan

Before DEVELOPMENT/TEST execution evidence is accepted, archive an `ExtractionExecutionPlan` that commits:

- exact input-artifact manifest SHA-256;
- exact source-tree SHA-256;
- parser-registry SHA-256;
- numerical-runtime SHA-256;
- execution-command SHA-256;
- network disabled;
- source mount read-only;
- no mounted credentials.

The plan is fail-closed: unsafe isolation flags, malformed hashes, unsupported schema versions, or any production-authority flag are rejected.

The input-artifact manifest is intentionally separate from the sampling-frame manifest. Sampling-frame URLs identify candidate papers; execution evidence must identify the exact bytes that were actually supplied to the parser run.

## Canonical prediction artifact

`extraction_prediction_artifact_bytes()` is the only canonical persisted representation accepted by the attested release path. It serializes the ordered `ExtractionPrediction` tuple as strict deterministic UTF-8 JSON with:

- `schema_version = 1`;
- sorted JSON object keys;
- no formatting-dependent whitespace;
- exact prediction/resolution/candidate/source values.

The attestation stores two commitments:

- `prediction_artifact_sha256`: exact bytes, so formatting/order changes are visible;
- `prediction_semantics_sha256`: target-id-sorted prediction semantics, so semantically equivalent ordering can be distinguished from actual prediction drift.

An attested release supplies the exact artifact bytes. The software re-renders the canonical artifact from the bound observation predictions and requires byte-for-byte equality.

## Per-threshold execution attestation

Every DEVELOPMENT and TEST threshold observation requires one `ExtractionExecutionEvidence` entry. Its `ExtractionExecutionAttestation` binds:

- unique execution id;
- exact execution-plan SHA-256;
- DEVELOPMENT or TEST split;
- exact threshold id/value;
- exact derived split-target manifest SHA-256;
- exact canonical prediction-artifact SHA-256;
- exact semantic prediction SHA-256;
- successful exit code;
- disabled network;
- read-only source mount;
- no mounted credentials.

The attested release rejects missing or duplicate threshold evidence, changed execution plans, wrong split membership, post-hoc threshold changes, target-manifest drift, artifact-byte drift, semantic prediction drift, failed executions, and weakened isolation controls.

## Receipt chain

`build_attested_extraction_evidence_release_receipt()` first rebuilds the ordinary `ExtractionEvidenceReleaseReceipt`. It then validates all DEVELOPMENT and TEST execution evidence against the exact observations and deterministically derived target manifests. The final receipt commits:

- base release-receipt SHA-256;
- execution-plan SHA-256;
- DEVELOPMENT execution-evidence-set SHA-256;
- TEST execution-evidence-set SHA-256.

Changing any underlying prediction artifact, execution identity, threshold, target manifest, or execution-plan commitment changes or invalidates the attested receipt.

## Signed external trust root

For a stronger real-run provenance claim, Veritas now provides:

- `ExtractionExternalTrustRoot`;
- `ExtractionExternalProvenanceStatement`;
- `ExtractionSignedExternalProvenance`;
- `verify_external_extraction_provenance()`;
- strict UTF-8 JSON loaders for archived trust-root and signed-provenance manifests.

The signed statement covers the exact attested-release receipt, execution plan, DEV/TEST execution sets, git commit, run id/attempt, input-artifact manifest, source tree, parser registry, numerical runtime, execution command, repository/workflow/runner identity, and trust-root SHA-256. Ed25519 verification is available through the optional `veritas-audit[attestation]` dependency.

This only becomes an **external** trust root when the public key itself was pinned independently before TEST. A caller-generated key pair and self-signed statement are cryptographically valid but are not third-party or institutional provenance. See `docs/EXTRACTION_EXTERNAL_PROVENANCE.md`.

## Authority boundary

The ordinary and attested contracts prove consistency of supplied execution evidence objects and exact persisted prediction bytes. The signed external-provenance layer can additionally prove that the holder of a genuinely pretrusted Ed25519 private key signed the exact reconstructed execution/release subject.

None of these layers, by themselves, prove that a familiar issuer name owns a caller-supplied key. Real deployments must establish the public-key trust anchor through an independent CI/deployment policy, protected configuration, transparency log, institutional key registry, or equivalent mechanism before TEST.

Likewise, execution or signed provenance does not create reviewer independence, adjudication, untouched TEST status, correctness of the publication bytes in an input-artifact manifest, or production hard-finding authority. Those remain separate governance requirements.
