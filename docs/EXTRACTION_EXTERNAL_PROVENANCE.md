# Signed external extraction provenance

`AttestedExtractionEvidenceReleaseReceipt` proves that supplied execution objects and canonical prediction-artifact bytes are internally consistent. It does **not** prove that a remote runner actually executed them.

The external-provenance layer adds a cryptographic trust root for that stronger claim while remaining non-production.

## Trust root

`ExtractionExternalTrustRoot` pins:

- issuer identity;
- runner identity;
- repository identity;
- workflow identity;
- a 32-byte Ed25519 public key;
- the `ed25519` algorithm and schema version.

A key generated after seeing benchmark results and then used to self-sign a provenance statement is not an external trust root, even if the Ed25519 signature is mathematically valid.

## Pre-TEST trust policy

For the strongest software-enforced path, build an `ExtractionExternalTrustPolicy` **before TEST**. It binds:

- a policy id;
- the already-frozen `ExtractionEvidencePlan` SHA-256;
- the already-frozen `ExtractionExecutionPlan` SHA-256;
- the exact `ExtractionExternalTrustRoot` SHA-256;
- issuer identity;
- runner identity;
- repository identity;
- workflow identity.

`scripts/build_extraction_external_trust_policy.py` takes the strict evidence-plan JSON emitted by `build_extraction_evidence_plan.py`, the strict execution-plan JSON frozen for the run, the five concrete execution artifacts committed by that plan, and a strict trust-root JSON file. It reconstructs and rehashes both plan archives, independently rehashes the exact input-artifact-manifest/source-tree/parser-registry/numerical-runtime/execution-command bytes, and only then emits the non-production trust-policy JSON artifact and its SHA-256. There are no manual plan-digest inputs on this CLI path.

The trust policy has its own strict UTF-8 JSON loader. Duplicate keys, unknown fields, unsupported versions, non-standard numeric constants, malformed hashes, and production-authority attempts fail closed.

The policy does not create trust merely by existing. Its value is that an independent deployment/CI governance channel can pin one exact root to one exact evidence plan **and one exact execution plan** before TEST. Because policy construction also checks the concrete execution artifacts against that plan, a post-hoc change to those archived bytes cannot silently retain the same precommitment.

In a real deployment, archive the evidence plan, execution plan, five execution artifacts, trust root, and trust policy in the protected configuration/artifact history used to establish pre-TEST timing.

## Signed subject

`ExtractionExternalProvenanceStatement` binds the trusted runner identity to:

- run id and run attempt;
- exact git commit SHA;
- exact `AttestedExtractionEvidenceReleaseReceipt` SHA-256;
- exact `ExtractionExecutionPlan` SHA-256;
- DEVELOPMENT and TEST execution-evidence-set SHA-256 values;
- input-artifact-manifest SHA-256;
- source-tree SHA-256;
- parser-registry SHA-256;
- numerical-runtime SHA-256;
- execution-command SHA-256;
- exact trust-root SHA-256.

The attested receipt itself contains the exact `ExtractionEvidencePlan` SHA-256 copied from the rebuilt base release receipt. Because the external statement signs the entire attested-receipt hash, the signature transitively commits the exact evidence plan. The signed statement also directly commits the exact execution-plan SHA-256 and its five artifact digests.

The statement is encoded as canonical UTF-8 JSON with sorted object keys and compact separators before signing.

Changing the run id, commit, release receipt, evidence plan, execution plan, split execution set, input artifacts, source tree, parser registry, runtime, command, issuer, runner, repository, workflow, or trust root invalidates the signed subject or its precommitted policy binding.

## Verification layers

`verify_external_extraction_provenance()` is the low-level subject verifier. It reconstructs the expected statement from the supplied trusted root, attested release receipt, and execution plan, requires exact equality, then verifies the detached Ed25519 signature.

A successful low-level verification produces `ExternallyVerifiedExtractionEvidenceReceipt`. It remains `production_authorized = false`.

### Run-context verification

A real external-run claim should at minimum use `verify_external_extraction_provenance_for_run()`. The caller must independently supply:

- the expected run id;
- the expected run attempt;
- the expected git commit SHA.

The function requires those values to match the signed statement exactly before performing full subject reconstruction and Ed25519 verification. Its `ExternallyVerifiedExtractionRunReceipt` preserves the verified run, commit, repository, workflow, runner, issuer, trust-root, and underlying verified-evidence receipt identity.

This prevents a historical but otherwise valid signed statement from being silently reused as proof for a different run, rerun attempt, or commit. Expected context must come from the deliberately selected orchestration/deployment run, not simply be copied from the untrusted signed envelope.

### Precommitted run verification

For the strongest path, use `verify_precommitted_external_extraction_provenance_for_run()`. In addition to run-context and Ed25519 checks, it requires:

- the supplied evidence-plan SHA-256 to equal the precommitted trust policy;
- the same evidence-plan SHA-256 to equal the plan hash carried inside the signed attested release receipt;
- the supplied execution plan to hash to the exact execution-plan SHA-256 frozen in the precommitted trust policy;
- the supplied trust-root SHA-256 to equal the precommitted trust policy;
- issuer/runner/repository/workflow identity to equal the policy;
- the complete context-bound run verification to succeed.

