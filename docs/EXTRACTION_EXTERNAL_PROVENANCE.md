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

The public key must be trusted **before** inspecting TEST results. A key generated after seeing benchmark results and then used to self-sign a provenance statement is not an external trust root, even if the Ed25519 signature is mathematically valid.

In a real deployment, pin the trust root through an independent policy channel such as repository/environment configuration, CI policy, a protected configuration repository, transparency log, or institutional key registry. Archive the exact trust-root JSON bytes and their repository/history location used for the evidence run.

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

The statement is encoded as canonical UTF-8 JSON with sorted object keys and compact separators before signing.

Changing the run id, commit, release receipt, execution plan, split execution set, input artifacts, source tree, parser registry, runtime, command, issuer, runner, repository, workflow, or trust root invalidates the signature or subject binding.

## Verification

`verify_external_extraction_provenance()` performs two independent checks:

1. reconstruct the expected statement from the supplied trusted root, attested release receipt, and execution plan and require exact equality;
2. verify the detached Ed25519 signature against the pinned public key.

A successful verification produces `ExternallyVerifiedExtractionEvidenceReceipt`, which commits the attested release receipt, execution plan, trust root, signed statement, and signed envelope hashes. It remains `production_authorized = false`.

Ed25519 verification is an optional runtime capability. Install `veritas-audit[attestation]` to provide the `cryptography` implementation. CI installs this extra and exercises valid signatures, wrong keys, modified run ids, subject drift, execution-plan drift, and malformed signatures.

## Strict JSON ingress

Real trust roots and signed provenance envelopes should enter Veritas through:

- `load_extraction_external_trust_root()`;
- `load_extraction_signed_external_provenance()`.

These loaders require UTF-8 JSON, exact schema keys, supported schema versions, and reject duplicate object keys and non-standard `NaN` / `Infinity` numeric constants. Unknown fields are rejected instead of being silently ignored.

The serializer helpers `extraction_external_trust_root_payload()` and `extraction_signed_external_provenance_payload()` provide the corresponding schema-shaped objects for archival.

## What this proves

With a genuinely pretrusted public key, successful verification proves that the holder of the corresponding private key signed the exact execution/release subject that Veritas independently reconstructed.

That can support a real external-run provenance claim when the private key is controlled by the claimed trusted runner or signing service.

It does **not** prove by itself:

- that the key was genuinely controlled by GitHub Actions or any named provider;
- that the public key was pinned before TEST rather than chosen post hoc;
- reviewer independence or adjudication;
- untouched TEST status;
- correctness of publication bytes in the input-artifact manifest;
- production hard-finding authority.

Those claims require the corresponding governance or external evidence. Veritas must not convert a caller-selected self-signed key into institutional trust merely because `issuer` contains a familiar service name.
