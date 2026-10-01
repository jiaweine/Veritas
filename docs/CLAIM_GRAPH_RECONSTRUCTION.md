# Parser-independent claim-graph reconstruction

A `StatisticalClaimGraph` is intended to be a durable detector-input boundary, not a cache of parser internals. Once a graph has been serialized and restored, deterministic detectors should be able to consume supported statistical objects without reopening the source parser state.

## RegressionResult adapter

`veritas.claim_reconstruction.reconstruct_statistical_object()` supports `RegressionResult` nodes. The adapter rebuilds detector-facing `ReportedNumber` values from graph fields using only parsed numeric value, displayed precision, explicit comparison operator, graph/object source provenance, and explicit inference metadata needed by the regression detector.

The exact raw displayed string remains in `ExtractedField.raw` for provenance and review even though `ReportedNumber` itself stores the parsed value, precision, and comparison operator.

## Structured scalar-key adapters

The graph's field payload is intentionally scalar so every displayed quantity can keep its own source address and confidence. Structured objects therefore use deterministic field-key schemas rather than embedding untraceable dict/list payloads.

### SamplePartition

- `total_n` — optional integer total.
- `group_count:<label>` — one integer field per displayed group count.
- `non_overlapping` — required boolean whenever group counts exist.
- `exhaustive` — optional boolean.
- `explanation_present` — optional boolean.

Counts remain independently source-addressable. Negative counts reject reconstruction.

### CorrelationMatrix

- `label:<index>` — string variable labels with contiguous zero-based indexes.
- `cell:<row>:<column>` — one reported-number field per displayed cell.

Cells need not duplicate both triangles: missing cells remain `None` and the correlation detector performs its existing symmetry/interval logic. Every displayed cell must carry its explicit comparison operator, while displayed precision flows into the reconstructed rounding interval.

### MeanSD

A standalone reported N/mean/SD row reconstructs to the existing `GroupSummary` type using required `label`, integer `n >= 2`, reported `mean` and `sd`, optional `sd_definition`, and optional `weighted` status. A negative SD or invalid sample size rejects reconstruction. Missing weighting or SD-definition semantics do not get guessed into detector-applicable values.

### GroupComparison

A two-group comparison reconstructs directly to the existing `TwoGroupComparison` detector input. Each group remains independently source-addressable through `group_a:` / `group_b:` prefixes. Optional reported statistics and test-definition metadata stay explicit, while missing verification flags only drive the detector toward `UNVERIFIABLE`. If a p-value is reported, `p_value_adjusted` is required because silently defaulting it to `False` could create a hard numerical check that the graph did not justify.

### DiscreteSummary

- `n` — required positive integer.
- `mean` — required reported number with explicit comparison operator.
- `sd` — optional reported number with explicit comparison operator.
- `support:<index>` — finite support values with contiguous zero-based indexes; at least two distinct values are required.
- `sd_definition` — required when `sd` exists and must be `sample`, `population`, or `unknown`.
- `support_verified`, `n_verified`, and `weighted` — required booleans and never inherited from model defaults.

### LogitResult

`beta` and `odds_ratio` are required reported numbers, while `exp_beta_relation_verified` is a required boolean establishing that the displayed quantities are claimed on the same logit scale with OR = exp(beta).

### MediationResult

`a_path`, `b_path`, and `indirect_effect` are required reported numbers. `product_definition_verified` and `scale_consistent_verified` are required booleans establishing the product definition and compatible scales.

### StandardizedRegressionReconstruction

The standardized OLS object references a separately source-addressable `CorrelationMatrix` graph object instead of embedding matrix bytes inside a second object.

- `correlation_matrix_object_id` — required string ID of an existing `CorrelationMatrix` in the same graph.
- `outcome` — required outcome label.
- `predictor:<index>` — contiguous zero-based predictor labels.
- `standardized_beta:<index>` — one reported coefficient per predictor with the exact same index set.
- `ols_identity_verified`, `same_sample_verified`, and `complete_predictor_set_verified` — required booleans matching the detector's applicability boundary.

Reconstruction independently validates the referenced correlation object, rejects missing or wrong-typed references, and preserves every standardized beta's displayed precision and comparison operator.

## Fail-closed requirements

Reconstruction does not infer detector-relevant semantics from model defaults.

- Every reported numeric field must carry an explicit `comparison_operator`.
- A reported p-value or confidence interval requires explicit inference metadata where that metadata changes detector applicability.
- Any reported confidence-interval bound requires an explicit `ci_level`.
- A populated sample partition must state whether groups are non-overlapping.
- Indexed correlation, finite-support, predictor, and standardized-beta fields must be contiguous and internally consistent.
- Mean/SD sample sizes and SD values must satisfy the existing typed-model constraints.
- Group-comparison flags default only toward `UNVERIFIABLE`; they never default toward detector authority.
- Discrete, logit, mediation, and standardized-regression applicability gates must be explicit even when false.
- Cross-object references must resolve to the exact expected graph object type.
- Unsupported statistical object types raise `ClaimObjectReconstructionError`; callers must not guess a nearby schema.

This means older or incomplete graphs can remain valid provenance records while still being ineligible for parser-independent detector execution.

## Current scope

Adapters currently cover `RegressionResult`, `SamplePartition`, `CorrelationMatrix`, `MeanSD`, `GroupComparison`, `DiscreteSummary`, `LogitResult`, `MediationResult`, and `StandardizedRegressionReconstruction`. Additional adapters should be added object-by-object with their own fail-closed metadata contract and round-trip detector tests rather than through a permissive generic coercion layer.
