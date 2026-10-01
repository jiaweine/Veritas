# Parser-independent claim-graph reconstruction

A `StatisticalClaimGraph` is intended to be a durable detector-input boundary, not a cache of parser internals. Once a graph has been serialized and restored, deterministic detectors should be able to consume supported statistical objects without reopening the source parser state.

## RegressionResult adapter

`veritas.claim_reconstruction.reconstruct_statistical_object()` supports `RegressionResult` nodes. The adapter rebuilds detector-facing `ReportedNumber` values from graph fields using only:

- parsed numeric value;
- displayed precision;
- explicit comparison operator;
- graph/object source provenance;
- explicit inference metadata needed by the regression detector.

The exact raw displayed string remains in `ExtractedField.raw` for provenance and review even though `ReportedNumber` itself stores the parsed value, precision, and comparison operator.

## Structured scalar-key adapters

The graph's field payload is intentionally scalar so every displayed quantity can keep its own source address and confidence. Structured objects therefore use deterministic field-key schemas rather than embedding untraceable dict/list payloads.

### SamplePartition

- `total_n` — optional integer total.
- `group_count:<label>` — one integer field per displayed group count. Everything after the first prefix is the exact group label.
- `non_overlapping` — required boolean whenever group counts exist, because silently accepting the model default could create a hard arithmetic contradiction.
- `exhaustive` — optional boolean.
- `explanation_present` — optional boolean.

Counts remain independently source-addressable. Negative counts reject reconstruction.

### CorrelationMatrix

- `label:<index>` — string variable labels with contiguous zero-based indexes.
- `cell:<row>:<column>` — one reported-number field per displayed cell.

Cells need not duplicate both triangles: missing cells remain `None` and the correlation detector performs its existing symmetry/interval logic. Every displayed cell must carry its explicit comparison operator, while displayed precision flows into the reconstructed rounding interval.

### MeanSD

A standalone reported N/mean/SD row reconstructs to the existing `GroupSummary` type using:

- `label` — required non-empty group/row label;
- `n` — required integer with `N >= 2`;
- `mean` and `sd` — required reported-number fields with explicit comparison operators;
- `sd_definition` — optional `sample`, `population`, or `unknown`; omitted values remain `unknown`;
- `weighted` — optional boolean; omitted values remain unknown.

A negative SD or invalid sample size rejects reconstruction. Missing weighting or SD-definition semantics do not get guessed into detector-applicable values.

### GroupComparison

A two-group comparison reconstructs directly to the existing `TwoGroupComparison` detector input. Each group remains independently source-addressable through `group_a:` / `group_b:` prefixes:

- `group_<a|b>:label`, `:n`, `:mean`, `:sd`, `:sd_definition`, and `:weighted`;
- optional reported statistics: `reported_mean_difference`, `reported_t`, `reported_df`, `reported_p_value`, `reported_cohen_d`, and `reported_hedges_g`;
- optional `test_definition` (`student_equal_var`, `welch`, or `unknown`) and `hedges_correction` (`exact_gamma`, `approx_4df_minus_1`, or `unknown`);
- conservative verification flags: `independent_groups_verified`, `same_outcome_scale_verified`, `difference_direction_verified`, and `pooled_sd_effect_size_verified`.

Missing verification flags become `False`, which makes the deterministic detector return `UNVERIFIABLE` instead of manufacturing applicability. If a p-value is reported, `p_value_adjusted` is required because silently defaulting it to `False` could create a hard numerical check that the graph did not justify.

### DiscreteSummary

- `n` — required positive integer.
- `mean` — required reported number with explicit comparison operator.
- `sd` — optional reported number with explicit comparison operator.
- `support:<index>` — finite support values with contiguous zero-based indexes; at least two distinct values are required.
- `sd_definition` — required when `sd` exists and must be `sample`, `population`, or `unknown`.
- `support_verified`, `n_verified`, and `weighted` — required booleans. These detector applicability gates are never inherited from model defaults.

This preserves the distinction between a mathematically feasible finite-support check and the separate evidence needed to establish that the displayed statistic is actually an unweighted count summary over the claimed support.

### LogitResult

- `beta` and `odds_ratio` — required reported numbers.
- `exp_beta_relation_verified` — required boolean establishing that the two displayed quantities are claimed on the same logit scale with OR = exp(beta).

### MediationResult

- `a_path`, `b_path`, and `indirect_effect` — required reported numbers.
- `product_definition_verified` — required boolean establishing that the reported indirect effect is defined as `a*b`.
- `scale_consistent_verified` — required boolean establishing compatible scales for the three quantities.

The relation/scale booleans are explicit provenance gates. Missing gates reject reconstruction instead of becoming the dataclass defaults that could accidentally authorize a numerical contradiction.

## Fail-closed requirements

Reconstruction does not infer detector-relevant semantics from model defaults.

- Every reported numeric field must carry an explicit `comparison_operator`. Missing operators reject reconstruction rather than silently becoming equality.
- A reported p-value or confidence interval requires an explicit `inference_distribution` field.
- A reported regression or group-comparison p-value requires explicit `p_value_adjusted` status whenever that status can change deterministic applicability.
- Any reported confidence-interval bound requires an explicit `ci_level`.
- A populated sample partition must state whether groups are non-overlapping.
- Correlation and finite-support indexes must be contiguous and every indexed quantity must refer to a declared position.
- Mean/SD sample sizes and SD values must satisfy the existing typed-model constraints.
- Group-comparison applicability flags default only toward `UNVERIFIABLE`; they never default toward detector authority.
- Discrete, logit, and mediation detector applicability gates must be present explicitly even when their value is `False`.
- Unsupported statistical object types raise `ClaimObjectReconstructionError`; callers must not guess a nearby schema.

This means older or incomplete graphs can remain valid provenance records while still being ineligible for parser-independent detector execution.

## Current scope

Adapters currently cover `RegressionResult`, `SamplePartition`, `CorrelationMatrix`, `MeanSD`, `GroupComparison`, `DiscreteSummary`, `LogitResult`, and `MediationResult`. Additional adapters should be added object-by-object with their own fail-closed metadata contract and round-trip detector tests rather than through a permissive generic coercion layer.
