# Extraction evidence operations runbook

This runbook turns the remaining real-evidence work in issue #26 into an operator sequence. It is intentionally
stricter than "run the scripts until they pass": repository code can verify identities and consistency, but it
cannot manufacture independent humans, historical pre-TEST timing, institutional key ownership, or an untouched
TEST process.

The repository orchestration baseline is now `main`, but the frozen v0.15 execution source commit remains
`d6ffdf7debd63281e0db5934e3d4b7ebafb98311`. **Do not replace the frozen execution source commit with current
`main`** merely because the orchestration code was later integrated there.

## 0. Authority prerequisites before TEST

Before any held-out TEST outcome is inspected:

- the exact sampling frame, seed manifest, evidence plan, execution plan, publication/input bytes, source-tree
  archive, parser registry, numerical runtime, execution command, and blinded packet commitments must already be
  archived under the precommitted identities;
- the evidence-run trust root and trust policy must already exist in an independently controlled historical
  channel if an external-run claim will be made;
- any stronger commit-to-source-archive claim needs its own pretrusted builder root/policy and independently
  governed build history;
- reviewer A, reviewer B, and the adjudicator must be genuinely independent people/processes. Reviewer IDs are
  not proof of human independence;
- expected evidence-run id/attempt/commit and optional build-run id/attempt must come from an independently
  selected expected run context, not from the signed envelope being verified;
- `production_authorized` remains false throughout this workflow.

Repository Git history, GitHub Actions history, and a valid signature can support the evidence package, but they
are not substitutes for those external facts.

## 1. Persist strict reviewer submissions and adjudication

Each reviewer works from the already frozen blinded packet, without another reviewer's submission or legacy
benchmark values. Persist one strict submission JSON per reviewer and one strict adjudication JSON per target.

Build one canonical review record per target:

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

Archive the printed review-record SHA-256 next to the independently maintained reviewer/adjudication provenance.
Do not synthesize missing reviewer records, copy reviewer identities, or treat agreement between A and B as a
substitute for the required independent adjudicator.

## 2. Derive DEVELOPMENT and TEST membership mechanically

After all review records entering locked gold have been independently adjudicated, derive the family split and
target manifests with the repository builder:

```bash
python scripts/build_extraction_split_manifests.py \
  --sampling-frame benchmark/corpus/evidence_sampling_frame_v0.15.json \
  --seed-manifest benchmark/extraction/evidence_seed_manifest_v0.15.json \
  --evidence-plan benchmark/extraction/evidence_plan_v0.15.json \
  --review-record evidence/review-records/<target-1>.json \
  --review-record evidence/review-records/<target-2>.json \
  --review-record evidence/review-records/<target-N>.json \
  --output-dir evidence/splits
```

The command writes:

- `development-target-manifest.json`;
- `test-target-manifest.json`;
- `split-derivation.json`.

`split-derivation.json` records the reviewed-gold hash, family split-lock hash and assignments, semantic manifest
hashes, exact split-manifest file hashes, and every review-record hash. The builder rejects post-precommit
sampling/seed byte drift, target identity drift, source-locator drift, duplicate review targets, missing
adjudication, and any split that cannot produce non-empty DEVELOPMENT and TEST manifests.

Do not hand-author split membership and do not copy a membership digest from another run.

## 3. Pin the evidence-run trust policy before TEST

The trust root supplied here must already be governed and historically archived outside the evidence run. Build
the policy from concrete artifacts rather than manually typed digests:

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

Archive the policy bytes and printed SHA-256 through the independent historical channel before TEST.

If the evidence claim must additionally prove that the source-tree archive was produced from the named Git
commit, precommit the separate builder policy before TEST:

```bash
python scripts/build_extraction_source_archive_trust_policy.py \
  --policy-id '<source-archive-policy-id>' \
  --source-commit-sha d6ffdf7debd63281e0db5934e3d4b7ebafb98311 \
  --execution-plan benchmark/extraction/extraction_execution_plan_v0.15.json \
  --source-tree evidence/execution/source-tree.tar \
  --trust-root external/source-archive-trust-root.json \
  --output external/source-archive-trust-policy.json
```

A valid builder signature later proves only that the holder of the pretrusted builder key signed the exact
commit/execution-plan/source-tree relation. External governance must still establish who controlled that key and
what the trusted workflow actually did.

## 4. Run every precommitted threshold on DEVELOPMENT

The threshold runner accepts a blinded packet and a derived split manifest. It does not read reviewed gold or the
value-bearing seed manifest:

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

Repeat for the complete frozen grid (`nc-005`, `nc-010`, `nc-020`) with their exact precommitted values and repeat
`--paper-artifact` for every paper required by the split.

Archive every canonical prediction artifact and the execution context needed to build the corresponding
`ExtractionExecutionAttestation`. DEVELOPMENT-only evaluation and threshold selection must be completed and
historically frozen before TEST begins.

## 5. Freeze DEVELOPMENT selection before touching TEST

Evaluate every DEVELOPMENT prediction artifact against the exact reviewed DEVELOPMENT gold using the
precommitted benchmark confidence and pilot threshold policy. Preserve the complete observations, coverage-
selectivity curve, selected threshold, derived DEVELOPMENT manifest hash, and execution attestations.

The release/cold-rebuild APIs deterministically recompute this selection. Historical evidence must additionally
show that the DEVELOPMENT-only decision existed before held-out TEST outcomes were inspected.

**TEST must not feed back** into threshold selection, parser routing, promotion logic, publication/input selection,
source commit choice, execution-plan changes, trust-root selection, or trust-policy construction.

## 6. Run the untouched TEST grid

Only after DEVELOPMENT selection and all pre-TEST trust material are frozen, run the same complete threshold grid
with:

```text
--target-manifest evidence/splits/test-target-manifest.json
```

Archive exact canonical prediction bytes and one execution attestation per TEST threshold. Do not tune anything
from these outcomes.

## 7. Build the release-evidence bundle

Once review records, DEVELOPMENT/TEST prediction artifacts, execution IDs, and the DEVELOPMENT-only policy are
archived, build the canonical bundle:

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

Use the exact already frozen policy values; do not choose them from TEST results. The v0.15 `0.80` wrong-accept
upper-bound limit is a non-production pilot threshold and must not be represented as a production safety target.

## 8. Cold rebuild and verify external provenance

On an independent verifier, supply the archived source evidence, exact publication/execution bytes, pre-TEST
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

When making the stronger source-archive claim, also provide all five optional source-archive verification inputs:
trust root, trust policy, signed provenance, independently selected run id, and independently selected run attempt.
Supplying only part of that chain must fail closed.

## 9. What closes issue #26

Repository-side success is necessary but not sufficient. The milestone can close only when the archived evidence
also supports the external facts that software cannot create: genuine reviewer/adjudicator independence,
historical pre-TEST trust/policy existence, untouched TEST handling, independently controlled expected run
context, any claimed institutional key/workflow ownership, and the complete cold-verifiable evidence package.

A green CI run, a Git commit, or a structurally valid receipt alone is not that evidence.
