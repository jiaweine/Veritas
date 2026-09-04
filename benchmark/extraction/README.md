# Real-paper extraction corpus

This directory separates **sampling-frame candidates**, **seed cases**, **reviewed gold**, **locked benchmark splits**, and any later release receipt.

A paper or case appearing here is never evidence that the paper is reliable, unreliable, reproducible, or problematic. The corpus evaluates extraction and promotion behavior only.

## Lifecycle

1. **Unlabeled sampling frame** — candidate papers live in `benchmark/corpus/candidates.json`. Presence in the frame is metadata only and carries no claim/extraction label.
2. **Pre-TEST evidence plan** — before reviewed TEST outcomes are inspected, `scripts/build_extraction_evidence_plan.py` commits the exact sampling-frame bytes, normalized sampling-frame identity, independent-review protocol version, split salt, and complete threshold grid. The plan is explicitly non-production.
3. **Seed** — a real, legally accessible paper/display item useful for parser development. Seed cases may have legacy manual checks, but they are not benchmark gold.
4. **Double review** — every numerical field, table/figure identity, row/column identity, and critical semantic gate is independently checked by at least two reviewers and adjudicated. Veritas cannot manufacture reviewer independence; reviewer identities and adjudication must come from genuinely independent humans.
5. **Family lock** — all paper versions sharing one `article_family_id` receive one immutable train/development/test assignment. Corpus growth requires an explicit new plan/lock rather than silently changing the old family universe.
6. **Development calibration** — extraction thresholds, parser routing, and promotion policy may be tuned only on train/development families. The selected threshold must be one of the threshold IDs/values committed before TEST.
7. **Untouched TEST** — the TEST families are used only after the extraction/promotion protocol is frozen. TEST outcomes cannot be used to change thresholds and then be reported as held-out evidence.
8. **Release receipt** — `ExtractionEvidenceReleaseReceipt` can be issued only if the reviewed gold, deterministic split lock, frozen DEVELOPMENT threshold, TEST seal, TEST evaluation lock, and DEVELOPMENT/TEST coverage–selectivity curves all validate against the same pre-TEST evidence plan. The receipt remains `production_authorized = false`.

The release workflow is deliberately stricter than having a collection of hashes. It mechanically rejects mixed sampling frames, altered review protocols, split drift, post-hoc threshold grids, changed DEVELOPMENT/TEST manifests, invalid TEST seals, and curves evaluated on a different threshold grid.

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
