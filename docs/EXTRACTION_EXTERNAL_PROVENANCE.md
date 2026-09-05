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
- the exact `ExtractionExternalTrustRoot` SHA-256;
- issuer identity;
- runner identity;
- repository identity;
- workflow identity.

`scripts/build_extraction_external_trust_policy.py` takes an evidence-plan SHA-256 plus a strict trust-root JSON file and emits an immutable, non-production trust-policy JSON artifact and its SHA-256. Archive that policy through the independent channel used to establish trust.

The trust policy has its own strict UTF-8 JSON loader. Duplicate keys, unknown fields, unsupported versions, non-standard numeric constants, malformed hashes, and production-authority attempts fail closed.

The policy does not create trust merely by existing. Its value is that an independent deployment/CI governance channel can pin one exact root to one exact evidence plan **before** TEST, and Veritas can later mechanically reject a different root or plan.

In a real deployment, archive the trust root and trust policy in a protected configuration repository, CI/deployment policy, transparency log, institutional key registry, or equivalent independent channel.

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

The attested receipt itself contains the exact `ExtractionEvidencePlan` SHA-256 copied from the rebuilt base release receipt. Because the external statement signs the entire attested-receipt hash, the signature transitively commits the exact evidence plan without relying on a separate unsigned plan parameter.

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
- the supplied trust-root SHA-256 to equal the precommitted trust policy;
- issuer/runner/repository/workflow identity to equal the policy;
- the complete context-bound run verification to succeed.

The resulting `PrecommittedExternalExtractionRunReceipt` commits the trust-policy, evidence-plan, trust-root, and verified-run receipt hashes. Changing the evidence plan, replacing the signing key/root, or changing trusted runner identity after the policy was frozen fails closed. A policy hash and a release subject can no longer merely carry unrelated but individually valid plan digests.

Ed25519 verification is an optional runtime capability. Install `veritas-audit[attestation]` to provide the `cryptography` implementation. CI installs this extra and exercises valid signatures, wrong keys, modified run ids, subject drift, execution-plan drift, expected-run/attempt/commit drift, trust-policy/root drift, signed-release evidence-plan drift, and malformed signatures.

## Strict JSON ingress

Real evidence should enter Veritas through strict file loaders:

- `load_extraction_external_trust_root()`;
- `load_extraction_external_trust_policy()`;
- `load_extraction_signed_external_provenance()`.

They require UTF-8 JSON, exact schema keys, supported schema versions, and reject duplicate object keys and non-standard `NaN` / `Infinity` numeric constants. Unknown fields are rejected rather than ignored.

The stable public import surface for execution evidence, signed provenance, trust-policy precommitment, strict JSON ingress, and context-bound verification is `veritas.extraction_provenance`.

## What this proves

With a genuinely independently archived pre-TEST trust policy, a pretrusted public key, and independently selected expected run context, successful precommitted run verification proves that:

1. the exact evidence plan carried by the signed attested release matches the plan committed by the pre-TEST trust policy;
2. that policy selected the exact pinned trust root and runner/repository/workflow identity;
3. the holder of the corresponding Ed25519 private key signed the exact execution/release subject;
4. that subject is for the independently expected run id, attempt, and commit;
5. Veritas independently reconstructed the same release/execution subject.

That can support a real external-run provenance claim when the private key is genuinely controlled by the claimed trusted runner or signing service and the policy was actually archived before TEST.

It does **not** prove by itself:

- that the policy was historically archived before TEST unless the external policy channel supplies that history;
- that the key was genuinely controlled by GitHub Actions or any named provider;
- reviewer independence or adjudication;
- untouched TEST status;
- correctness of publication bytes in the input-artifact manifest;
- production hard-finding authority.

Those claims require the corresponding governance or external evidence. Veritas must not convert a caller-selected self-signed key or caller-created post-hoc policy into institutional trust merely because identity strings contain familiar service names.
