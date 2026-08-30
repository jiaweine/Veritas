# Veritas v0.1 methodology

## 1. What Veritas judges

Veritas audits **empirical claims and their evidence**, not researcher intent. An automated finding can establish that reported quantities are mutually incompatible, that a stated design has a known identification risk, or that a reproduction attempt disagrees with a published claim. It cannot, by itself, establish fabrication or falsification.

The platform keeps two axes separate:

- **Verification coverage**: how much relevant evidence could actually be checked from available artifacts.
- **Review priority**: how strongly the findings justify expert review.

Missing data/code lowers coverage. It does not add reliability risk.

## 2. Evidence grades

- `E0 UNVERIFIABLE`: required evidence is unavailable or assumptions cannot be established.
- `E1 WEAK_SIGNAL`: unusual or incompletely explained pattern with plausible benign explanations.
- `E2 METHODOLOGICAL_RISK`: a design/inference choice is vulnerable under recognized conditions.
- `E3 INTERNAL_CONTRADICTION`: reported quantities cannot all be true under the paper's stated procedure.
- `E4 REPRODUCTION_CONTRADICTION`: a controlled rerun cannot recover a reported result.
- `E5 DATA_PROVENANCE_CONCERN`: direct contradiction involving data lineage, exclusions, randomization, or provenance.

Even E5 is a research-integrity concern, not an automated judgment of intent.

## 3. Materiality

`M0` formatting, `M1` peripheral, `M2` secondary result, `M3` main empirical claim, `M4` changes the substantive conclusion.

Evidence strength is a function of grade, materiality, applicability confidence, extraction confidence, and validated detector precision.

## 4. Coverage semantics

Every detector emits checks with one of five states:

- `PASS`
- `FAIL`
- `REVIEW`
- `UNVERIFIABLE`
- `NOT_RELEVANT`

Coverage is `(PASS + FAIL + REVIEW) / (PASS + FAIL + REVIEW + UNVERIFIABLE)`, weighted by check importance. `NOT_RELEVANT` is excluded from both numerator and denominator.

## 5. v0.1 regression consistency

The regression detector treats displayed numbers as rounded intervals instead of exact latent values. For a value printed to `d` decimals, Veritas considers the latent quantity to lie within half a unit in the last displayed decimal.

Given compatible intervals for coefficient `beta` and standard error `SE`, Veritas derives the full possible interval for `beta / SE`. A reported t/z statistic is an E3 contradiction only if its own rounding interval does not intersect the implied interval.

P-values are checked only when the inference distribution is specified and the p-value is not marked as adjusted. Bootstrap, randomization-inference, multiplicity-adjusted, or otherwise nonstandard p-values should remain `UNVERIFIABLE` until a detector explicitly models that procedure.

This conservative design follows the general lesson from statcheck: rounding and deliberate statistical corrections can create apparent inconsistencies and therefore must be modeled before flagging a contradiction.

## 6. v0.1 sample accounting

Group counts are a hard contradiction only when they are explicitly an exhaustive partition, or when non-overlapping groups sum to more than the reported total. Unequal totals without an exhaustiveness claim are not treated as contradictions.

## 7. Planned design-specific detectors

DiD, IV, RDD, RCT, survey, SEM, mediation, and meta-analysis detectors will be applicability-gated. For example, staggered-adoption TWFE should produce a methodological-risk finding only when the required timing/heterogeneity conditions are present; merely using TWFE is not itself an error.

## References informing the design

- Nuijten et al., statcheck: automated reporting-consistency checks with explicit treatment of rounding and known limitations.
- Callaway & Sant'Anna, Difference-in-Differences with Multiple Time Periods.
- Baker, Callaway, Cunningham, Goodman-Bacon & Sant'Anna, Difference-in-Differences Designs: A Practitioner's Guide (JEL, 2026).

Detector-specific references and validation evidence belong in `DETECTOR_CARDS.md` and must be updated before a detector can emit high-severity findings.
