# Post-verification external archive handoff

The v0.15 bound cold verifier closes the repository-side gap between the release calibration sidecar,
the release execution-attestation sidecar, cold reconstruction, and the precommitted external provenance
signature. A separate question remains after that verification succeeds: which exact bytes should an
independently controlled custodian preserve so that the final bound verification can later be replayed?

`build_extraction_postverification_external_handoff.py` answers only that packaging question.

## Temporal and authority boundary

This handoff is created **after** `verify_bound_extraction_external_provenance.py` succeeds. It is therefore a
new post-verification archive event. It must not be described as though the original external Ed25519 statement
had historically signed the later release calibration or release execution sidecars.

The original signed statement directly commits the attested release receipt, execution plan and execution-set
identities, execution/publication artifact identities, source commit, run context, and trusted runner identity.
It does not directly commit the later release sidecar files. The post-verification handoff preserves the original
signed provenance unchanged and packages it together with those sidecars and the final bound-verification result.

A repository-generated handoff is not an external archive receipt, timestamp, proof of independent control,
proof of immutable historical custody, proof of reviewer independence, proof of untouched TEST handling, proof
of institutional key/workflow ownership, or production authorization.

## Canonical operator command

Use the same frozen inputs supplied to the authoritative bound cold verifier and add its exact output:

```bash
python scripts/build_extraction_postverification_external_handoff.py \
  --bound-verification evidence/release/bound-cold-verification.json \
  --sampling-frame benchmark/corpus/evidence_sampling_frame_v0.15.json \
  --seed-manifest benchmark/extraction/evidence_seed_manifest_v0.15.json \
  --evidence-plan benchmark/extraction/evidence_plan_v0.15.json \
  --release-bundle evidence/release/release-evidence-bundle.json \
  --release-artifact-root evidence/predictions \
  --release-calibration-binding evidence/release/release-calibration-binding.json \
  --pilot-threshold-policy benchmark/extraction/pretest_pilot_threshold_policy_v0.15.json \
  --development-freeze evidence/calibration/development-calibration-freeze.json \
  --development-manifest evidence/splits/development-target-manifest.json \
  --test-evaluation-lock evidence/calibration/test-evaluation-lock.json \
  --test-manifest evidence/splits/test-target-manifest.json \
  --release-execution-binding evidence/release/release-execution-binding.json \
  --development-attestation nc-005 evidence/attestations/development/nc-005.json \
  --development-attestation nc-010 evidence/attestations/development/nc-010.json \
  --development-attestation nc-020 evidence/attestations/development/nc-020.json \
  --test-attestation nc-005 evidence/attestations/test/nc-005.json \
  --test-attestation nc-010 evidence/attestations/test/nc-010.json \
  --test-attestation nc-020 evidence/attestations/test/nc-020.json \
  --trust-root external/evidence-run-trust-root.json \
  --trust-policy external/evidence-run-trust-policy.json \
  --signed-provenance external/signed-evidence-run-provenance.json \
  --execution-plan benchmark/extraction/extraction_execution_plan_v0.15.json \
  --input-artifact-manifest benchmark/extraction/extraction_input_artifact_manifest_v0.15.json \
  --input-artifact-root evidence/input-artifacts \
  --source-tree evidence/execution/source-tree.tar \
  --parser-registry benchmark/extraction/execution_artifacts_v0.15/parser_registry.json \
  --numerical-runtime benchmark/extraction/execution_artifacts_v0.15/numerical_runtime.json \
  --execution-command benchmark/extraction/execution_artifacts_v0.15/execution_command.json \
  --attested-release evidence/release/attested-release.json \
  --expected-run-id '<independently-selected-run-id>' \
  --expected-run-attempt '<independently-selected-run-attempt>' \
  --expected-commit-sha d6ffdf7debd63281e0db5934e3d4b7ebafb98311 \
  --output external/postverification-bound-release-handoff.json
```

If the stronger source-archive chain was part of the bound verification, provide the complete source-archive
trust root, trust policy, signed provenance, expected run id, and expected run attempt together. Partial source-
archive verification inputs fail closed.

## What the builder verifies

The builder does not merely hash whatever files it is handed. Before writing a handoff it:

- strictly loads the canonical bound-verification artifact and requires the non-production verified state;
- reconstructs and verifies the release calibration binding from the frozen policy, DEVELOPMENT freeze, split
  manifests, TEST evaluation lock, release bundle, and exact prediction bytes;
- reconstructs and verifies the release execution binding from the execution plan, DEV/TEST manifests, exact
  prediction bytes, and every per-threshold execution attestation;
- verifies the execution-plan publication/source/parser/runtime/command artifacts;
- cold-rebuilds the attested release from the sampling frame, seed, evidence plan, release bundle, and prediction
  artifacts and requires equality with the archived attested release;
- verifies the precommitted external trust policy, external signature, and independently selected expected run
  context;
- requires the final bound-verification result to match those recomputed identities exactly.

Only after those checks does it construct the archive object set.

## Stable archive object-set identity

Every archived object receives a stable POSIX `archive_name`. The handoff records the operator's source path for
retrieval, but `archive_object_set_sha256` is computed only from the sorted stable archive name, exact SHA-256,
and size of every object. Moving the same evidence package to another working directory therefore does not change
the object-set identity.

The object set contains the final bound-verification JSON, both release sidecars, release bundle, attested release,
all frozen calibration and split artifacts, all DEV/TEST execution attestations, all canonical prediction files,
the original trust root/policy/signed provenance, execution plan and execution artifacts, the source-tree archive,
and every publication/input artifact referenced by the frozen input manifest.

## External completion condition

The generated payload intentionally has:

- `independent_archive_receipt_present=false`;
- `independent_control_established=false`;
- `historical_channel_semantics_established=false`;
- `production_authorized=false`.

Those values may only be superseded by genuine evidence from the independently controlled external custodian.
Issue #26 remains open until that evidence and the other external milestone facts actually exist.
