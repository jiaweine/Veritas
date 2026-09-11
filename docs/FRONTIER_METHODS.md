# Frontier methodology policy

Veritas should be current without becoming fashionable. A method is not promoted because it is new; it is promoted when it has a clear estimand, explicit assumptions, a usable implementation, and a validation path.

## Freshness rule

For design-sensitive detectors, the detector card must record:

- methodological anchor and publication/version date;
- estimand and identifying assumptions;
- exact applicability gate;
- known benign exceptions;
- severity ceiling before AuditBench certification;
- software package/version when Veritas delegates numerical work.

A detector is reviewed whenever a major methodological survey, journal article, or maintained reference implementation materially changes recommended practice.

## 2026 priority stack

### Difference-in-differences

Primary organizing reference: Baker, Callaway, Cunningham, Goodman-Bacon & Sant'Anna (2026), *Journal of Economic Literature*, “Difference-in-Differences Designs: A Practitioner's Guide.”

Implementation rule: classify the design before evaluating the estimator. Veritas must resolve at least treatment timing, number of periods, treatment type, comparison group, and estimator family. It must not implement `TWFE == invalid` as a keyword rule.

For staggered adoption and heterogeneous effects, the current robustness set includes group-time estimators, interaction-weighted/event-study approaches, and imputation-style estimators such as Borusyak, Jaravel & Spiess (2024, *Review of Economic Studies*). Continuous-treatment DiD receives a separate applicability path because recent work shows that popular TWFE summaries can have multiple, limited causal interpretations.

### Instrumental variables

Primary current practical reference: Lee & Porter (2026), *Journal of Economic Perspectives*, “Correct (and Incorrect) Inference with a Single Instrumental Variable.”

Implementation rule: never use `F > 10` as a hard validity threshold for the just-identified single-IV case. Prefer detection of whether weak-instrument-robust inference such as Anderson-Rubin or tF is available and whether the paper overstates what a first-stage threshold proves.

### Regression discontinuity

Current implementation family: maintained `rdpackages` ecosystem.

- `rdrobust`: local-polynomial estimation and robust bias-corrected inference;
- `rddensity`: local-polynomial density/manipulation testing, including the 2024 local regression distribution methodology;
- `rdlocrand`: local-randomization inference, window selection, and sensitivity analysis;
- `rdhte`: heterogeneous RD effects with robust bias-corrected inference (2025+).

Veritas should compare a paper's stated RD procedure against this design map rather than flagging a missing single diagnostic as misconduct.

### Analytical robustness

The 2025 multi-analyst Nature study on 100 social/behavioural studies shows that reasonable analyst choices can materially change estimates and conclusions. Veritas therefore treats specification uncertainty as a separate evidence family. The target implementation is a typed specification graph, not a brute-force “run every model” search. Only theoretically admissible, non-redundant specifications should enter the robustness set.

### Paper parsing and table extraction

Scientific tables remain a hard document-understanding problem. The ingestion layer should be benchmarked independently from statistical detectors. OmniDocBench (CVPR 2025, updated through 2026) tracks text, formula, table and reading-order performance across specialized document VLMs; 2025 table-understanding studies also show that scientific tables remain harder than generic tables for multimodal LLMs.

Veritas therefore uses a multi-pass extraction boundary:

1. native PDF text/layout extraction when available;
2. specialized document parser/VLM for page structure and tables;
3. independent table-cell reconstruction pass;
4. schema-constrained claim extraction;
5. cross-pass agreement and provenance retention;
6. unresolved disagreement lowers extraction confidence instead of being silently resolved by an LLM.

## New paper-only algorithm: interval SDP for correlation matrices

A displayed correlation matrix is not tested at its printed midpoint. Each reported entry defines a rounding interval. Veritas solves a semidefinite max-min eigenvalue problem over all symmetric matrices satisfying:

- diagonal = 1;
- each reported cell lies inside its rounding interval;
- missing triangular cells may be completed consistently;
- correlations remain in [-1, 1].

The optimization maximizes the smallest feasible eigenvalue. A non-negative optimum means at least one legal PSD correlation matrix is compatible with the paper. A negative optimum means no PSD completion exists under the modeled intervals.

Until AuditBench certifies solver tolerances and paper-level false-alert rates, an SDP-only negative margin is capped at E2. Direct algebraic impossibilities, such as a correlation whose entire rounding interval lies outside [-1, 1], may still emit E3.

## Governance

“Frontier” in Veritas means **latest defensible method under explicit version control**, not “newest preprint wins.” Experimental methods can be implemented behind a severity ceiling, but cannot produce production E3+ findings until benchmarked.
