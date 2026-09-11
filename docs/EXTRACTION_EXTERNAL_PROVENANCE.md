# Signed external extraction provenance

`AttestedExtractionEvidenceReleaseReceipt` proves internal consistency of a release/execution evidence chain. The external-provenance layer adds cryptographic trust roots for stronger real-run claims while remaining non-production.

The strongest archived path does **not** trust an attested-release JSON merely because it is signed. A cold verifier rebuilds that receipt from source evidence first and only then verifies the precommitted policy, independently selected run context, and Ed25519 signature.

## Evidence-run trust root and pre-TEST policy

`ExtractionExternalTrustRoot` pins issuer, runner, repository, workflow, a 32-byte Ed25519 public key, algorithm, and schema version. A key generated after seeing benchmark results is not an external trust root merely because its signature verifies.

For the evidence execution, build an `ExtractionExternalTrustPolicy` **before TEST**. It commits:

- exact `ExtractionEvidencePlan` SHA-256;
- exact `ExtractionExecutionPlan` SHA-256;
- exact source commit SHA;
- exact trust-root SHA-256;
- issuer/runner/repository/workflow identities.

`scripts/build_extraction_external_trust_policy.py` does not accept manually typed plan digests. It strict-loads the evidence plan and execution plan, verifies the strict input-artifact manifest against the actual publication/input files under `--input-artifact-root`, rehashes the manifest plus source-tree/parser-registry/numerical-runtime/execution-command artifacts, validates the explicit source commit format, loads the trust root, and only then emits the trust policy.

The policy therefore freezes the exact evidence plan, checked execution artifact set, source commit, and trust identity before TEST. The external historical channel is still responsible for proving that this policy/root/archive genuinely existed before held-out TEST outcomes were inspected.

## Optional trusted source-archive build relation

The ordinary evidence-run chain deliberately treats `source_commit_sha` and `source_tree_sha256` as two commitments that the trusted evidence runner signs together. That alone does **not** prove that the archive was actually produced from the named Git commit.

Deployments that need the stronger commit-to-archive claim can add a second, independently archived build-provenance chain:

- `ExtractionSourceArchiveTrustPolicy` precommits the exact execution plan, source commit, source-tree digest, builder trust root, and builder issuer/runner/repository/workflow identity;
- `ExtractionSourceArchiveProvenanceStatement` binds an independently identified build run/attempt to that exact commit, execution plan, and source-tree digest;
- `ExtractionSignedSourceArchiveProvenance` carries the Ed25519 signature from the trusted build/archive identity;
- `verify_precommitted_extraction_source_archive_provenance_for_run()` requires policy, trust root, exact execution plan/source-tree commitment, independently supplied build run context, independently supplied expected commit, reconstructed subject, and signature to agree;
- `PrecommittedExtractionSourceArchiveReceipt` records the verified build relation as a separate non-production receipt.

`scripts/build_extraction_source_archive_trust_policy.py` strict-loads the execution plan and builder trust root, rehashes the exact `--source-tree` bytes against the plan, validates the source commit, and emits the pre-TEST policy. It does not accept a manually typed source-tree digest.

This second chain is optional because its authority is external: a signature only proves that the holder of the pretrusted builder key signed the exact relation. The historical/governance layer must still establish that the key and workflow really belonged to the intended trusted build/archive process and that the policy/root existed before TEST. Software does not manufacture that institutional trust.

The source-archive trust root may be operationally distinct from the evidence-run trust root. The verifier does not require distinct keys because some deployments may intentionally use one pretrusted provider, but independence of the expected build-run context from the untrusted signed envelope is mandatory.

## Publication/input source closure

`ExtractionInputArtifactManifest` identifies the concrete publication/input byte universe with unique artifact IDs, safe relative paths, exact byte sizes, and SHA-256 values. `verify_extraction_input_artifact_manifest()` reopens every file and fails on path traversal, symbolic links, missing/non-regular files, size drift, or byte drift.

The cold release path also calls `verify_extraction_release_source_artifacts()`. Every review-record source, reviewer-submission source, adjudication source, and every accepted prediction-candidate source must name an `artifact_id` present in that already verified input manifest. This prevents the publication archive from being a disconnected set of correctly hashed files while the actual release evidence cites a different source universe.

Byte/source closure does not establish publisher, URL, DOI, or license authenticity. Those remain external provenance claims.

## Recomputable release archive

