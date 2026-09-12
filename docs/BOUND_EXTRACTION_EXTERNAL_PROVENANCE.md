# Bound extraction external-provenance verification

The v0.15 bound-release path must use `scripts/verify_bound_extraction_external_provenance.py` for final cold verification.

`verify_extraction_external_provenance.py` remains available as a compatibility verifier for older unbound archives. A successful result from that older entrypoint is **not** the v0.15 bound-release final verification artifact because it does not consume the release calibration/execution binding sidecars.

## Why the bound verifier exists

The release workflow now creates two exact sidecars:

- `release-calibration-binding.json`, which binds the release bundle to the frozen pilot policy, DEVELOPMENT calibration freeze, DEVELOPMENT manifest, TEST evaluation archive/lock, TEST manifest, and frozen DEVELOPMENT prediction identities;
- `release-execution-binding.json`, which binds the release bundle and execution plan to every DEVELOPMENT/TEST execution attestation and its exact prediction bytes/semantics.

Running those preflight CLIs separately and later invoking the older cold verifier leaves a time-of-check/time-of-use gap: files could be changed after a preflight succeeds. The bound verifier therefore reloads and reconstructs both bindings in the same process that performs the cold rebuild and external signature verification.

## Required final verification

A final v0.15 bound-release verification supplies all calibration and execution inputs again, including every per-threshold attestation:

```bash
python scripts/verify_bound_extraction_external_provenance.py \
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
  --output evidence/release/bound-cold-verification.json
```

The expected run id, attempt, and commit remain independently selected expectations. They must not be copied from the signed envelope merely to make verification pass.

## Fail-closed order

The bound verifier performs these checks before writing any output:

1. strict-load the release bundle, frozen calibration artifacts, split manifests, execution plan, both sidecars, and all execution attestations;
2. reconstruct and compare the release calibration binding from the exact supplied bytes;
3. reconstruct and compare the release execution binding from the exact supplied bytes and prediction artifacts;
4. verify execution-plan artifact bytes and publication/input-artifact bytes;
5. cold-rebuild the attested extraction release from primary release artifacts and require exact agreement with the archived attested release;
6. verify the precommitted external trust policy, signature, and independently selected run context;
7. if source-archive provenance is requested, require the complete optional source-archive chain and verify it too.

The final JSON commits the semantic and exact-file SHA-256 identities of both release bindings in addition to the rebuilt attested release and external provenance receipt.

## Authority boundary

This verifier closes a repository-side consistency/TOCTOU gap. It does **not** prove that reviewers or adjudicators were independent people, that a trust root was independently governed before TEST, that an execution id corresponds to an independently controlled real-world run, that TEST was historically untouched, or that an institution owned the signing key/workflow. It also grants no production authority: `production_authorized` remains false.
