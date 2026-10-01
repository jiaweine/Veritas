# Parser-independent claim-graph reconstruction

A `StatisticalClaimGraph` is intended to be a durable detector-input boundary, not a cache of parser internals. Once a graph has been serialized and restored, deterministic detectors should be able to consume supported statistical objects without reopening the source parser state.

## RegressionResult adapter

`veritas.claim_reconstruction.reconstruct_statistical_object()` currently supports `RegressionResult` nodes. The adapter rebuilds detector-facing `ReportedNumber` values from graph fields using only:

- parsed numeric value;
- displayed precision;
- explicit comparison operator;
- graph/object source provenance;
- explicit inference metadata needed by the regression detector.

The exact raw displayed string remains in `ExtractedField.raw` for provenance and review even though `ReportedNumber` itself stores the parsed value, precision, and comparison operator.

## Fail-closed requirements

Reconstruction does not infer detector-relevant semantics from model defaults.

- Every reported numeric field must carry an explicit `comparison_operator`. Missing operators reject reconstruction rather than silently becoming equality.
- A reported p-value or confidence interval requires an explicit `inference_distribution` field.
- A reported p-value requires explicit `p_value_adjusted` status. Missing adjustment status must not silently become `False` because that could turn an otherwise unverifiable p-value into a hard numerical check.
- Any reported confidence-interval bound requires an explicit `ci_level`.
- Unsupported statistical object types raise `ClaimObjectReconstructionError`; callers must not guess a nearby schema.

This means older or incomplete graphs can remain valid provenance records while still being ineligible for parser-independent detector execution.

## Current scope

The first adapter is deliberately narrow because `RegressionResult` has a mature deterministic detector and explicit display-rounding semantics. Additional adapters should be added object-by-object with their own fail-closed metadata contract and round-trip detector tests rather than through a permissive generic coercion layer.
