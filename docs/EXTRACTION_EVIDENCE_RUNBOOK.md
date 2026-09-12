# Extraction evidence operations runbook

This runbook turns the remaining real-evidence work in issue #26 into an operator sequence. Repository code can
verify identities, byte commitments, deterministic derivations, and fail-closed relationships; it cannot
manufacture independent humans, historical pre-TEST timing, institutional key ownership, or an untouched TEST
process.

The repository orchestration baseline is now `main`, but the frozen v0.15 execution source commit remains
`d6ffdf7debd63281e0db5934e3d4b7ebafb98311`. **Do not replace the frozen execution source commit with current
`main`** merely because orchestration code was integrated later.

## 0. Authority prerequisites before TEST

Before any held-out TEST outcome is inspected:

- exact sampling-frame, seed, evidence-plan, execution-plan, publication/input, source-tree, parser-registry,
  numerical-runtime, execution-command, and blinded-packet identities must already be fixed under the original
  pre-TEST commitment;
- any external-run trust root and trust policy must already exist in an **independent historical channel before TEST**;
- reviewer A, reviewer B, and the adjudicator must be genuinely independent people/processes. Reviewer IDs are
  **not proof of human independence**;
- expected evidence-run id/attempt/commit and optional source-build run context must come from an independently
  **selected expected run context, not from the signed envelope**;
- `production_authorized` remains false throughout this workflow.

Git history, CI history, signatures, and structurally valid receipts can support the package, but cannot create
those external facts.

## 1. Persist strict reviewer submissions and adjudication

Each reviewer works from the frozen blinded packet without another reviewer's submission or legacy benchmark
values. Persist one strict submission per reviewer and one strict adjudication per target, then build one canonical
review record:

```bash
python scripts/build_extraction_review_record.py \
  --seed-manifest benchmark/extraction/evidence_seed_manifest_v0.15.json \
  --target-id '<target-id>' \
  --kind '<evidence-kind>' \
  --submission evidence/reviews/<target-id>.reviewer-a.json \
  --submission evidence/reviews/<target-id>.reviewer-b.json \
  --adjudication evidence/reviews/<target-id>.adjudication.json \
  --output evidence/review-records/<target-id>.json
```

Archive the review-record SHA-256 with independently maintained reviewer/adjudicator provenance. Do not synthesize
missing reviewers or treat A/B agreement as a substitute for adjudication.

## 2. Derive DEVELOPMENT and TEST membership mechanically

After all records entering locked gold are adjudicated, derive the family split and manifests:

```bash
python scripts/build_extraction_split_manifests.py \
  --sampling-frame benchmark/corpus/evidence_sampling_frame_v0.15.json \
  --seed-manifest benchmark/extraction/evidence_seed_manifest_v0.15.json \
  --evidence-plan benchmark/extraction/evidence_plan_v0.15.json \
  --review-record evidence/review-records/<target-1>.json \
  --review-record evidence/review-records/<target-N>.json \
  --output-dir evidence/splits
```

The derivation records reviewed-gold/split-lock identities, exact manifest bytes, review-record hashes,
assignments, and memberships. Do not hand-author split membership.

## 3. Pin evidence-run trust before TEST

The evidence-run root must already be governed and historically archived outside the evidence run. Build the trust
policy from concrete frozen artifacts:

```bash
python scripts/build_extraction_external_trust_policy.py \
  --policy-id '<policy-id>' \
  --source-commit-sha d6ffdf7debd63281e0db5934e3d4b7ebafb98311 \
  --evidence-plan benchmark/extraction/evidence_plan_v0.15.json \
  --execution-plan benchmark/extraction/extraction_execution_plan_v0.15.json \
  --input-artifact-manifest benchmark/extraction/extraction_input_artifact_manifest_v0.15.json \
  --input-artifact-root evidence/input-artifacts \
  --source-tree evidence/execution/source-tree.tar \
  --parser-registry benchmark/extraction/execution_artifacts_v0.15/parser_registry.json \
  --numerical-runtime benchmark/extraction/execution_artifacts_v0.15/numerical_runtime.json \
  --execution-command benchmark/extraction/execution_artifacts_v0.15/execution_command.json \
  --trust-root external/evidence-run-trust-root.json \
  --output external/evidence-run-trust-policy.json
```

For a stronger commit-to-source-archive claim, separately precommit the source-archive trust root/policy and
preserve independently governed builder history. A signature proves possession of a key, not independent control
or workflow semantics.

## 4. Run every precommitted threshold on DEVELOPMENT

Run the full frozen grid against the mechanically derived DEVELOPMENT manifest. The threshold runner sees the
blinded packet and split manifest, not reviewed gold:

