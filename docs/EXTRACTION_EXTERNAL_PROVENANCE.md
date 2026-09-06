# Signed external extraction provenance

`AttestedExtractionEvidenceReleaseReceipt` proves internal consistency of the supplied release/execution objects. The external-provenance layer adds a cryptographic trust root for a stronger real-run claim while remaining non-production.

## Trust root and pre-TEST policy

`ExtractionExternalTrustRoot` pins issuer, runner, repository, workflow, a 32-byte Ed25519 public key, algorithm, and schema version. A key generated after seeing benchmark results is not an external trust root merely because its signature verifies.

For the strongest software-enforced path, build an `ExtractionExternalTrustPolicy` **before TEST**. It commits:

- exact `ExtractionEvidencePlan` SHA-256;
- exact `ExtractionExecutionPlan` SHA-256;
- exact trust-root SHA-256;
- issuer/runner/repository/workflow identities.

`scripts/build_extraction_external_trust_policy.py` does not accept manually typed plan digests. It strict-loads the evidence plan and execution plan, verifies the strict input-artifact manifest against the actual publication/input files under `--input-artifact-root`, rehashes the manifest plus source-tree/parser-registry/numerical-runtime/execution-command artifacts, loads the trust root, and only then emits the trust policy.

The policy therefore commits an execution plan whose artifact digests were mechanically checked against concrete archived bytes at policy-construction time. The external historical channel is still responsible for proving that this policy/root/archive actually existed before held-out TEST outcomes were inspected.

## Signed subject

`ExtractionExternalProvenanceStatement` binds the trusted runner identity to run id/attempt, exact git commit SHA, attested release, execution plan, DEV/TEST execution sets, input-artifact manifest, source tree, parser registry, numerical runtime, execution command, repository/workflow identities, and trust root.

The attested receipt carries the exact evidence-plan SHA-256. The signed statement directly carries the execution-plan SHA-256 and its execution-artifact commitments. Changing the release, plans, run context, publication-manifest digest, source/runtime/command digests, runner identity, or trust root invalidates subject reconstruction or signature verification.

## Verification layers

`verify_external_extraction_provenance()` is the low-level subject/signature verifier.

`verify_external_extraction_provenance_for_run()` additionally requires independently supplied expected run id, run attempt, and commit SHA, preventing a historical valid signature from silently standing in for a different run.

`verify_precommitted_external_extraction_provenance_for_run()` adds the pre-TEST trust-policy checks: the policy must match the exact evidence plan, exact execution plan, trust root, and runner/repository/workflow identity before the context-bound signature is accepted. `PrecommittedExternalExtractionRunReceipt` records both plan hashes, policy/root identity, and the verified-run receipt commitment.

The strongest CLI path performs another layer before these cryptographic checks: `verify_extraction_execution_plan_artifacts()` strict-loads the input-artifact manifest, verifies every referenced publication/input file by `size_bytes` and SHA-256, and then rehashes all five execution artifacts against the execution plan.

## Strict JSON ingress

The cold-verification archive has **seven strict JSON artifacts**:

1. `ExtractionEvidencePlan` archive;
2. `ExtractionInputArtifactManifest` archive;
3. `ExtractionExternalTrustRoot` archive;
4. `ExtractionExternalTrustPolicy` archive;
5. `ExtractionSignedExternalProvenance` archive;
6. `ExtractionExecutionPlan` archive;
7. `AttestedExtractionEvidenceReleaseReceipt` archive.

Relevant loaders are:

- `load_extraction_evidence_plan()`;
- `load_extraction_input_artifact_manifest()`;
- `load_extraction_external_trust_root()`;
- `load_extraction_external_trust_policy()`;
- `load_extraction_signed_external_provenance()`;
- `load_extraction_execution_plan()`;
- `load_attested_extraction_evidence_release_receipt()`.

These paths require UTF-8 JSON, exact schema keys, supported schemas, and reject duplicate object keys and non-standard `NaN` / `Infinity` constants. The input-artifact manifest additionally enforces unique artifact IDs/paths, safe relative paths, exact file size/hash, regular-file roots, and no symbolic-link traversal.

`scripts/build_extraction_input_artifact_manifest.py` is the intended builder for publication/input identity. `scripts/build_extraction_execution_plan.py` then verifies that manifest against the actual publication root before creating the execution plan.

## File-driven cold verification

`scripts/verify_extraction_external_provenance.py` consumes the seven strict JSON artifacts above. It also requires:

- `--input-artifact-root`, containing the exact publication/input files referenced by the manifest;
- exact source-tree artifact/archive;
- exact parser-registry artifact;
- exact numerical-runtime artifact;
- exact execution-command artifact;
- independently selected expected run id, run attempt, and git commit SHA.

The verifier performs this chain in order:

1. strict-load the evidence plan and all trust/signed/execution receipts;
2. strict-load the input-artifact manifest;
3. verify every publication/input file's safe path, size, and SHA-256;
4. rehash the input manifest and four other raw execution artifacts against the execution plan;
5. require both plans and trust identity to match the pre-TEST trust policy;
6. require the signed subject to reconstruct exactly;
7. require expected run id/attempt/commit to match;
8. verify the Ed25519 signature;
9. emit a non-production `PrecommittedExternalExtractionRunReceipt` plus its SHA-256.

A one-byte publication change therefore fails before the signature can be accepted, even if the archived manifest, execution plan, policy, and signed envelope were left untouched.

## What successful verification proves

With a genuinely pre-TEST archived policy/root/artifact set and independently selected run context, successful cold verification proves that:

1. every publication/input file supplied to the audit matches the strict input-artifact manifest by path, size, and SHA-256;
2. the exact manifest and four other execution artifacts match the frozen execution plan;
3. the execution plan and evidence plan match the pre-TEST trust policy;
4. the policy selected the exact trust root and runner/repository/workflow identity;
5. the holder of the corresponding Ed25519 private key signed the exact reconstructed release/execution subject;
6. the subject matches the independently expected run id, attempt, and commit.

It does **not** by itself prove:

- that the archive/policy was historically fixed before TEST without an external history source;
- that a named provider actually controlled the private key;
- that a publication file came from the claimed publisher/URL or has the claimed license;
- reviewer independence or adjudication;
- untouched TEST history;
- production hard-finding authority.

Those remain external governance/evidence requirements. The stable public import surface for these APIs is `veritas.extraction_provenance`.
