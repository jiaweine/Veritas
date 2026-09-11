# Extraction architecture: calibrated abstention, not LLM guessing

Statistical auditing fails if PDF extraction silently changes a sign, decimal, sample size, table column, or estimator label. Veritas therefore treats ingestion as a separately benchmarked statistical component.

## Multi-pass parser boundary

Recommended production path:

1. native PDF text/layout objects;
2. specialized document parser/VLM for page structure;
3. independent table-structure reconstruction;
4. schema-constrained claim/object extraction;
5. cross-pass value alignment;
6. conformal calibration gate;
7. unresolved conflicts remain unresolved.

No downstream E3+ finding is allowed to hide extraction uncertainty.

## Why an ensemble

OmniDocBench (CVPR 2025 and living updates through 2026) shows that parser rankings depend on text, formula, table and reading-order difficulty. Scientific-table evaluations in 2025 likewise show that scientific tables remain harder for multimodal LLMs than generic tables. A fixed single-parser architecture would make Veritas brittle to both document type and model churn.

## Conformal Extraction Gate

`ConformalExtractionGate` uses held-out nonconformity scores to compute a finite-sample split-conformal threshold with the `(n + 1)` correction. Candidate values above the threshold are rejected.

After calibration, Veritas requires agreement across independent parser families. If two calibrated candidates disagree, the system returns `CONFLICT`; it does not ask an LLM to choose the more plausible number.

The optional distribution-shift gate uses a conformal-style tail p-value on held-out shift scores. Extreme inputs are marked `DOMAIN_SHIFT` and abstained before statistical auditing. This follows the direction of 2025 selective-conformal work emphasizing that exchangeability/domain shift must be tested rather than assumed.

## Calibration corpus

The extraction benchmark must be stratified across:

- economics regression tables;
- psychology/management correlation and SEM tables;
- sociology/political-science descriptive and causal tables;
- multi-column PDFs;
- scanned/OCR documents;
- appendices with small fonts;
- significance stars, inequality p-values and footnote-defined standard errors;
- cross-page tables.

Metrics are field-level exact match, numeric tolerance match, sign error rate, decimal-shift rate, row/column identity accuracy, claim-link accuracy, and downstream false-hard-alert rate.

The calibration split and parser versions are part of the audit protocol lock.
