# Detector cards

A detector may emit `E3+` only after its applicability rules and false-positive behavior are documented and benchmarked.

## regression_consistency@0.1.0

**Purpose:** identify algebraic contradictions among reported regression coefficient, standard error, t/z statistic, p-value, and confidence interval.

**Requires:** coefficient + SE. Individual subchecks require the corresponding reported statistic.

**Conservative safeguards:**

- reported decimals are treated as rounding intervals;
- adjusted p-values are not compared to unadjusted beta/SE statistics;
- Student-t p/CI checks require degrees of freedom;
- unknown inference distributions are `UNVERIFIABLE`;
- missing optional statistics are `NOT_RELEVANT`, not a coverage penalty;
- missing evidence lowers coverage rather than increasing risk.

**Can emit:** `E3 INTERNAL_CONTRADICTION`.

**Known limitations:** table extraction errors, ambiguous coefficient scales, nonstandard pivots, transformed parameters, bootstrap/randomization inference, and journal-specific star legends.

**Validation gate before production red flags:** synthetic rounding boundary tests + manually adjudicated paper examples; target paper-level false hard-alert rate below 1% on the locked benchmark.

## sample_accounting@0.1.0

**Purpose:** check arithmetic consistency of reported sample partitions.

**Hard contradiction conditions:**

- non-overlapping groups sum to more than total N; or
- an explicitly exhaustive partition does not sum to total N.

**Weak-review condition:** unequal counts with no explanation when exhaustiveness is unknown.

**Can emit:** `E1` or `E3`.

**Known limitations:** overlapping categories, changing analysis samples, missing outcomes, weighting, repeated observations, panel unit-vs-row counts, and ambiguous captions.
