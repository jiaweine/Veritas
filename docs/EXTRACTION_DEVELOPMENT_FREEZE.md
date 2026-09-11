# DEVELOPMENT calibration freeze and pre-TEST archive

This document covers the temporal boundary between DEVELOPMENT calibration and held-out TEST execution for the
v0.15 extraction-evidence workflow.

It is intentionally separate from the original pre-TEST witness. The original witness and external handoff are
created before any DEVELOPMENT or TEST predictions exist. They must not be edited later to make DEVELOPMENT
calibration appear precommitted. Instead, after DEVELOPMENT is complete and before any TEST prediction is opened,
create a second repository-side witness/handoff and obtain a second independently archived receipt.

None of the artifacts in this document establish production authority. `production_authorized` remains false.

## Preconditions

Before starting DEVELOPMENT calibration:

- the original v0.15 pre-TEST archive receipt has been obtained from the independently controlled historical
  channel and verified with `verify_extraction_pretest_external_archive_receipt.py`;
- independently reviewed/adjudicated canonical review records exist;
- `build_extraction_split_manifests.py` has produced the canonical DEVELOPMENT and TEST target manifests;
- the frozen evidence plan, pilot threshold policy, execution plan, publication/input bytes, source tree, parser
  registry, numerical runtime, execution command, and external trust material remain unchanged;
- no held-out TEST prediction or TEST outcome has been inspected.

A repository-side verified receipt binding proves only that the supplied receipt binds the supplied bytes and
expected identities. It does not establish independent control or historical-channel semantics by itself.

## 1. Run the complete frozen grid on DEVELOPMENT

Run `scripts/run_extraction_evidence_threshold.py` for every threshold id/value in the frozen evidence plan using
`evidence/splits/development-target-manifest.json`. Do not omit thresholds or add an exploratory threshold.

For each threshold, immediately build the strict execution-attestation archive:

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

Repeat for the complete threshold grid. The attestation builder obtains the numeric threshold from the frozen
evidence plan; it does not accept a caller-supplied threshold value.

## 2. Freeze DEVELOPMENT calibration without TEST input

After all DEVELOPMENT prediction artifacts are present, create the calibration freeze:

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

The command has no TEST-manifest, TEST-prediction, or TEST-metric argument. It mechanically reconstructs reviewed
gold and the DEVELOPMENT split, requires the complete precommitted threshold grid, verifies that each prediction
artifact embeds the correct frozen numeric threshold, recomputes DEVELOPMENT benchmark reports, applies the
already frozen pilot policy, and records the selected threshold.

The archive binds:

- evidence-plan identity and benchmark confidence;
- exact pilot-policy file bytes and semantic policy hash;
- exact DEVELOPMENT prediction bytes and prediction semantics for every threshold;
- benchmark-report hashes and threshold-level aggregate observations;
- the complete DEVELOPMENT selectivity curve;
- the DEVELOPMENT target-manifest semantic hash;
- the selected `FrozenExtractionThreshold` and its semantic hash.

Cold release verification must still recompute these values from primary artifacts. The freeze is a historical
audit artifact, not a substitute for recomputation.

## 3. Bind the frozen decision to the untouched TEST manifest

Before opening any TEST prediction, create the TEST evaluation lock:

```bash
python scripts/build_extraction_test_evaluation_lock.py \
  --development-freeze evidence/calibration/development-calibration-freeze.json \
  --development-manifest evidence/splits/development-target-manifest.json \
  --test-manifest evidence/splits/test-target-manifest.json \
  --output evidence/calibration/test-evaluation-lock.json
```

This command accepts no TEST prediction artifact and no TEST performance value. It requires DEVELOPMENT and TEST
to share the same reviewed-gold identity and article-family split lock, requires their family/target memberships
to be disjoint, and binds the already selected DEVELOPMENT threshold to the exact TEST manifest.

## 4. Build the post-DEVELOPMENT / pre-TEST handoff

Use the verified binding from the original pre-TEST archive as the previous-link input. Include every DEVELOPMENT
prediction and its matching execution attestation:

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

The handoff rejects threshold membership drift, prediction byte/semantic drift, attestation split/threshold/
manifest/prediction drift, a different source commit from the initial archive binding, and any mismatch between
the DEVELOPMENT freeze and TEST evaluation archive.

Its `pretest_witness` is the exact file SHA-256 of `test-evaluation-lock.json`. The handoff records
`executed_v015_development_predictions=true` and `executed_v015_test_predictions=false`.

## 5. Obtain and verify the second independent archive receipt

Send the exact handoff object set to the independently controlled historical archive before any TEST prediction
is opened. The external custodian must issue a receipt with an external timestamp or sequence position and with
its `pretest_witness_sha256` equal to the handoff's TEST-evaluation-lock file hash.

The existing receipt verifier is deliberately reused:

```bash
python scripts/verify_extraction_pretest_external_archive_receipt.py \
  --receipt external/post-development-pretest-receipt.json \
  --handoff external/post-development-pretest-handoff.json \
  --expected-handoff-sha256 '<independently-recorded-handoff-sha256>' \
  --expected-source-commit-sha d6ffdf7debd63281e0db5934e3d4b7ebafb98311 \
  --expected-custodian-identity '<independently-selected-custodian>' \
  --expected-archive-channel-identity '<independently-selected-channel>' \
  --expected-archive-record-id '<independently-selected-record-id>' \
  --output external/post-development-pretest-verified-binding.json
```

Do not copy expected custodian/channel/record context from the receipt being verified. Those expectations must be
selected independently.

A structurally valid receipt and verified binding still do not prove that the named channel was independently
controlled or historically append-only. Those are external governance facts.

## 6. Only now open TEST

Only after the second archive/receipt exists in the independent historical channel may the held-out TEST grid be
executed.

**TEST must not feed back** into threshold selection, the frozen pilot policy, parser routing, promotion logic,
publication/input selection, source commit choice, execution-plan changes, trust-root selection, or trust-policy
construction.

The TEST evaluation lock fixes which DEVELOPMENT-selected threshold is authoritative for the held-out decision.
Running the full TEST grid may still be required for the precommitted evidence report/selectivity curve, but TEST
results cannot change the selected threshold or any upstream design choice.
