# Group-summary reconstruction

Veritas reconstructs group-comparison statistics only when the paper reports enough information to identify the intended statistic and its scale. Displayed decimal values are treated as rounding intervals, not exact latent values.

## Two independent groups

For verified independent, unweighted groups with sample SDs, Veritas can reconstruct:

- `mean_A - mean_B`;
- Student equal-variance `t` and `df`;
- Welch `t` and Welch-Satterthwaite `df`;
- two-sided `p`, including inequality reports such as `p < .05`;
- pooled-SD Cohen's `d`;
- Hedges' `g` when the small-sample correction is explicitly identified.

Student and Welch tests are distinct applicability paths. An unknown test definition never falls back to a guessed formula.

For Welch inference, let

`A = s_A^2 / n_A`, `B = s_B^2 / n_B`, and `r = A / B`.

Then

`df(r) = (r + 1)^2 / (r^2/(n_A-1) + 1/(n_B-1))`.

Rounding intervals for the two SDs imply an interval for `r`. The global extrema of the Welch df over that interval occur at its endpoints and, when included, the unique stationary point

`r* = (n_A - 1)/(n_B - 1)`.

This avoids pretending that the printed SD midpoints are exact.

## Classical one-way ANOVA

For a verified classical independent-groups one-way ANOVA, Veritas reconstructs the feasible ranges of:

- numerator and denominator degrees of freedom;
- between-group sum of squares;
- within-group sum of squares;
- `F`;
- the corresponding unadjusted `p`;
- eta-squared when that effect-size definition is explicitly verified.

### Global lower bound for between-group SS

For group means `m_i` with weights `n_i`,

`SS_B = sum_i n_i (m_i - m_bar)^2 = min_c sum_i n_i (m_i-c)^2`.

If each latent mean lies in a printed rounding interval `I_i`, then

`min_{m_i in I_i} SS_B = min_c sum_i n_i dist(c, I_i)^2`.

The right side is a one-dimensional convex function. Veritas solves its monotone first-order condition by bisection and slightly expands the resulting bound in the conservative direction.

### Global upper bound for between-group SS

`SS_B` is convex in the vector of group means. Over a hyperrectangle of rounding intervals, a maximum is attained at a vertex. For up to 12 groups, Veritas enumerates all vertices exactly. For larger designs, it uses a looser range-based upper bound rather than allowing combinatorial cost to create an unsafe approximation.

### Within-group SS

For sample SDs,

`SS_W = sum_i (n_i - 1) s_i^2`.

This is monotone in each nonnegative SD, so its lower and upper rounding-compatible bounds are obtained directly from the SD interval endpoints.

The resulting conservative intervals propagate to `F`, `p`, and eta-squared. A wider interval may reduce detection power, but it cannot justify a harder finding.

## Applicability gates

A group-summary reconstruction abstains when required semantics are unknown, including relevant cases such as:

- paired/repeated observations presented as independent groups;
- survey or analytic weights;
- population SD versus sample SD ambiguity;
- Welch versus pooled-variance test ambiguity;
- adjusted p-values without the adjustment rule;
- standardized-effect denominator not identified;
- ANOVA variant not verified as classical one-way independent-groups ANOVA;
- summary inputs reported only as inequalities rather than equality values.

Unreported redundant statistics are `NOT_RELEVANT`, not `UNVERIFIABLE`.

## Severity

When the statistic definition and all required semantics are explicitly verified, a deterministic disjoint feasible interval is an internal mathematical contradiction and can support E3. This is evidence about the reported numbers, not evidence about author intent.