`ExtractionReleaseEvidenceBundle` is the cold-rebuild input for release semantics. It contains complete `ExtractionReviewRecord` values, the DEVELOPMENT threshold-selection policy, and complete DEVELOPMENT/TEST threshold-run descriptors.

Each threshold-run descriptor names a canonical prediction-artifact file by safe relative path plus its threshold id/value and execution id. `load_extraction_prediction_artifact()` strict-parses every prediction/resolution/candidate/source object and requires the exact file bytes to equal `extraction_prediction_artifact_bytes()` for the reconstructed predictions. Formatting drift, duplicate keys, non-standard numeric constants, unsupported decisions, malformed typed fields, unsafe paths, and non-canonical bytes fail closed.

`rebuild_attested_extraction_evidence_release_receipt_from_archive()` reconstructs the release rather than trusting caller-supplied aggregate hashes. It:

1. rebuilds the evidence plan from the supplied sampling-frame bytes, seed-manifest bytes, threshold grid, review protocol, split salt/fractions, and benchmark confidence, and requires equality with the archived plan;
2. rebuilds locked gold from the complete review records;
3. rebuilds the deterministic article-family split lock and DEVELOPMENT/TEST target manifests;
4. loads every canonical prediction artifact over the complete precommitted threshold grid;
5. re-runs `evaluate_extraction_benchmark()` against the exact split gold and precommitted confidence level;
6. rebuilds `ExtractionThresholdObservation` values and per-threshold `ExtractionExecutionEvidence`;
7. deterministically selects the DEVELOPMENT threshold under the archived policy;
8. rebuilds the TEST seal/evaluation lock and both coverage-selectivity curves;
9. invokes the canonical `build_attested_extraction_evidence_release_receipt()` path.

The cold verifier requires the rebuilt attested receipt to equal the separately archived attested-release JSON exactly. A changed review/adjudication identity, target/source locator, threshold policy, prediction artifact, prediction semantics, execution id, split membership, benchmark result, frozen threshold, TEST lock, or curve therefore cannot be hidden behind an old signed receipt.

## Evidence-run signed subject

`ExtractionExternalProvenanceStatement` binds the trusted evidence runner identity to run id/attempt, exact Git commit SHA, attested release, execution plan, DEV/TEST execution sets, input-artifact manifest, source tree, parser registry, numerical runtime, execution command, repository/workflow identities, and trust root.

The attested receipt carries the exact evidence-plan SHA-256. The signed statement directly carries the execution-plan SHA-256 and its execution-artifact commitments. Changing the rebuilt release, plans, run context, publication-manifest digest, source/runtime/command digests, runner identity, or trust root invalidates subject reconstruction or signature verification.

## Verification layers

`verify_external_extraction_provenance()` is the low-level evidence-run subject/signature verifier.

`verify_external_extraction_provenance_for_run()` additionally requires independently supplied expected run id, run attempt, and commit SHA, preventing a historical valid signature from silently standing in for a different run.

`verify_precommitted_external_extraction_provenance_for_run()` adds the pre-TEST policy checks. It requires policy evidence plan = rebuilt signed-release evidence plan, policy execution plan = actual execution plan, and **policy source commit = signed statement commit = independently supplied expected commit**, plus exact trust root/runner identity. `PrecommittedExternalExtractionRunReceipt` records the policy, both plans, source commit, trust root, and verified-run commitment.

`verify_precommitted_extraction_source_archive_provenance_for_run()` is a separate optional verifier for the stronger build relation. It requires source-archive policy commit = independently expected commit = signed build statement commit, policy source tree = exact execution-plan source tree = signed build statement source tree, exact builder trust root/identity, independently selected build run id/attempt, and a valid Ed25519 signature.

## Archived cold-verification inventory

`scripts/verify_extraction_external_provenance.py` always requires these ten top-level archives:

1. sampling-frame source JSON;
2. seed-manifest source JSON;
3. evidence-plan JSON;
4. release-evidence-bundle JSON;
5. input-artifact-manifest JSON;
6. evidence-run trust-root JSON;
7. evidence-run trust-policy JSON;
8. signed evidence-run provenance JSON;
9. execution-plan JSON;
10. attested-release JSON.

It additionally requires every publication/input file under `--input-artifact-root`, every canonical DEVELOPMENT/TEST prediction artifact under `--release-artifact-root`, the exact source-tree/parser-registry/numerical-runtime/execution-command artifacts, and independently selected expected evidence-run id/attempt/commit.

To verify the stronger source-archive build relation in the same cold run, provide **all five** additional inputs together:

