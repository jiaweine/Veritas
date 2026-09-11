# Extraction execution evidence contract

The extraction evidence workflow has two internal software receipts plus an optional signed external-provenance layer.

1. `ExtractionEvidenceReleaseReceipt` proves that the precommitted sampling/seed/split/threshold chain is internally consistent and that benchmark reports are recomputed from exact `ExtractionPrediction` / `ExtractionResolution` provenance.
2. `AttestedExtractionEvidenceReleaseReceipt` additionally binds that prediction provenance to persisted canonical prediction-artifact bytes and a frozen execution contract.
3. The external-provenance layer can additionally bind the rebuilt attested release to a pretrusted Ed25519 runner identity and independently selected run context.

All receipts remain explicitly non-production.

## Publication-byte manifest

The strongest execution path starts from the exact publication/input files, not from caller-authored digests.

`ExtractionInputArtifactManifest` is strict, non-production JSON. Each entry contains a unique `artifact_id`, unique safe POSIX `relative_path`, exact file SHA-256, and exact `size_bytes`.

`scripts/build_extraction_input_artifact_manifest.py` builds this manifest by opening the files below an explicit root and hashing their exact bytes. Absolute paths, `..`, empty path segments, backslashes, symbolic-link roots/components, duplicate IDs/paths, malformed hashes, unsupported schemas, duplicate JSON keys, unknown fields, and production-authority drift fail closed.

`verify_extraction_input_artifact_manifest()` independently reopens every referenced regular file below the configured root and requires both size and SHA-256 to match. A changed publication file therefore fails even when old manifest/plan/policy/signature JSON files are unchanged.

`verify_extraction_release_source_artifacts()` closes the next link: every review record, reviewer submission, adjudication, and accepted prediction candidate must cite an `artifact_id` from that verified manifest. The publication archive cannot be a correctly hashed but unrelated set of files.

This proves byte identity and source-universe closure for the archive supplied to the verifier. It does not by itself prove URL, publisher, DOI, license, or institutional origin authenticity.

## Pre-TEST execution plan

Before DEVELOPMENT/TEST execution evidence is accepted, archive an `ExtractionExecutionPlan` that commits exact bytes for:

- the strict input-artifact manifest;
- source-tree artifact/archive;
- parser-registry artifact;
- numerical-runtime artifact;
- execution-command artifact;

and requires network disabled, source mount read-only, and no mounted credentials.

Do not hand-author those five digests for the evidence run. `scripts/build_extraction_execution_plan.py` requires the strict input-artifact manifest, its publication root, and the four other execution artifacts. It first verifies every publication/input file against the manifest and then hashes the exact manifest/source-tree/parser-registry/runtime/command bytes into the plan.

For a directory-like source tree, first create the deployment's deterministic archive and pass that exact archive file. The contract hashes bytes, not an ambient mutable directory.

`verify_extraction_execution_plan_artifacts()` repeats the same checks for an existing plan. Both policy construction and cold verification invoke it before accepting the execution plan.

## Source commit precommitment

The external trust policy additionally commits an exact 40-character source commit SHA before TEST. The strongest run verifier requires:

`policy source commit = signed statement commit = independently supplied expected commit`.

This prevents post-policy commit substitution. It does **not** mechanically prove that an arbitrary separately archived source-tree file was generated from that Git commit merely because both are frozen; deployments requiring that stronger statement must establish the commit/archive relationship in their trusted build or source-archive process.

## Canonical prediction artifacts

`extraction_prediction_artifact_bytes()` is the canonical persisted representation for an ordered `ExtractionPrediction` tuple. It uses deterministic UTF-8 JSON with sorted keys, compact separators, and exact prediction/resolution/candidate/source values.

Each execution attestation commits both exact prediction-artifact bytes and target-id-sorted prediction semantics. `load_extraction_prediction_artifact()` reconstructs typed predictions from archive and requires the exact file bytes to equal the canonical serialization. Added whitespace, reordered/non-canonical encoding, malformed values, duplicate keys, or semantic drift fail closed.

## Recomputable release evidence