The strongest CLI path additionally calls `verify_extraction_execution_plan_artifacts()` before this verifier, so all five execution-plan digests must match the exact archived files supplied to the cold audit.

The resulting `PrecommittedExternalExtractionRunReceipt` explicitly commits the trust-policy, evidence-plan, execution-plan, trust-root, and verified-run receipt hashes. Changing the evidence plan, changing parser/source/runtime/command after the policy was frozen, replacing the signing key/root, or changing trusted runner identity fails closed.

Ed25519 verification is an optional runtime capability. Install `veritas-audit[attestation]` to provide the `cryptography` implementation. CI installs this extra and exercises valid signatures, wrong keys, modified run ids, subject drift, execution-plan drift, archived-artifact byte drift, expected-run/attempt/commit drift, trust-policy/root drift, signed-release evidence-plan drift, and malformed signatures.

## Strict JSON ingress and archived artifact bytes

Real evidence should enter Veritas through strict file loaders:

- `load_extraction_evidence_plan()`;
- `load_extraction_external_trust_root()`;
- `load_extraction_external_trust_policy()`;
- `load_extraction_signed_external_provenance()`;
- `load_extraction_execution_plan()`;
- `load_attested_extraction_evidence_release_receipt()`.

The evidence-plan loader reconstructs the `ExtractionEvidencePlan` and complete threshold grid, recomputes `plan_sha256`, and requires the grid commitment to match. The execution-plan loader reconstructs the exact pre-TEST execution contract and enforces its isolation/security flags. All six loaders require UTF-8 JSON, exact schema keys, supported schema versions, and reject duplicate object keys and non-standard `NaN` / `Infinity` numeric constants.

The five execution-plan commitments are not accepted as opaque hashes on the strongest CLI paths. `extraction_execution_artifact_sha256()` hashes exact files, `build_extraction_execution_plan_from_artifacts()` creates a plan from those files, and `verify_extraction_execution_plan_artifacts()` rehashes them against an existing plan. `scripts/build_extraction_execution_plan.py` is the preferred way to construct the pre-TEST execution-plan JSON.

The stable public import surface for these execution-artifact, execution-evidence, signed-provenance, trust-policy, strict-JSON, and context-bound verification APIs is `veritas.extraction_provenance`.

### File-driven verification

`scripts/verify_extraction_external_provenance.py` provides the strongest archived-evidence verification path without custom Python glue. It requires six strict JSON artifacts:

1. the exact pre-TEST evidence-plan JSON emitted by `build_extraction_evidence_plan.py`;
2. the pretrusted `ExtractionExternalTrustRoot`;
3. the pre-TEST `ExtractionExternalTrustPolicy`;
4. the Ed25519-signed external provenance envelope;
5. the exact `ExtractionExecutionPlan`;
6. the exact `AttestedExtractionEvidenceReleaseReceipt`.

It additionally requires the five concrete archived files named by the execution contract:

1. input-artifact manifest;
2. source-tree artifact/archive;
3. parser-registry artifact;
4. numerical-runtime artifact;
5. execution-command artifact.

The verifier reconstructs the evidence and execution plans, rehashes all five execution artifacts, and requires everything to match the precommitted trust policy and signed subject. The caller separately supplies only the expected run id, run attempt, and git commit SHA; those values are not inferred from the untrusted signed envelope. On success the CLI writes a `PrecommittedExternalExtractionRunReceipt` payload plus its SHA-256; on any artifact-byte, plan, grid, schema, policy, subject, run-context, or signature mismatch it exits non-zero.

This makes a cold-machine audit possible from archived files while preserving the same non-production authority boundary as the Python API.

## What this proves

With a genuinely independently archived pre-TEST trust policy, a pretrusted public key, the five archived execution artifacts, and independently selected expected run context, successful precommitted run verification proves that:

1. the exact evidence plan carried by the signed attested release matches the plan committed by the pre-TEST trust policy;
2. the exact execution plan used by the signed subject matches the execution plan committed by the same pre-TEST policy;
3. all five execution-plan artifact digests match the exact archived files supplied to the policy builder/cold verifier;
4. that policy selected the exact pinned trust root and runner/repository/workflow identity;
5. the holder of the corresponding Ed25519 private key signed the exact execution/release subject;
6. that subject is for the independently expected run id, attempt, and commit;
7. Veritas independently reconstructed the same release/execution subject.

That can support a real external-run provenance claim when the private key is genuinely controlled by the claimed trusted runner or signing service and the plans/root/policy were actually archived before TEST.

It does **not** prove by itself:

- that the policy or artifact archive was historically fixed before TEST unless the external policy channel supplies that history;
- that the key was genuinely controlled by GitHub Actions or any named provider;
- reviewer independence or adjudication;
- untouched TEST status;
- that the publication files referenced by the input-artifact manifest actually match the identities/hashes recorded inside that manifest;
- production hard-finding authority.

Those claims require the corresponding governance or deeper artifact validation. Veritas must not convert a caller-selected self-signed key or caller-created post-hoc policy into institutional trust merely because identity strings contain familiar service names.
