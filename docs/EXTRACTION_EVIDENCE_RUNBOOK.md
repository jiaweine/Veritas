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
Its strict archive binds execution id, execution plan, split, target manifest, exact prediction bytes, prediction
semantics, isolation flags, and successful exit status.

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

## 6. Run the untouched TEST grid and attest each execution

Only after the DEVELOPMENT freeze, TEST evaluation lock, and second independent archive/receipt exist, run the
same complete threshold grid against `evidence/splits/test-target-manifest.json`. Archive exact canonical TEST
prediction bytes and immediately build one strict execution attestation for every TEST threshold using the frozen
execution plan, evidence plan, TEST manifest, exact prediction artifact, threshold id, and real execution id.

TEST may populate the precommitted report; it may not change upstream choices. Preserve the TEST attestation files
with the release evidence. Release assembly will derive execution ids from these files and will not accept a
separately retyped execution id.

## 7. Build a release bundle bound to calibration and execution attestations

Release assembly must not retype policy values, numeric thresholds, or execution ids. Supply the exact execution
plan and one prediction path plus strict attestation file for every threshold; the builder derives policy from the
DEVELOPMENT freeze, thresholds from the evidence-plan grid, and execution ids from the attestations:

```bash
python scripts/build_extraction_release_bundle.py \
  --review-record evidence/review-records/<target-1>.json \
  --review-record evidence/review-records/<target-N>.json \
  --release-artifact-root evidence/predictions \
  --input-artifact-manifest benchmark/extraction/extraction_input_artifact_manifest_v0.15.json \
  --input-artifact-root evidence/input-artifacts \
  --evidence-plan benchmark/extraction/evidence_plan_v0.15.json \
  --execution-plan benchmark/extraction/extraction_execution_plan_v0.15.json \
  --pilot-threshold-policy benchmark/extraction/pretest_pilot_threshold_policy_v0.15.json \
  --development-freeze evidence/calibration/development-calibration-freeze.json \
  --development-manifest evidence/splits/development-target-manifest.json \
  --test-evaluation-lock evidence/calibration/test-evaluation-lock.json \
  --test-manifest evidence/splits/test-target-manifest.json \
  --development-run nc-005 development/nc-005.json evidence/attestations/development/nc-005.json \
  --development-run nc-010 development/nc-010.json evidence/attestations/development/nc-010.json \
  --development-run nc-020 development/nc-020.json evidence/attestations/development/nc-020.json \
  --test-run nc-005 test/nc-005.json evidence/attestations/test/nc-005.json \
  --test-run nc-010 test/nc-010.json evidence/attestations/test/nc-010.json \
  --test-run nc-020 test/nc-020.json evidence/attestations/test/nc-020.json \
  --output evidence/release/release-evidence-bundle.json \
  --calibration-binding-output evidence/release/release-calibration-binding.json \
  --execution-binding-output evidence/release/release-execution-binding.json
```

There are no release-stage `--min-selective-coverage`, `--min-accepted-full-accuracy`,
`--max-critical-family-wrong-accept-upper-bound`, caller-supplied numeric run-threshold, or caller-supplied
execution-id arguments.

`release-calibration-binding.json` commits the exact release bundle to the pilot policy, DEVELOPMENT freeze,
selected threshold, DEVELOPMENT manifest, TEST evaluation archive/lock, TEST manifest, and frozen DEVELOPMENT
prediction bytes/semantics.

`release-execution-binding.json` separately commits the exact release bundle and execution plan to the sorted
DEVELOPMENT/TEST attestation sets. Each threshold row binds execution id, attestation semantic/file SHA-256, and
prediction byte/semantic SHA-256. The builder reopens release prediction artifacts and requires exact agreement
with each attestation.

## 8. Bound cold verification is the final repository-side v0.15 release check

The standalone binding verifiers remain useful diagnostic preflights. They can identify calibration-chain or
execution-attestation problems before the more expensive cold rebuild:

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

python scripts/verify_extraction_release_execution_binding.py \
  --release-bundle evidence/release/release-evidence-bundle.json \
  --release-execution-binding evidence/release/release-execution-binding.json \
  --release-artifact-root evidence/predictions \
  --execution-plan benchmark/extraction/extraction_execution_plan_v0.15.json \
  --development-manifest evidence/splits/development-target-manifest.json \
  --test-manifest evidence/splits/test-target-manifest.json \
  --development-attestation nc-005 evidence/attestations/development/nc-005.json \
  --development-attestation nc-010 evidence/attestations/development/nc-010.json \
  --development-attestation nc-020 evidence/attestations/development/nc-020.json \
  --test-attestation nc-005 evidence/attestations/test/nc-005.json \
  --test-attestation nc-010 evidence/attestations/test/nc-010.json \
  --test-attestation nc-020 evidence/attestations/test/nc-020.json \
  --output evidence/release/release-execution-verification.json
