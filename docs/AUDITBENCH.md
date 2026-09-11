# AuditBench certification protocol

AuditBench is not a leaderboard for average accuracy. Its purpose is to decide whether a detector is allowed to emit high-severity findings in a research-integrity product.

## Unit of evaluation

The primary safety unit is the **paper**, not the individual statistic. Ten correlated alerts caused by one transcription error count as one paper-level hard alert.

All benchmark cases derived from the same source paper stay in the same split. `assign_paper_split()` hashes `paper_id + locked salt`, preventing table rows from the same paper leaking across development and final test sets.

## Controlled corruption families

Initial families:

- coefficient / SE / p-value transcription;
- confidence-interval mismatch;
- sample partition arithmetic;
- symmetric correlation mismatch;
- impossible correlation bounds;
- benign rounding edge cases;
- adjusted p-values that must abstain;
- missing inference metadata that must become `UNVERIFIABLE`;
- extraction disagreements that must become `CONFLICT`/`ABSTAIN`.

Later families include specification search, sample deletion, wrong clustering, staggered-DiD estimator mismatch, weak-IV inference, RDD procedure perturbations, outcome switching, and provenance inconsistencies.

## Why point estimates are insufficient

A detector that produces zero false hard alerts on 50 papers has not demonstrated a <1% false-alert rate. With a finite benchmark, uncertainty around the error rate matters.

Veritas therefore computes one-sided exact Clopper-Pearson bounds. The default E3 certification target requires:

- at least 300 clean applicable papers;
- at least 50 positive applicable papers;
- 95% upper confidence bound for paper-level false hard-alert rate <= 1%;
- 95% lower confidence bound for hard-alert precision >= 95%.

In practice, zero false alerts requires roughly 300+ clean papers before the upper bound approaches 1%, so small demos cannot self-certify.

## Selection freeze

Detector thresholds, parser versions, calibration corpus hash, methodology snapshot, corruption operators, development split, and final-test split are frozen before final evaluation. Final-test outcomes cannot be used to choose detector thresholds.

## Reporting

Every detector card should publish:

- applicability count;
- clean and positive paper counts;
- point precision/recall;
- paper-level false hard-alert rate;
- exact confidence bounds;
- failure slices by discipline, reporting style, parser route, and PDF quality;
- benchmark and methodology snapshot hashes.

A detector that fails certification may remain available as E1/E2 experimental evidence; it does not get promoted to production E3.
