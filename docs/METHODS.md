# Veritas methodology

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

## 5. Regression consistency

The regression detector treats displayed numbers as rounded intervals instead of exact latent values. For a value printed to `d` decimals, Veritas considers the latent quantity to lie within half a unit in the last displayed decimal.

Given compatible intervals for coefficient `beta` and standard error `SE`, Veritas derives the full possible interval for `beta / SE`. A reported t/z statistic is an E3 contradiction only if its own rounding interval does not intersect the implied interval.

P-values are checked only when the inference distribution is specified and the p-value is not marked as adjusted. Bootstrap, randomization-inference, multiplicity-adjusted, or otherwise nonstandard p-values should remain `UNVERIFIABLE` until a detector explicitly models that procedure.

This conservative design follows the general lesson from statcheck: rounding and deliberate statistical corrections can create apparent inconsistencies and therefore must be modeled before flagging a contradiction.

## 6. Sample accounting

Group counts are a hard contradiction only when they are explicitly an exhaustive partition, or when non-overlapping groups sum to more than the reported total. Unequal totals without an exhaustiveness claim are not treated as contradictions.

## 7. Detector promotion is not production authority

Veritas treats PDF extraction as an uncertain measurement process. Statistical objects do not enter deterministic detectors merely because a parser emitted a value.

The ingestion layer distinguishes:

- `UNVERIFIED`: no calibration-authority claim;
- `BENCHMARK`: evaluation-only calibration;
- `RESEARCH`: research use without production authority;
- `PRODUCTION_CERTIFIED`: eligible for production authority only with a matching held-out certificate.

A detector-ready object has satisfied the extraction and promotion contract. That fact alone says nothing about whether a resulting hard finding may be presented as production-authorized.

`AuditEngine.audit_verified()` always runs without production authority, even if an envelope happens to carry a production certificate. Only `AuditEngine.audit_production_verified()` may authorize production hard findings, and it revalidates the certificate against the currently executing system identity.

## 8. Held-out production certification

Production certification is paper-level, not finding-level. Multiple correlated findings within one paper count once.

A `ProductionCalibrationCertificate` may be issued only from a locked `TEST` split whose paper-level outcome labels agree exactly with the benchmark manifest and whose certification report passes policy.

The default strict policy requires at least 300 applicable clean papers and 50 applicable positive papers, with a 95% one-sided exact Clopper-Pearson upper bound on the paper-level false hard-alert rate of at most 1%, and a 95% one-sided exact lower bound on hard-alert precision of at least 95%.

Certificate v2 binds:

- calibration SHA-256;
- parser ids and versions;
- object-schema version;
- promotion-spec SHA-256;
- TEST benchmark-manifest SHA-256;
- audited Veritas-system SHA-256;
- certification-policy SHA-256;
- certification-report SHA-256.

The certificate is a deterministic, hash-bound provenance artifact. It is not a cryptographic signature, institutional endorsement, or research-misconduct determination.

## 9. System identity and fail-closed recertification

The audited system manifest binds:

1. the exact installed `veritas/**/*.py` source-tree bytes;
2. detector ids and declared versions;
3. numerical backend versions, including Python, NumPy, SciPy, CVXPY, and SCS.

The ingestion protocol and certificate separately bind parser versions and object schema, while promotion binds the exact `PromotionSpec` hash.

Consequences are intentionally strict:

- changing Veritas source code invalidates an old system certificate;
- changing a detector registry invalidates an old system certificate;
- changing numerical software invalidates an old system certificate;
- changing parser versions or object schema makes a production protocol invalid;
- changing promotion thresholds or required fields makes promotion `UNVERIFIABLE` under the old certificate.

This is intentionally more conservative than relying on manual semantic versioning alone.

## 10. Design-specific detectors

DiD, IV, RDD, RCT, survey, SEM, mediation, and meta-analysis detectors are applicability-gated. For example, staggered-adoption TWFE should produce a methodological-risk finding only when the required timing/heterogeneity conditions are present; merely using TWFE is not itself an error.

Design-risk findings normally remain E2 unless a deterministic contradiction is available from reported quantities or supplied artifacts.

## 11. Current real-PDF status

The current open-access PDF extraction, fail-closed, and selective-promotion benchmarks are benchmark evidence, **not production certification**. Their purpose is to validate extraction fidelity, abstention behavior, and detector-promotion mechanics on real documents.

Production authority should remain zero until a sufficiently large, locked held-out TEST corpus satisfies the certification policy for the exact deployed parser/schema/spec/system combination.

## References informing the design

- Nuijten et al., statcheck: automated reporting-consistency checks with explicit treatment of rounding and known limitations.
- Callaway & Sant'Anna, Difference-in-Differences with Multiple Time Periods.
- Baker, Callaway, Cunningham, Goodman-Bacon & Sant'Anna, Difference-in-Differences Designs: A Practitioner's Guide (JEL, 2026).

Detector-specific references and validation evidence belong in `DETECTOR_CARDS.md`. PDF-ingestion and production-authority details are specified in `docs/methods/pdf_ingestion_promotion.md` and must be updated before a pipeline may be represented as production-certified.
