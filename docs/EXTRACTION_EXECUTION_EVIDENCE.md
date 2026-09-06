# Extraction execution evidence contract

The extraction evidence workflow has two internal software receipts plus an optional signed external-provenance layer.

1. `ExtractionEvidenceReleaseReceipt` proves that the precommitted sampling/seed/split/threshold chain is internally consistent and that benchmark reports are recomputed from exact `ExtractionPrediction` / `ExtractionResolution` provenance.
2. `AttestedExtractionEvidenceReleaseReceipt` additionally binds that prediction provenance to persisted canonical prediction-artifact bytes and a frozen execution contract.
3. The external-provenance layer can additionally bind the attested release to a pretrusted Ed25519 runner identity and independently selected run context.

All receipts remain explicitly non-production.

## Publication-byte manifest

The strongest execution path starts from the exact publication/input files, not from caller-authored digests.

`ExtractionInputArtifactManifest` is strict, non-production JSON. Each entry contains:

- a unique `artifact_id`;
- a unique safe POSIX `relative_path`;
- exact file SHA-256;
- exact `size_bytes`.

`scripts/build_extraction_input_artifact_manifest.py` builds this manifest by opening the files below an explicit root and hashing their exact bytes. Absolute paths, `..`, empty path segments, backslashes, symbolic-link roots/components, duplicate IDs/paths, malformed hashes, unsupported schemas, duplicate JSON keys, unknown fields, and production-authority drift fail closed.

`verify_extraction_input_artifact_manifest()` independently reopens every referenced regular file below the configured root and requires both its size and SHA-256 to match. A changed publication file therefore fails even when the archived manifest, execution plan, trust policy, and signature themselves have not changed.

This proves byte identity for the archived files supplied to the verifier. It does not by itself prove URL provenance, licensing, publisher authenticity, or that an independently named institution originally supplied those bytes.

## Pre-TEST execution plan

Before DEVELOPMENT/TEST execution evidence is accepted, archive an `ExtractionExecutionPlan` that commits:

- exact strict input-artifact-manifest bytes;
- exact source-tree artifact/archive bytes;
- parser-registry artifact bytes;
- numerical-runtime artifact bytes;
- execution-command artifact bytes;
- network disabled;
- source mount read-only;
- no mounted credentials.

Do not hand-author those five digests for the evidence run. `scripts/build_extraction_execution_plan.py` requires the strict input-artifact manifest, its publication root, and the four other execution artifacts. It first verifies every publication/input file against the manifest and then hashes the exact manifest/source-tree/parser-registry/runtime/command bytes into the plan.

For a directory-like source tree, first create the deployment's deterministic archive and pass the exact archive file to the builder. The contract hashes bytes, not an ambient mutable directory.

`verify_extraction_execution_plan_artifacts()` repeats the same checks for an existing plan: strict-load and verify the publication manifest against its root, then rehash all five execution artifacts. Both `scripts/build_extraction_external_trust_policy.py` and `scripts/verify_extraction_external_provenance.py` invoke this check before policy construction or signed-run verification.

## Canonical prediction artifact

`extraction_prediction_artifact_bytes()` is the canonical persisted representation accepted by the attested release path. It serializes the ordered `ExtractionPrediction` tuple as deterministic UTF-8 JSON with sorted object keys, no formatting-dependent whitespace, and exact prediction/resolution/candidate/source values.

The attestation stores two commitments:

- `prediction_artifact_sha256`: exact bytes;
- `prediction_semantics_sha256`: target-id-sorted prediction semantics.

An attested release supplies the exact artifact bytes. The software re-renders the canonical artifact from the bound observation predictions and requires byte-for-byte equality.

## Per-threshold execution attestation

Every DEVELOPMENT and TEST threshold observation requires one `ExtractionExecutionEvidence` entry. Its `ExtractionExecutionAttestation` binds the execution-plan SHA-256, split, threshold id/value, exact derived split-target manifest, exact canonical prediction artifact, semantic prediction digest, successful exit code, and isolation controls.

The attested release rejects missing or duplicate threshold evidence, changed execution plans, wrong split membership, post-hoc threshold changes, target-manifest drift, prediction-artifact drift, semantic drift, failed executions, and weakened isolation controls.

## Receipt and precommit chain

`build_attested_extraction_evidence_release_receipt()` first rebuilds the ordinary release receipt and then validates complete DEVELOPMENT/TEST execution evidence. The final attested receipt commits the base release receipt, exact evidence-plan SHA-256, execution-plan SHA-256, and both split execution-evidence-set hashes.

The pre-TEST external trust policy separately commits the exact evidence plan, exact execution plan, trust root, and runner/repository/workflow identities. Because policy construction verifies the publication root and all execution artifacts before committing the execution plan, the strongest chain is:

`publication bytes → strict input-artifact manifest → execution artifact bytes → execution plan → pre-TEST trust policy → attested release → signed run → independently selected run context`.

Changing a publication file, manifest byte, source-tree archive, parser registry, runtime artifact, command artifact, execution plan, evidence plan, prediction artifact, threshold, target manifest, or signed subject breaks the corresponding check.

## Archive inventory for cold verification

The strongest cold-verification path uses **seven strict JSON artifacts**:

1. evidence-plan JSON;
2. input-artifact-manifest JSON;
3. trust-root JSON;
4. trust-policy JSON;
5. signed-provenance JSON;
6. execution-plan JSON;
7. attested-release JSON.

It additionally requires:

- every publication/input file referenced by the input-artifact manifest under the configured input root;
- the exact source-tree artifact/archive;
- the exact parser-registry artifact;
- the exact numerical-runtime artifact;
- the exact execution-command artifact;
- independently selected expected run id, run attempt, and git commit SHA.

## Authority boundary

This software can prove that the publication files supplied to verification match their strict manifest, that the manifest and four other execution artifacts match the frozen execution plan, and that the resulting plan/release subject matches a precommitted policy and valid signature.

It still does not manufacture institutional trust, reviewer independence, adjudication, untouched TEST history, publisher/origin authenticity, historical pre-TEST timing, or production hard-finding authority. Those remain external governance/evidence requirements.