- `--source-archive-trust-root`;
- `--source-archive-trust-policy`;
- `--signed-source-archive-provenance`;
- `--expected-source-archive-run-id`;
- `--expected-source-archive-run-attempt`.

The expected commit is the same independently supplied `--expected-commit-sha` used by the evidence-run chain. Supplying only part of the source-archive chain fails closed. Supplying none leaves the existing evidence-run verification semantics unchanged and does not claim commit-to-archive derivation.

The evidence-plan, input-manifest, release-bundle, trust, signed, execution-plan, attested-release, source-archive policy/signed envelope, and prediction-artifact ingress paths fail closed on their defined schema/type/canonicalization constraints. Sampling-frame and seed-manifest loaders additionally bind their exact source bytes into the evidence plan.

## File-driven cold verification

The verifier performs the mandatory chain in order:

1. load the sampling-frame and seed source archives;
2. load the evidence plan and threshold grid, then reconstruct the same plan from those source archives;
3. load the release bundle and canonical prediction artifacts;
4. load and byte-verify the input-artifact manifest against every publication/input file;
5. rehash the input manifest and four other raw execution artifacts against the execution plan;
6. require all review/adjudication/prediction source artifact IDs to belong to the verified publication/input manifest;
7. rebuild gold, split lock, DEVELOPMENT/TEST manifests, benchmark reports, observations, execution evidence, frozen threshold, TEST seal/lock, curves, and the final attested release;
8. require the separately archived attested-release JSON to equal that rebuilt receipt;
9. require evidence plan, execution plan, source commit, trust root, and runner identity to match the pre-TEST evidence-run policy;
10. reconstruct the signed evidence-run subject from the **rebuilt** release;
11. require independently selected evidence-run id/attempt/commit to match;
12. verify the evidence-run Ed25519 signature;
13. emit a non-production `PrecommittedExternalExtractionRunReceipt`, plus release-bundle and rebuilt-attested-release SHA-256 values.

When all optional source-archive inputs are supplied, the verifier then:

14. strict-loads the source-archive builder root, pre-TEST policy, and signed build provenance;
15. requires their execution-plan, commit, source-tree, and builder-identity commitments to match the already byte-verified execution plan and independently expected commit;
16. requires the independently supplied build run id/attempt to match the signed build statement;
17. reconstructs the exact build subject and verifies its Ed25519 signature;
18. emits a non-production `PrecommittedExtractionSourceArchiveReceipt` and its SHA-256 alongside the ordinary run receipt.

A one-byte publication, prediction, or source-tree artifact change therefore fails before the stronger receipt can be accepted, even if old receipt/policy/signature JSON files were left untouched.

## What successful verification proves

With a genuinely pre-TEST archived evidence-run policy/root/artifact set and independently selected run context, mandatory cold verification proves that:

1. supplied sampling/seed source archives reproduce the exact precommitted evidence plan;
2. every publication/input file matches the strict input-artifact manifest;
3. all cited review/adjudication/accepted-prediction sources belong to that verified input universe;
4. the exact manifest and four other execution artifacts match the frozen execution plan;
5. supplied review records and canonical prediction artifacts mechanically rebuild the same gold/split/calibration/TEST/curve/execution-evidence chain and exact attested release that was archived and signed;
6. evidence plan, execution plan, and source commit match the pre-TEST evidence-run policy;
7. the policy selected the exact evidence-run trust root and runner/repository/workflow identity;
8. the holder of the corresponding Ed25519 private key signed the exact rebuilt release/execution subject;
9. the signed subject matches independently expected evidence-run id, attempt, and commit.

If the optional source-archive chain also succeeds under a genuinely pretrusted builder root/policy and independently selected build context, the additional receipt proves that the holder of that builder key signed the exact relation **expected commit → exact execution-plan/source-tree artifact** for the independently identified build run.

It still does **not** by itself prove:

- that any policy/root/archive was historically fixed before TEST without an external history source;
- that a named provider actually controlled either private key;
- that the trusted builder workflow really performed the claimed Git checkout/archive procedure unless that workflow identity and its semantics are independently governed/audited;
- that a publication file came from the claimed publisher/URL or has the claimed license;
- that reviewer identities are genuinely independent humans rather than merely distinct IDs in the archive;
- untouched TEST history outside the independently maintained experiment/archive history;
- production hard-finding authority.

Those remain external governance/evidence requirements. The stable public import surface for release rebuild, source binding, evidence-run provenance, and source-archive provenance APIs is `veritas.extraction_provenance`.
