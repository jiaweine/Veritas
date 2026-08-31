# HKSJ and prediction-interval arithmetic contract

Method snapshot date: 2026-08-31.

This document defines only arithmetic identities that Veritas v0.6 may hard-audit after semantic verification. It does not claim that the method is substantively appropriate for every meta-analysis.

## HKSJ

For inverse-variance weights `w_i`, study effects `y_i`, and pooled center `mu_hat`:

- `SSE = sum_i w_i * (y_i - mu_hat)^2`
- `q = SSE / (k - 1)`
- `Var_HK(mu_hat) = q / sum_i w_i`
- `SE_HK = sqrt(Var_HK(mu_hat))`
- confidence intervals and two-sided tests use Student t with `k - 1` degrees of freedom.

The modified/truncated Knapp-Hartung path implemented here uses:

- `q_star = max(1, q)`
- `Var_mKH(mu_hat) = q_star / sum_i w_i`

A paper must explicitly support the relevant HKSJ definition before `hksj_definition_verified=True` is allowed.

## Rounding-aware residual-SSE bounds

Study effect and SE reports are treated as rounding intervals. For HKSJ residual SSE, Veritas computes:

- a global safe lower bound by minimizing `sum_i w_i^L * dist(c, Y_i)^2` over one scalar center `c`;
- a global safe upper bound using the upper weight vector and exact effect-box vertex enumeration for small `k`;
- for larger `k`, a weighted Popoviciu range bound is used instead of exponential enumeration.

The large-k fallback deliberately widens the feasible set. It may reduce power but cannot create a hard contradiction by making the interval too narrow.

## HTS t_(k-2) conventional prediction interval

The first prediction-interval construction implemented by Veritas is explicitly named:

`hts_t_k_minus_2_conventional`

For a random-effects inverse-variance model with reported `tau^2`, it reconstructs:

`mu_hat +/- t_(k-2, 1-alpha/2) * sqrt(Var_conventional(mu_hat) + tau^2)`

where `Var_conventional(mu_hat) = 1 / sum_i w_i`.

No other prediction-interval label is silently mapped onto this formula. HKSJ-based, bootstrap, `k-1`, and other constructions remain unverifiable until separately implemented.

## Evidence boundaries

Arithmetic incompatibility may reach E3 only when the exact method semantics are verified. Small-study behavior, uncertainty in heterogeneity estimation, and whether a prediction interval is methodologically advisable are separate design-validity questions and must not be collapsed into arithmetic inconsistency.

Primary method anchors:

- Cochrane Handbook, Chapter 10, last updated November 2024: https://training.cochrane.org/handbook/current/chapter-10
- Stata current Meta-Analysis Reference Manual: https://www.stata.com/manuals/meta.pdf
- Matrai, Koi, Sipos & Farkas (2026), *Assessing the properties of the prediction interval in random-effects meta-analysis*, DOI 10.1017/rsm.2025.10055.
