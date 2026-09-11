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
  numerical-runtime, execution-command, and blinded packet identities must already be fixed under the original
  pre-TEST commitment;
- any external-run trust root and trust policy must already exist in an independent historical channel before TEST;
- any stronger commit-to-source-archive claim needs its separately pretrusted builder root/policy and preserved
  builder history;
- reviewer A, reviewer B, and the adjudicator must be genuinely independent people/processes. Reviewer IDs are not proof of human independence;
- expected evidence-run id/attempt/commit and optional build-run id/attempt must come from an independently
  selected expected run context, not from the signed envelope;
- `production_authorized` remains false throughout this workflow.

Repository Git history, CI history, signatures, and structurally valid receipts can support the package, but are
not substitutes for those external facts.

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

Archive the review-record SHA-256 alongside independently maintained reviewer/adjudicator provenance. Do not
synthesize missing reviewers or treat A/B agreement as a substitute for adjudication.

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

The command writes `development-target-manifest.json`, `test-target-manifest.json`, and
`split-derivation.json`. The derivation records reviewed-gold/split-lock identities, exact manifest file hashes,
review-record hashes, assignments, and memberships. Do not hand-author split membership.

## 3. Pin evidence-run trust before TEST

The evidence-run root supplied here must already be governed and historically archived outside the evidence run.
Build the policy from concrete artifacts:

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

Archive policy bytes and the printed SHA-256 through the independent historical channel before TEST.

For a stronger commit-to-source-archive claim, precommit the separate builder policy before TEST:

```bash
python scripts/build_extraction_source_archive_trust_policy.py \
  --policy-id '<source-archive-policy-id>' \
  --source-commit-sha d6ffdf7debd63281e0db5934e3d4b7ebafb98311 \
  --execution-plan benchmark/extraction/extraction_execution_plan_v0.15.json \
  --source-tree evidence/execution/source-tree.tar \
  --trust-root external/source-archive-trust-root.json \
  --output external/source-archive-trust-policy.json
```

A valid signature proves only that the holder of the pretrusted key signed the exact relation. External governance
must still establish who controlled that key and what the trusted workflow actually did.

## 4. Run every precommitted threshold on DEVELOPMENT

The threshold runner accepts a blinded packet and a derived split manifest. It does not read reviewed gold:

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

Repeat for the complete frozen grid. For every prediction artifact, archive the strict execution attestation:

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

The attestation builder recovers the numeric threshold from the frozen grid. It does not accept a caller-supplied
numeric threshold.

## 5. Freeze DEVELOPMENT and lock TEST before touching TEST outcomes

Evaluate the complete DEVELOPMENT grid, under the already frozen pilot policy, without providing any TEST
prediction or metric:

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

This command mechanically rebuilds reviewed gold and the DEVELOPMENT split, requires every precommitted threshold,
checks the threshold embedded in every prediction resolution, recomputes reports, applies the frozen policy, and
writes the DEVELOPMENT-only selected threshold, observations, report hashes, prediction byte/semantic hashes, and
selectivity curve.

Then bind that frozen decision to the untouched TEST manifest:

```bash
python scripts/build_extraction_test_evaluation_lock.py \
  --development-freeze evidence/calibration/development-calibration-freeze.json \
  --development-manifest evidence/splits/development-target-manifest.json \
  --test-manifest evidence/splits/test-target-manifest.json \
  --output evidence/calibration/test-evaluation-lock.json
```

The lock command accepts no TEST prediction or TEST performance value.

Historical timing requires one more external archive event. Build the post-DEVELOPMENT / pre-TEST handoff, chaining
it to the verified binding from the original pre-TEST archive:

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

The independent archive must preserve those exact bytes and issue a second receipt before any TEST prediction is
opened. Verify the externally supplied receipt with the existing generic verifier:

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

The second receipt binds exact bytes and external record context. Repository verification still does not establish
that the channel was actually independently controlled or historically append-only.

**TEST must not feed back** into threshold selection, parser routing, promotion logic, publication/input selection,
source commit choice, execution-plan changes, trust-root selection, or trust-policy construction.

See `docs/EXTRACTION_DEVELOPMENT_FREEZE.md` for the detailed temporal-boundary procedure.

## 6. Run the untouched TEST grid

Only after the DEVELOPMENT freeze, TEST evaluation lock, and second independent archive/receipt exist, run the
same complete threshold grid against:

```text
--target-manifest evidence/splits/test-target-manifest.json
```

Archive exact canonical TEST prediction bytes and one execution attestation per TEST threshold. TEST may evaluate
the already frozen decision and populate the precommitted evidence report; it may not change upstream choices.

## 7. Build the release-evidence bundle

Once review records, DEVELOPMENT/TEST predictions, execution IDs, and the frozen policy are archived, build the
canonical bundle:

```bash
python scripts/build_extraction_release_bundle.py \
  --review-record evidence/review-records/<target-1>.json \
  --review-record evidence/review-records/<target-N>.json \
  --release-artifact-root evidence/predictions \
  --input-artifact-manifest benchmark/extraction/extraction_input_artifact_manifest_v0.15.json \
  --input-artifact-root evidence/input-artifacts \
  --development-run nc-005 0.005 '<execution-id>' development/nc-005.json \
  --development-run nc-010 0.010 '<execution-id>' development/nc-010.json \
  --development-run nc-020 0.020 '<execution-id>' development/nc-020.json \
  --test-run nc-005 0.005 '<execution-id>' test/nc-005.json \
  --test-run nc-010 0.010 '<execution-id>' test/nc-010.json \
  --test-run nc-020 0.020 '<execution-id>' test/nc-020.json \
  --min-selective-coverage '<precommitted-value>' \
  --min-accepted-full-accuracy '<precommitted-value>' \
  --max-critical-family-wrong-accept-upper-bound 0.80 \
  --output evidence/release/release-evidence-bundle.json
```

Use exact frozen policy values; do not choose them from TEST. The v0.15 `0.80` family upper-bound limit is a
non-production pilot policy, not a production safety target.

## 8. Cold rebuild and verify external provenance

On an independent verifier, supply archived source evidence, exact publication/execution bytes, pre-TEST
policy/root, signed provenance, and expected run context chosen independently of the signed envelope:

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

For the stronger source-archive claim, provide the complete optional source-archive verification chain; partial
chains must fail closed. Cold reconstruction remains authoritative: it reopens canonical prediction artifacts,
recomputes reports, re-derives the DEVELOPMENT threshold, and reconstructs the TEST lock rather than trusting
archive summaries.

## 9. What closes issue #26

Repository-side success is necessary but not sufficient. The milestone closes only when the archived evidence
supports the external facts software cannot create: genuine reviewer/adjudicator independence, historical pre-TEST
trust/policy and post-DEVELOPMENT freeze existence, untouched TEST handling, independently controlled expected run
context, any claimed institutional key/workflow ownership, and the complete cold-verifiable evidence package.

A green CI run, a Git commit, or a structurally valid receipt alone is not that evidence.
