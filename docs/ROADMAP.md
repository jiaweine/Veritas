# Roadmap

Veritas separates **implemented**, **experimentally validated**, and **production-certified** capability. A detector or PDF path being implemented does not imply production authority.

## Through v0.10 — evidence-first paper auditing foundation

### Core evidence model — implemented

- [x] evidence grades and materiality
- [x] verification coverage separated from review priority
- [x] statistical-object / empirical-claim graph schemas
- [x] applicability-gated detector registry
- [x] correlated-finding-aware review priority
- [x] immutable protocol and artifact identity locks

### Paper-only numerical auditing — implemented, detector-specific maturity varies

- [x] rounding-aware regression consistency (`beta`, `SE`, `t/z`, `p`, confidence intervals)
- [x] conservative sample accounting
- [x] correlation-matrix PSD feasibility under rounding constraints
- [x] standardized-regression reconstruction from correlation matrices
- [x] discrete-summary / GRIM-style feasibility with applicability gates
- [x] logit / odds-ratio and mediation algebra
- [x] two-group and ANOVA summary arithmetic
- [x] meta-analysis arithmetic, HKSJ, and prediction-interval checks
- [x] SEM / CFA fit arithmetic and nested-model checks
- [x] DID, IV, and RDD design-risk detectors

Most non-core detectors remain **experimental** until their detector cards and held-out validation justify higher authority.

### PDF extraction and selective promotion — implemented and benchmarked

- [x] dual native PDF parser path
- [x] borderless-table geometry fallback
- [x] precise page/table/row/source provenance
- [x] calibrated extraction `ACCEPT` / conflict / domain-shift behavior
- [x] `PROMOTE` / `REVIEW` / `UNVERIFIABLE` detector-input gate
- [x] real open-access PDF extraction smoke benchmark
- [x] real fail-closed ambiguity / wrong-page / absent-row controls
- [x] real selective-promotion benchmark

Current real-PDF benchmarks are **benchmark evidence, not production certification**.

### AuditBench and authority governance — infrastructure implemented

- [x] deterministic paper-level train/development/test assignment
- [x] benchmark-manifest hashing
- [x] controlled synthetic corruption benchmarks
- [x] paper-level false-hard-alert calibration
- [x] exact one-sided Clopper-Pearson certification bounds
- [x] explicit `UNVERIFIED` / `BENCHMARK` / `RESEARCH` / `PRODUCTION_CERTIFIED` scopes
- [x] held-out `ProductionCalibrationCertificate`
- [x] certificate binding to calibration, parsers, schema, promotion spec, TEST manifest, policy, report, and audited system
- [x] fail-closed source-tree / detector-registry / numerical-runtime recertification
- [x] explicit non-production and production audit APIs

No current real-PDF calibration is production-certified.

## v0.11 — real-paper extraction generalization

Primary goal: move from a four-case regression-table smoke benchmark toward a diverse, locked extraction corpus without weakening abstention.

### Benchmark governance — implemented in v0.11 branch

- [x] introduce article-family split locks to prevent near-duplicate leakage across development/test
- [x] bind split locks to the exact corpus-manifest SHA-256, not only family assignments
- [x] benchmark table/row identity separately from numeric-field accuracy
- [x] benchmark semantic-gate extraction separately from numeric extraction
- [x] report coverage–selectivity curves rather than a single extraction threshold
- [x] move the four existing real-PDF cases into an explicit seed manifest
- [x] prevent seed cases from carrying locked splits or production authority
- [x] require independent double review and review-record hashes before extraction targets can enter locked gold
- [x] expose DEVELOPMENT-only threshold selection; TEST observations are rejected from calibration APIs
- [x] bind frozen extraction thresholds to development-manifest and policy hashes before TEST evaluation
- [x] register adversarial negative families as a non-production benchmark contract

The current four PLOS cases remain **seed cases**, not locked gold. Their legacy manual checks must be replaced by two independent reviewers plus adjudication before they can enter a frozen benchmark split.

### Corpus expansion and lock — remaining

- [ ] expand real open-access extraction corpus across journals, layouts, and statistical object types
- [ ] instantiate and execute adversarial fixtures for repeated labels, continuation tables, footnotes, multi-panel tables, and OCR-like text corruption
- [ ] complete independent double review and adjudication for extraction gold targets
- [ ] run geometry/native threshold calibration on locked DEVELOPMENT data using the development-only selection API
- [ ] freeze a genuinely untouched extraction TEST set
- [ ] publish coverage–selectivity curves on that locked development/TEST protocol

## v0.12 — end-to-end empirical claim graph

Primary goal: connect publication language to the statistical object being audited.

- [ ] extract candidate `Claim -> Estimate -> Sample -> Data -> Code -> Assumption` links from paper artifacts
- [ ] align abstract/main-text claims with exact table/figure estimands
- [ ] normalize scale transformations and outcome/treatment identities
- [ ] require high-confidence identity before cross-location E3 findings
- [ ] propagate source spans and extraction uncertainty through graph edges
- [ ] evaluate claim identity independently from detector correctness

## v0.13 — reproducibility artifacts

Primary goal: add stronger evidence when authors provide code/data, while keeping unavailable artifacts neutral.

- [ ] isolated R and Python replication runners with network disabled
- [ ] environment and dependency capture
- [ ] generated table/figure to publication-object matching
- [ ] processed-data and code provenance graph
- [ ] optional licensed Stata adapter
- [ ] E4 reproduction-contradiction evidence path

## v0.14 — data and preregistration integrity

- [ ] preregistration / PAP / registry comparison
- [ ] raw-to-analysis sample lineage
- [ ] undocumented exclusion and transformation checks
- [ ] survey careless-response modules with multi-signal applicability gates
- [ ] provenance and randomization-record checks where artifacts permit
- [ ] E5 direct data/provenance concern path with human-review escalation rules

## Production-certification milestone

Production hard-finding authority remains a separate milestone rather than a version checkbox. It requires a sufficiently large, locked, held-out paper corpus to satisfy the certification policy for the **exact** parser/schema/promotion-spec/source-tree/detector/numerical-runtime combination being deployed.

Until then, benchmark/research detector outputs may support methodological development and expert review but must remain `production_hard_finding_authorized = false`.
