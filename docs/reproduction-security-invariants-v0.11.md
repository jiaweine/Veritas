# Reproduction security invariants (v0.11 hardening stack)

This document freezes the security invariants implemented by the experimental reproduction control plane. It describes fail-closed engineering behavior. It is **not** a production-certification claim and does not by itself complete the v0.13 reproducibility-artifacts milestone.

## 1. Control JSON is strict

Security-sensitive reproduction JSON is decoded as UTF-8 only. Duplicate object keys are rejected. `NaN`, `Infinity`, and `-Infinity` are rejected. Booleans are never accepted as integers or numeric results. Version numbers and exit codes must be real integers, not Python/JSON booleans.

Single-target and target-set packet/execution contracts reject undeclared security-critical fields and validate hashes, commit identities, target identities, review flags, output bindings, and execution-security flags before comparison.

## 2. Sealed target secrets are exact and typed

Private reproduction targets are reconstructed only after exact schema validation. Unknown target, reported-number, and source fields are rejected. Reported values and bounding-box components must be finite numbers. `decimals` must be a non-negative integer or null. Comparison operators and materiality must be supported typed values.

The target-set root requires `schema_version: 1`. The legacy single-target v1 form may omit the version for compatibility, but a supplied version is strictly typed and must equal `1`.

## 3. Result artifacts are answer-only and artifact-bound

Blind CodeAgent output and strict target-set output use an exact root shape containing `schema_version` and `targets`. Each result row contains only a target identity and one finite numeric value. Unknown target IDs, duplicate target IDs, boolean values, non-finite values, and extra result claims are rejected.

Every accepted reproduced cell is bound to the SHA-256 of the exact output artifact bytes that produced it.

## 4. Blind agent visibility is minimized

Independent-reimplementation backends receive a leak-safe `AgentTaskView`, not the full sealed `CodeAgentTask`. Publication provenance, source URIs, reported numeric answers, comparison feedback, internal claim IDs, task IDs, and method-spec IDs are excluded from the model-visible projection. Only required output target IDs/metrics, method choices, leak-reviewed artifact identities, and explicitly permitted execution controls remain.

The boundary revalidates runtime types so truthy strings such as `"false"` cannot masquerade as security booleans. Independent blind reproduction requires network access to remain disabled and rejects disallowed artifact roles.

## 5. Dispatch authorization is typed and pre-egress

Remote coding-agent dispatch is restricted to public artifacts with explicit model-egress authorization. Confidential-compute dispatch requires an explicit approval flag and rejects unknown-sensitivity artifacts. Authorization flags must be real booleans; truthy strings do not grant access.

These checks occur before artifact/task content is exposed to an external coding-agent backend.

## 6. Frozen execution evidence is exact

Execution attestations are bound to the locked task, generated code, sandbox policy, input artifact hashes, output artifact hashes, environment identity, frozen workspace, and successful exit status. Network-disabled and read-only-input requirements are rechecked against the locked sandbox policy.

At authority boundaries, exit codes and sandbox resource limits must be real integers and execution-policy fields must be real booleans. Python's `True == 1` and `False == 0` behavior is never accepted as attestation evidence.

## 7. E4 comparisons are canonical, not caller-authored

The E4-capable report path does not trust a caller-provided `MATCH`/`MISMATCH` status, reported interval, or custom comparison tolerance. It reconstructs reproduced cells from finite values bound to attested output hashes, reruns the canonical Veritas comparator using the sealed target set, and requires the supplied comparison records to exactly equal that canonical result.

Missing comparisons may not carry hidden numeric values, intervals, or output identities. Directly constructed `ReproductionTarget` objects are runtime-validated before commitment checking so non-finite values, boolean numeric values, invalid decimals, untyped comparison operators, or untyped materiality cannot bypass the strict JSON loaders.

## 8. Independent actors are identity-separated

For an E4-capable path, the executor, method-fidelity verifier, and artifact-identity verifier must not reuse the CodeAgent identity. The method-fidelity verifier must cover every method field whose value was actually supplied, including supplied optional fields, and must leave no mismatched or unresolved choices.

Artifact identity verification must cover exactly the locked task artifact set.

## 9. Authority remains fail-closed

Answer-free single-target and target-set certificates remain descriptive and keep `production_authorized: false` and `e4_authorized: false`. Experimental CodeAgent attempts cannot promote themselves to E4 through the ordinary report builder.

E4-capable construction is reserved for the fully attested reproduction report path and is additionally bound to an authority compatible with the locked reproduction mode. Even that engineering path remains experimental until the broader reproducibility-artifact milestone, real execution infrastructure, held-out validation, governance, and production-certification requirements are satisfied.

## 10. Change rule

A future change that weakens any invariant above must be explicit, versioned where externally serialized, covered by regression tests, and reviewed as an authority/security change rather than treated as a parser convenience or compatibility cleanup.
