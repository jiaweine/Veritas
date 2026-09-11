# SEM/CFA paper-only arithmetic contract

Method snapshot date: 2026-08-31.

Veritas v0.7 separates ordinary unscaled maximum-likelihood fit arithmetic from robust/scaled and categorical-estimator output. Arithmetic compatibility is not a judgment that a model is substantively well specified.

## Ordinary unscaled ML model fit

When `estimator_path="ml_unscaled"` and `unscaled_fit_statistics_verified=True`, Veritas may reconstruct:

- model chi-square p-value from chi-square and df;
- RMSEA after the software/paper convention for `N` versus `N-1` is explicitly verified;
- CFI and TLI when the baseline-model chi-square and df are verified;
- standard ML AIC and BIC when log-likelihood, number of free parameters, sample size, and information-criterion definition are available.

### RMSEA

The implemented point-estimate identity is

`RMSEA = sqrt(max((chi_square - df) / (df * N_basis), 0))`

where `N_basis` is explicitly either `N` or `N-1`. Veritas never chooses between these conventions implicitly.

### CFI

The conventional CFI identity is

`CFI = 1 - max(chi_t-df_t, 0) / max(chi_t-df_t, chi_b-df_b, 0)`

where the `t` quantities refer to the target model and the `b` quantities to the verified baseline model.

### TLI

The conventional TLI identity is

`TLI = (chi_b/df_b - chi_t/df_t) / (chi_b/df_b - 1)`

TLI is not forcibly clipped to [0, 1]. If the rounded baseline chi-square/df interval reaches 1, Veritas abstains because the denominator is unstable.

### Information criteria

For a verified standard ML definition:

- `AIC = -2 * logLik + 2 * k`
- `BIC = -2 * logLik + k * log(N)`

Sample-size-adjusted BIC and other variants are not mapped onto ordinary BIC.

## Nested-model chi-square difference

Direct subtraction is implemented only when all of the following are verified:

- the models are nested;
- they use the same sample;
- the test is ordinary unscaled ML;
- the less/more restrictive model identity is known.

Then:

- `Delta_chi_square = chi_square_more_restricted - chi_square_less_restricted`
- `Delta_df = df_more_restricted - df_less_restricted`
- the p-value uses a chi-square reference distribution with `Delta_df`.

## Robust/scaled estimators

Veritas v0.7 does **not** directly subtract scaled chi-square values. Mplus explicitly notes that Satorra-Bentler scaled chi-square values cannot be used for ordinary chi-square difference testing. MLM/MLR/WLSM require scaling-correction formulas; MLMV/WLSMV/ULSMV use DIFFTEST or estimator-specific procedures.

Likewise, robust/scaled CFI and RMSEA are not treated as ordinary unscaled fit indices. lavaan distinguishes robust and scaled fit measures, and historical releases document separate robust CFI/RMSEA calculations.

Primary anchors:

- lavaan current tutorial and `fitMeasures()` documentation: https://lavaan.ugent.be/tutorial/
- Mplus chi-square difference testing guidance: https://www.statmodel.com/chidiff.shtml
- Mplus technical note on TLI/CFI formulas: https://www.statmodel.com/download/TLI.pdf
