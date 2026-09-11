# Paper-only algebra cross-checks

Some high-specificity contradictions can be established from the paper alone when the semantic relationship between reported quantities is itself verified.

## Logit coefficient and odds ratio

If a paper reports a log-odds coefficient `beta` and explicitly presents the corresponding odds ratio on the same scale, then

`OR = exp(beta)`.

Veritas propagates the displayed rounding interval of `beta` through the monotone exponential function and intersects it with the displayed rounding interval of the reported odds ratio.

A contradiction is allowed only when `exp_beta_relation_verified=True`. This gate prevents confusion with marginal effects, standardized effects, transformed units, interactions, or odds ratios from a different model.

## Mediation product

For a mediation result explicitly defined as the product-of-coefficients estimator,

`indirect = a * b`.

Veritas computes the full product interval from the four endpoint products of the rounding-compatible `a` and `b` intervals. It compares this set with the reported indirect-effect interval.

The check requires both:

- `product_definition_verified=True`;
- `scale_consistent_verified=True`.

This prevents false contradictions when authors report standardized and unstandardized coefficients together, use a different mediation estimand, or mix model scales.

## Principle

The LLM/extraction layer may identify candidate relationships, but deterministic algebra produces the finding. If relation identity is ambiguous, the detector returns `UNVERIFIABLE` rather than forcing a match.
