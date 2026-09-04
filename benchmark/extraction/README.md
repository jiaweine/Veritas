# Real-paper extraction corpus

This directory separates **sampling-frame candidates**, **seed cases**, **reviewed gold**, **locked benchmark splits**, and any later release receipt.

A paper or case appearing here is never evidence that the paper is reliable, unreliable, reproducible, or problematic. The corpus evaluates extraction and promotion behavior only.

## Lifecycle

1. **Unlabeled sampling frame** — candidate papers live in `benchmark/corpus/candidates.json`. Presence in the frame is metadata only and carries no claim/extraction label.
2. **Pre-TEST evidence plan** — before reviewed TEST outcomes are inspected, `scripts/build_extraction_evidence_plan.py` commits the exact sampling-frame bytes, normalized sampling-frame identity, exact seed-manifest bytes, the deterministic seed target-universe SHA-256, independent-review protocol version, split salt, and complete threshold grid. The plan is explicitly non-production. The seed file is a required explicit input and is strictly parsed before either its byte identity or its derived target-universe identity can enter the plan.
3. **Seed** — a real, legally accessible paper/display item useful for parser development. Seed cases may have legacy manual checks, but they are not benchmark gold. The exact committed seed bytes deterministically define the review-target universe (`case_id:key` plus paper/family/object/key/criticality and page/table/row locator identity); a later gold target cannot be introduced merely by copying the committed seed SHA.
4. **Double review and adjudication** — every numerical field, table/figure identity, row/column identity, and critical semantic gate is independently checked by at least two reviewers and then independently adjudicated before it can become locked gold. Agreement between reviewer A and reviewer B is sufficient for a review record, but it is **not** represented as adjudication and cannot be promoted to locked gold without a distinct adjudicator. Veritas cannot manufacture reviewer independence; reviewer identities and adjudication must come from genuinely independent humans.
5. **Family lock** — all paper versions sharing one `article_family_id` receive one immutable train/development/test assignment. Corpus growth requires an explicit new plan/lock rather than silently changing the old family universe.
6. **Derived split-target manifests** — DEVELOPMENT and TEST target manifests are deterministically derived from the exact reviewed-gold hash plus the exact family split-lock hash. Each manifest commits the split identity, article-family membership, and target membership. Callers do not get to supply arbitrary DEVELOPMENT/TEST digest strings and have them accepted as evidence membership.
7. **Development calibration** — extraction thresholds, parser routing, and promotion policy may be tuned only on train/development families. The selected threshold must be one of the threshold IDs/values committed before TEST, and its `development_manifest_sha256` must equal the deterministically derived DEVELOPMENT target manifest.
8. **Untouched TEST** — the TEST families are used only after the extraction/promotion protocol is frozen. TEST outcomes cannot be used to change thresholds and then be reported as held-out evidence. A case already used for parser development does not become untouched merely because its labels later receive double review. The TEST evaluation lock must bind the deterministically derived TEST target manifest.
9. **Release receipt** — `ExtractionEvidenceReleaseReceipt` can be issued only if the reviewed gold belongs to both the precommitted sampling frame and the exact seed-derived review-target universe, including its page/table/row locator identity, and if its deterministic split lock, derived DEVELOPMENT/TEST target manifests, frozen DEVELOPMENT threshold, TEST seal, TEST evaluation lock, and DEVELOPMENT/TEST coverage–selectivity curves all validate against the same pre-TEST evidence plan. The receipt records both derived split-manifest SHA-256 values and remains `production_authorized = false`.

The release workflow is deliberately stricter than having a collection of hashes. It mechanically rejects mixed sampling frames, changed seed bytes, changed seed target-universe semantics, target or locator drift, missing real adjudication, altered review protocols, split drift, caller-forged DEVELOPMENT/TEST membership hashes, post-hoc threshold grids, invalid TEST seals, and curves evaluated on a different threshold grid.

## Metrics

Extraction evaluation reports separate quantities rather than collapsing them into a single score:

- selective coverage;
- accepted numerical/value accuracy;
- accepted source identity accuracy;
- table/row identity accuracy;
- critical semantic-gate accuracy;
- article-family-level wrong-accept rate and its one-sided confidence bound.

A parser that extracts the correct number from the wrong table or wrong row is therefore not counted as correct merely because the numeric string matches.

Coverage–selectivity curves must retain every precommitted threshold point. A release receipt will not validate a curve with thresholds added, removed, or changed after the evidence plan was frozen.

## Production boundary

Seed, development, TEST benchmark, and release-receipt results carry no production hard-finding authority by themselves. Production authority remains governed separately by the held-out certification path and must bind a sufficiently large corpus plus the exact parser/schema/promotion/system combination being deployed.