```

Those separate commands are **not** the final v0.15 verification artifact. A later file change could otherwise
create a time-of-check/time-of-use gap. The authoritative v0.15 bound-release verification must re-check both
sidecars in the **same process** that performs the cold rebuild and external-provenance verification:

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

Do not use `scripts/verify_extraction_external_provenance.py` as the final verifier for a v0.15 bound release. That
entrypoint remains only a compatibility path for older unbound archives.

Cold reconstruction remains authoritative: the bound verifier first reconstructs both release bindings from the
exact supplied files, then reopens canonical prediction artifacts, verifies execution/publication bytes,
recomputes reports, re-derives the DEVELOPMENT threshold, reconstructs the TEST lock, requires the archived
attested release to match the cold rebuild, and verifies the precommitted external signature/run context. Its final
JSON also commits the semantic and exact-file SHA-256 identities of both release bindings.

The expected run id/attempt/commit must still be independently selected rather than copied from the signed
envelope. For a stronger source-archive claim, also provide the complete optional source-archive verification
chain; partial chains must fail closed. See `docs/BOUND_EXTRACTION_EXTERNAL_PROVENANCE.md` for the narrower
contract.

## 9. Archive the post-verification replay set and verify the external receipt

A successful `bound-cold-verification.json` closes the repository-side release verification, not the external
custody requirement. Immediately build the post-verification handoff from the same exact artifacts. This command
re-checks the release bindings, cold-rebuild inputs, external signature/run context, and the exact bound-verification
artifact before defining the stable replay object set:

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

If the optional source-archive provenance chain was part of bound verification, supply that same complete optional
chain to the handoff builder as well. Partial source-archive chains must fail closed.

The handoff is still repository-side evidence. Its status must remain
`repository_side_postverification_external_archive_handoff_ready_awaiting_independent_archive`, and
`production_authorized` remains false. Record the exact handoff file SHA-256 independently, then transmit the
complete `archive_objects` set to the genuinely external custodian identified by the archive policy. The repository
does **not** provide a command that generates the custodian receipt.

After the independent archive has preserved the exact object set and issued its own receipt or equivalent record,
verify that externally supplied receipt using expectations selected independently from the receipt itself:

```bash
python scripts/verify_extraction_postverification_external_archive_receipt.py \
  --receipt external/postverification-archive-receipt.json \
  --handoff external/postverification-bound-release-handoff.json \
  --expected-handoff-sha256 '<independently-recorded-handoff-sha256>' \
  --expected-source-commit-sha d6ffdf7debd63281e0db5934e3d4b7ebafb98311 \
  --expected-custodian-identity '<independently-expected-custodian>' \
  --expected-archive-channel-identity '<independently-expected-channel>' \
  --expected-archive-record-id '<independently-expected-record-id>' \
  --output external/verified-postverification-archive-receipt-binding.json
```

The verifier reconstructs `archive_object_set_sha256` from stable archive names, exact object SHA-256 values, and
sizes; requires the set to contain the exact `verification/bound-cold-verification.json`; and checks the receipt
against the independently selected handoff/source/custodian/channel/record context. Do not copy those expected
values from the receipt immediately before verification.

A successful receipt binding proves only that the supplied receipt is bound to the repository handoff identities
that software can check. It does not interrogate the custodian service, prove every object externally retrievable,
or establish institutional control or retention semantics. Therefore the verified binding intentionally keeps
`independent_control_established=false`, `historical_channel_semantics_established=false`, and
`production_authorized=false`.

See `docs/EXTRACTION_POSTVERIFICATION_ARCHIVE_RECEIPT.md` for the strict receipt schema and narrower authority
contract.

## 10. What closes issue #26

Repository-side success is necessary but not sufficient. The milestone closes only when archived evidence supports
the external facts software cannot create: genuine reviewer/adjudicator independence, historical pre-TEST trust
and post-DEVELOPMENT freeze existence, untouched TEST handling, independently controlled expected run context,
any claimed institutional key/workflow ownership, and the complete cold-verifiable evidence package.

A green CI run, a Git commit, or a structurally valid receipt alone is not that evidence.