# Real-paper extraction corpus

This directory separates **seed cases**, **reviewed gold**, and **locked benchmark splits**.

A case appearing here is never evidence that the paper is reliable, unreliable, reproducible, or problematic. The corpus evaluates extraction and promotion behavior only.

## Lifecycle

1. **Seed** — a real, legally accessible paper/display item useful for parser development. Seed cases may have legacy manual checks, but they are not benchmark gold.
2. **Double review** — every numerical field, table/figure identity, row/column identity, and critical semantic gate is independently checked by at least two reviewers and adjudicated.
3. **Family lock** — all paper versions sharing one `article_family_id` receive one immutable train/development/test assignment. Corpus growth requires an explicit new lock rather than silently changing the old family universe.
4. **Development calibration** — extraction thresholds, parser routing, and promotion policy may be tuned only on train/development families.
5. **Untouched TEST** — the TEST families are used only after the extraction/promotion protocol is frozen. TEST outcomes cannot be used to change thresholds and then be reported as held-out evidence.

## Metrics

Extraction evaluation reports separate quantities rather than collapsing them into a single score:

- selective coverage;
- accepted numerical/value accuracy;
- accepted source identity accuracy;
- table/row identity accuracy;
- critical semantic-gate accuracy;
- article-family-level wrong-accept rate and its one-sided confidence bound.

A parser that extracts the correct number from the wrong table or wrong row is therefore not counted as correct merely because the numeric string matches.

## Production boundary

Seed, development, and ordinary benchmark results carry no production hard-finding authority. Production authority remains governed separately by the held-out certification path and must bind the exact parser/schema/promotion/system combination being deployed.