```bash
python scripts/run_extraction_evidence_threshold.py \
  --input-artifact-manifest benchmark/extraction/extraction_input_artifact_manifest_v0.15.json \
  --input-artifact-root evidence/input-artifacts \
  --review-packet evidence/review-packets/reviewer-a.review-packet.json \
  --review-packet-sha256 '<precommitted-packet-sha256>' \
  --target-manifest evidence/splits/development-target-manifest.json \
  --paper-artifact '<paper-id>=<artifact-id>' \
  --threshold-id nc-005 \
  --threshold 0.005 \
  --output evidence/predictions/development/nc-005.json
```

Repeat for every frozen threshold. Build one strict execution-attestation archive for each prediction artifact:

```bash
python scripts/build_extraction_execution_attestation.py \
  --execution-plan benchmark/extraction/extraction_execution_plan_v0.15.json \
  --evidence-plan benchmark/extraction/evidence_plan_v0.15.json \
  --target-manifest evidence/splits/development-target-manifest.json \
  --prediction-artifact evidence/predictions/development/nc-005.json \
  --execution-id '<development-execution-id-nc-005>' \
  --threshold-id nc-005 \
  --output evidence/attestations/development/nc-005.json
```

The attestation builder recovers the numeric threshold from the frozen grid rather than accepting a retyped value.

## 5. Freeze DEVELOPMENT and lock TEST before touching TEST outcomes

Create the DEVELOPMENT-only calibration freeze:

```bash
python scripts/freeze_extraction_development_threshold.py \
  --sampling-frame benchmark/corpus/evidence_sampling_frame_v0.15.json \
  --seed-manifest benchmark/extraction/evidence_seed_manifest_v0.15.json \
  --evidence-plan benchmark/extraction/evidence_plan_v0.15.json \
  --pilot-threshold-policy benchmark/extraction/pretest_pilot_threshold_policy_v0.15.json \
  --review-record evidence/review-records/<target-1>.json \
  --review-record evidence/review-records/<target-N>.json \
  --development-manifest evidence/splits/development-target-manifest.json \
  --development-prediction nc-005 evidence/predictions/development/nc-005.json \
  --development-prediction nc-010 evidence/predictions/development/nc-010.json \
  --development-prediction nc-020 evidence/predictions/development/nc-020.json \
  --output evidence/calibration/development-calibration-freeze.json
```

Then bind the frozen decision to the untouched TEST manifest. This command accepts no TEST prediction or TEST
performance value:

```bash
python scripts/build_extraction_test_evaluation_lock.py \
  --development-freeze evidence/calibration/development-calibration-freeze.json \
  --development-manifest evidence/splits/development-target-manifest.json \
  --test-manifest evidence/splits/test-target-manifest.json \
  --output evidence/calibration/test-evaluation-lock.json
```

Before TEST is opened, build a second external handoff chaining to the original verified pre-TEST archive binding:

```bash
python scripts/build_extraction_development_freeze_external_handoff.py \
  --source-commit-sha d6ffdf7debd63281e0db5934e3d4b7ebafb98311 \
  --initial-archive-binding external/initial-pretest-verified-binding.json \
  --pilot-threshold-policy benchmark/extraction/pretest_pilot_threshold_policy_v0.15.json \
  --development-freeze evidence/calibration/development-calibration-freeze.json \
  --development-manifest evidence/splits/development-target-manifest.json \
  --test-evaluation-lock evidence/calibration/test-evaluation-lock.json \
  --test-manifest evidence/splits/test-target-manifest.json \
  --development-prediction nc-005 evidence/predictions/development/nc-005.json \
  --development-prediction nc-010 evidence/predictions/development/nc-010.json \
  --development-prediction nc-020 evidence/predictions/development/nc-020.json \
  --development-attestation nc-005 evidence/attestations/development/nc-005.json \
  --development-attestation nc-010 evidence/attestations/development/nc-010.json \
  --development-attestation nc-020 evidence/attestations/development/nc-020.json \
  --output external/post-development-pretest-handoff.json
```

The independent archive must preserve those exact bytes and issue a second receipt before TEST. Verify it using
independently selected custodian/channel/record expectations, never values copied from the receipt itself.

**TEST must not feed back** into threshold selection, parser routing, promotion logic, publication/input selection,
source commit choice, execution-plan changes, trust-root selection, or trust-policy construction.

See `docs/EXTRACTION_DEVELOPMENT_FREEZE.md` for the detailed temporal boundary.

## 6. Run the untouched TEST grid

Only after the DEVELOPMENT freeze, TEST evaluation lock, and second independent archive/receipt exist, run the
same complete threshold grid against `evidence/splits/test-target-manifest.json`. Archive exact canonical TEST
prediction bytes and one execution attestation per threshold. TEST may populate the precommitted report; it may
not change upstream choices.

## 7. Build a release bundle mechanically bound to the frozen calibration chain

