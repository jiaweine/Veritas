# Meta-analysis audit methodology

Veritas treats meta-analysis as a family of explicitly identified estimators and inference procedures, not as one generic `random_effects` flag.

## Supported arithmetic in v0.5

The first implementation supports inverse-variance meta-analysis when study effects and standard errors are reported on one verified additive analysis scale.

Supported model paths:

- `fixed_inverse_variance`;
- `random_inverse_variance_reported_tau2`.

The random-effects path requires the paper to report `tau^2`. Veritas does not guess a heterogeneity estimator and does not claim that a reported `tau^2` is correct merely because it can reconstruct weights from it.

## Rounding-aware weights

For a study standard error reported with interval `[s_L, s_U]`, fixed-effect inverse-variance weights satisfy

`w in [1/s_U^2, 1/s_L^2]`.

For a random-effects model with reported

`tau^2 in [t_L, t_U]`,

Veritas uses the safe outer weight interval

`w in [1/(s_U^2+t_U), 1/(s_L^2+t_L)]`.

All studies share the same latent `tau^2`, so treating these intervals as independently variable deliberately enlarges the feasible set. This can hide some contradictions, but it cannot turn a feasible result into a false contradiction. The relaxation is recorded in finding evidence.

## Global pooled-effect bounds without endpoint explosion

For study effects `y_i` and positive weights `w_i`,

`mu = sum(w_i y_i) / sum(w_i)`.

The minimum over independent weight intervals does not require enumerating all `2^k` weight vertices. For fixed candidate `m`, minimizing

`sum_i w_i (y_i-m)`

selects the upper weight bound when `(y_i-m) < 0` and the lower bound otherwise. The resulting piecewise-linear function is monotone in `m`; its zero gives the global minimum weighted average. The global maximum follows symmetrically.

Effect rounding uncertainty is incorporated by using all lower effect endpoints for the global lower bound and all upper endpoints for the global upper bound. A small outward numerical safety expansion is applied.

## Conventional normal inference

When `inference_method="normal"`, Veritas can form conservative rounding-compatible bounds for:

- pooled standard error `sqrt(1/sum(w_i))`;
- confidence-interval endpoints;
- two-sided pooled p-value;
- reported study weight percentages.

CI endpoint ranges are outer bounds because pooled center and pooled SE depend on the same weights. The rectangle relaxation makes the interval wider, not narrower.

## HKSJ is not normal inference

`hksj`, modified HKSJ, and other random-effects inference procedures are recognized as different paths. v0.5 checks the pooled center/weights when their weighting definition is known, but abstains on HKSJ SE/CI/p reconstruction rather than silently applying a normal critical value.

This follows the current methodological landscape: the Cochrane Handbook distinguishes heterogeneity estimators such as DerSimonian-Laird and REML and discusses Hartung-Knapp/Sidik-Jonkman as a distinct uncertainty adjustment, especially relevant when heterogeneity is estimated with limited information.

## Prediction intervals

Prediction intervals are not yet hard-audited in v0.5. They depend on a separately identified construction, uncertainty in heterogeneity, the number of studies, and distributional assumptions. Recent 2026 work shows that frequentist prediction-interval coverage can behave poorly or asymmetrically with small numbers of studies, so Veritas will not infer a PI formula from the phrase `95% prediction interval` alone.

Future support must identify the exact PI method before reconstruction.

## Cochran Q and I-squared

v0.5 performs reporting-internal consistency checks when the semantics are verified:

- `df_Q = k - 1`;
- `Q -> chi-square p-value`;
- `I^2 = max(0, (Q-df_Q)/Q) * 100`.

It does **not** yet claim to reconstruct the reported Q globally from rounded study effects and SEs. Q is a nonlinear function of both weights and the fitted pooled effect; a future hard detector must solve that joint uncertainty rather than substitute displayed midpoints.

## Applicability gates

The detector abstains when relevant prerequisites are missing, including:

- effects are not verified to be on one additive analysis scale;
- effects are correlated but ordinary independent inverse-variance weighting is assumed;
- study effect or SE inputs are inequalities rather than equality-reported rounded values;
- an SE rounding interval reaches zero;
- inverse-variance weighting is not established;
- random-effects weights are requested without reported `tau^2`;
- HKSJ or another non-normal inference path is reported but not explicitly implemented;
- adjusted p-values are reported without the adjustment rule.

A direct disjoint safe interval may support E3 internal contradiction when all required semantics are verified. Such a finding is about arithmetic compatibility only, not author intent.
