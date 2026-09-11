# Data and preregistration integrity contract (v0.14)

Veritas v0.14 adds a provenance-first integrity substrate for registration records, raw-to-analysis lineage, survey response diagnostics, randomization records, and direct E5 data/provenance concerns. The implementation is intentionally conservative: a deviation, undocumented transformation, or suspicious response pattern is not treated as evidence of intent or misconduct.

## Preregistration, PAP, and registry comparison

`RegistrationPlan` supports three explicit registration sources: preregistration, pre-analysis plan (PAP), and registry. Registered items are typed as hypotheses, outcomes, treatments, sample rules, exclusions, transformations, models, or inference rules.

`compare_registration_plan()` compares artifact-derived observed analysis items with the exact registered item they claim to implement. It produces separate states for:

- `MATCH` — normalized observed and registered specifications agree;
- `DEVIATION` — the linked specifications or item types differ;
- `UNDECLARED` — an observed item has no valid linked registered item;
- `UNOBSERVED` — a registered item was not found in the observed analysis artifact;
- `UNVERIFIABLE` — registration identity or observed extraction does not meet the verification gate.

The comparison reports protocol differences. It does not infer whether a difference is justified, intentional, problematic, or disclosed elsewhere; those questions require contextual human review.

## Raw-to-analysis sample lineage

`SampleLineage` binds every sample snapshot to:

- artifact SHA-256;
- row-identity-set SHA-256;
- row count;
- exact source provenance;
- an explicit `artifact_identity_verified` flag.

The lineage itself carries `completeness_verified`. This is deliberately separate from merely having hashes: a cryptographic digest identifies supplied bytes, but it does not prove that those bytes are the independently verified raw/analysis artifact or that the recorded DAG includes every relevant transformation.

`LineageOperation` records exclusions, filters, transformations, merges, and derivations with an evidence hash and optional registered-plan item identity. The lineage is a DAG, each produced snapshot has at most one producer, and invalid mutations are rolled back rather than leaving a partially corrupted graph.

Count semantics fail closed:

- exclusions/filters may not increase the row count;
- ordinary transformations/derivations must preserve the row count;
- merges are represented separately rather than being disguised as transformations.

`find_undocumented_lineage_operations()` identifies exclusion/filter/transformation operations that lack a valid registered-plan link. These are documentation/review concerns, not E5 findings by themselves.

## Survey response-integrity diagnostics

`assess_survey_response_integrity()` is an applicability-gated, multi-signal review module. Supported signal families include long-string behavior, person-total patterns, response time, invariant response patterns, and attention checks.

A signal participates only when it is applicable, has a resolved boolean result, and meets the extraction-confidence gate. Escalation requires at least two **independent signal families** by default. Two variants of the same signal family do not satisfy the independence requirement.

The strongest survey-only output is `REVIEW`. Survey response heuristics never create E5 data/provenance findings on their own.

## Randomization-record and artifact provenance checks

`RandomizationRecord` binds a verified randomization artifact to the unit-universe SHA-256 and treatment-assignment SHA-256, plus algorithm identity and an optional seed commitment. `compare_randomization_record()` compares those identities with the observed analysis assignment.

A randomization mismatch is a direct provenance concern only when the randomization artifact identity is verified and the observed assignment extraction meets the high-confidence gate. Otherwise the result is `UNVERIFIABLE`.

`compare_artifact_identity()` performs exact byte-identity checks against a verified expected artifact hash. `compare_lineage_origin()` checks whether a declared raw sample is actually an ancestor of the analysis sample. A lineage-origin result can be direct evidence only when **both endpoint artifact identities are verified and lineage completeness is independently verified**. If any of those conditions is absent, lineage-origin comparison returns `UNVERIFIABLE` rather than treating graph absence as a contradiction.

## E5 direct data/provenance concern path

`build_e5_data_provenance_check()` can emit `EvidenceGrade.DATA_PROVENANCE_CONCERN` only when at least one direct verified artifact/randomization/lineage identity check is a mismatch. Unverified direct evidence cannot be promoted to E5.

Every E5 finding records:

- the exact provenance concern type and explanation;
- immutable evidence hashes and source provenance;
- `human_review_required: true`;
- `human_review_status: pending`;
- `intent_inference_authorized: false`;
- `production_authorized: false`.

The finding language is limited to an identity/provenance conflict requiring human review. Veritas does not infer cause, intent, fabrication, falsification, or misconduct from the conflict.

## Authority scope

The v0.14 software substrate implements the roadmap's comparison and provenance-control primitives. It does not substitute for access to unavailable raw records, independent human adjudication, institutional investigation, or held-out production certification. Missing artifacts remain neutral/unverifiable rather than adverse evidence.