`ExtractionReleaseEvidenceBundle` contains the raw release-side material needed for a cold rebuild:

- complete review records, including reviewer A/B submissions and adjudication;
- DEVELOPMENT threshold-selection policy;
- DEVELOPMENT threshold-run descriptors;
- TEST threshold-run descriptors.

Each run descriptor names a canonical prediction artifact and carries threshold id/value plus execution id. The release artifact root is path-confined and rejects symbolic-link traversal.

`rebuild_attested_extraction_evidence_release_receipt_from_archive()` does not trust aggregate report or receipt hashes. Starting from the archived sampling-frame source, seed-manifest source, evidence plan/grid, release bundle, prediction artifacts, and execution plan, it mechanically rebuilds:

1. the evidence plan and verifies it against the sampling/seed source bytes;
2. locked gold from concrete review records;
3. deterministic article-family split lock;
4. exact DEVELOPMENT and TEST target manifests;
5. every threshold's predictions and benchmark report via `evaluate_extraction_benchmark()`;
6. threshold observations and per-threshold execution evidence;
7. deterministic DEVELOPMENT threshold selection;
8. TEST seal and TEST evaluation lock;
9. DEVELOPMENT and TEST coverage-selectivity curves;
10. the canonical `AttestedExtractionEvidenceReleaseReceipt`.

The cold verifier requires this rebuilt receipt to equal the separately archived attested-release JSON exactly before any signature is accepted. Reviewer/adjudicator drift, source-locator drift, prediction drift, report drift, split drift, policy drift, execution-id drift, frozen-threshold drift, TEST-lock drift, or curve drift therefore cannot hide behind an old signed summary.

## Per-threshold execution attestation

Every DEVELOPMENT and TEST threshold observation requires one `ExtractionExecutionEvidence` entry. Its `ExtractionExecutionAttestation` binds the execution-plan SHA-256, split, threshold id/value, exact derived split-target manifest, exact canonical prediction artifact, semantic prediction digest, successful exit code, and isolation controls.

The attested release rejects missing or duplicate threshold evidence, changed execution plans, wrong split membership, post-hoc threshold changes, target-manifest drift, prediction-artifact drift, semantic drift, failed executions, and weakened isolation controls.

## Strongest archived chain

The strongest software-verifiable chain is now:

`sampling/seed source bytes → evidence plan → review records + canonical prediction artifacts → rebuilt gold/splits/reports/calibration/TEST/curves/execution evidence → rebuilt attested release`

and, in parallel:

`publication bytes → strict input-artifact manifest → release source closure + execution artifact bytes → execution plan`.

Those meet at:

`pre-TEST trust policy (evidence plan + execution plan + source commit + trust root) → signed rebuilt release/run subject → independently selected run context`.

Changing any bound source, review, prediction, execution artifact, plan, policy, run context, or signature breaks the corresponding check.

## Archive inventory for cold verification

The top-level cold-verification inputs are:

1. sampling-frame source JSON;
2. seed-manifest source JSON;
3. evidence-plan JSON;
4. release-evidence-bundle JSON;
5. input-artifact-manifest JSON;
6. trust-root JSON;
7. trust-policy JSON;
8. signed-provenance JSON;
9. execution-plan JSON;
10. attested-release JSON.

It additionally requires every publication/input file under the input root, every canonical DEVELOPMENT/TEST prediction artifact under the release-artifact root, the source-tree/parser-registry/numerical-runtime/execution-command artifacts, and independently selected expected run id/attempt/commit.

## Authority boundary

This software can prove that the supplied source archives reproduce the precommitted evidence plan; that publication files match their manifest; that release evidence actually cites that verified input universe; that raw review and prediction evidence reconstructs the exact attested release; that execution artifacts match the frozen execution plan; and that the rebuilt release/execution subject matches the precommitted policy, independently selected run context, and valid Ed25519 signature.

It still cannot manufacture genuine human reviewer independence, external adjudicator independence, untouched TEST history, publisher/origin authenticity, historical pre-TEST timing, institutional key control, source-archive/Git-commit correspondence outside the trusted archive process, or production hard-finding authority. Those remain external governance/evidence requirements.