Release assembly must not retype policy values or numeric thresholds. Supply only threshold IDs, execution IDs,
and prediction paths; the builder recovers policy and threshold values from the frozen artifacts:

```bash
python scripts/build_extraction_release_bundle.py \
  --review-record evidence/review-records/<target-1>.json \
  --review-record evidence/review-records/<target-N>.json \
  --release-artifact-root evidence/predictions \
  --input-artifact-manifest benchmark/extraction/extraction_input_artifact_manifest_v0.15.json \
  --input-artifact-root evidence/input-artifacts \
  --evidence-plan benchmark/extraction/evidence_plan_v0.15.json \
  --pilot-threshold-policy benchmark/extraction/pretest_pilot_threshold_policy_v0.15.json \
  --development-freeze evidence/calibration/development-calibration-freeze.json \
  --development-manifest evidence/splits/development-target-manifest.json \
  --test-evaluation-lock evidence/calibration/test-evaluation-lock.json \
  --test-manifest evidence/splits/test-target-manifest.json \
  --development-run nc-005 '<execution-id>' development/nc-005.json \
  --development-run nc-010 '<execution-id>' development/nc-010.json \
  --development-run nc-020 '<execution-id>' development/nc-020.json \
  --test-run nc-005 '<execution-id>' test/nc-005.json \
  --test-run nc-010 '<execution-id>' test/nc-010.json \
  --test-run nc-020 '<execution-id>' test/nc-020.json \
  --output evidence/release/release-evidence-bundle.json \
  --calibration-binding-output evidence/release/release-calibration-binding.json
```

The builder derives `ExtractionThresholdPolicy` from the DEVELOPMENT freeze and numeric thresholds from the
precommitted evidence-plan grid. There are no release-stage `--min-selective-coverage`,
`--min-accepted-full-accuracy`, `--max-critical-family-wrong-accept-upper-bound`, or caller-supplied run-threshold
arguments.

The separate strict `release-calibration-binding.json` commits both semantic and exact-file SHA-256 identities for
the release bundle, pilot policy, DEVELOPMENT freeze, DEVELOPMENT manifest, TEST evaluation archive/lock, and TEST
manifest. It also requires the DEVELOPMENT prediction bytes/semantics in the release artifact root to be exactly
the predictions committed by the pre-TEST DEVELOPMENT freeze.

## 8. Verify the release/calibration binding, then cold-rebuild external provenance

The calibration preflight is mandatory for the v0.15 bound-release path. Run it on the independent verifier before
external provenance verification:

```bash
python scripts/verify_extraction_release_calibration_binding.py \
  --release-bundle evidence/release/release-evidence-bundle.json \
  --release-calibration-binding evidence/release/release-calibration-binding.json \
  --release-artifact-root evidence/predictions \
  --evidence-plan benchmark/extraction/evidence_plan_v0.15.json \
  --pilot-threshold-policy benchmark/extraction/pretest_pilot_threshold_policy_v0.15.json \
  --development-freeze evidence/calibration/development-calibration-freeze.json \
  --development-manifest evidence/splits/development-target-manifest.json \
  --test-evaluation-lock evidence/calibration/test-evaluation-lock.json \
  --test-manifest evidence/splits/test-target-manifest.json \
  --output evidence/release/release-calibration-verification.json
```

Do not proceed unless that command succeeds. It recalculates the binding from the exact supplied bytes rather than
trusting hashes copied from the sidecar.

Then perform the existing cold rebuild and external-provenance verification:

```bash
python scripts/verify_extraction_external_provenance.py \
  --sampling-frame benchmark/corpus/evidence_sampling_frame_v0.15.json \
  --seed-manifest benchmark/extraction/evidence_seed_manifest_v0.15.json \
  --evidence-plan benchmark/extraction/evidence_plan_v0.15.json \
  --release-bundle evidence/release/release-evidence-bundle.json \
  --release-artifact-root evidence/predictions \
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
  --output evidence/release/cold-verification.json
```

Cold reconstruction remains authoritative: it reopens canonical prediction artifacts, recomputes reports,
re-derives the DEVELOPMENT threshold, and reconstructs the TEST lock. The binding preflight additionally proves
that those reconstructed inputs are the exact policy/freeze/lock/manifests assembled around the release bundle.
For a stronger source-archive claim, also provide the complete optional source-archive verification chain; partial
chains must fail closed.

## 9. What closes issue #26

Repository-side success is necessary but not sufficient. The milestone closes only when archived evidence supports
the external facts software cannot create: genuine reviewer/adjudicator independence, historical pre-TEST trust
and post-DEVELOPMENT freeze existence, untouched TEST handling, independently controlled expected run context,
any claimed institutional key/workflow ownership, and the complete cold-verifiable evidence package.

A green CI run, a Git commit, or a structurally valid receipt alone is not that evidence.
