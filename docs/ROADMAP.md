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
- [x] seal untouched extraction TEST membership to exact gold-manifest and split-lock hashes
- [x] register adversarial negative families as a non-production benchmark contract
- [x] execute gating synthetic adversarial fixtures for repeated labels, continuation tables, footnotes, multi-panel tables, and OCR-like text corruption

### External evidence orchestration — implemented

- [x] maintain an explicitly unlabeled real-paper sampling frame separate from benchmark labels
- [x] precommit exact sampling-frame bytes, normalized frame identity, exact seed-manifest bytes, review protocol, split salt, and the full threshold grid before TEST
- [x] require reviewed gold papers/families to come from the precommitted sampling frame and the exact precommitted seed manifest
- [x] mechanically bind deterministic family lock, frozen DEVELOPMENT threshold, TEST seal, and TEST evaluation lock into one release chain
- [x] require published DEVELOPMENT and TEST coverage–selectivity curves to use the exact precommitted threshold grid
- [x] issue an immutable non-production release receipt only when the complete evidence chain validates

The evidence workflow is implemented by `src/veritas/extraction_evidence_workflow.py` and `scripts/build_extraction_evidence_plan.py`. It prevents benchmark stages from being silently reordered or mixed across sampling frames, seed manifests, review protocols, split salts, threshold grids, DEVELOPMENT locks, or TEST seals. It does not generate labels or simulate independent reviewers.

The current four PLOS cases remain **seed cases**, not locked gold. Their legacy manual checks must be replaced by two independent reviewers plus adjudication before they can enter a frozen benchmark split. The synthetic adversarial benchmark is a deterministic fail-closed regression gate; it does not substitute for diverse real-paper negative examples.

### Corpus expansion and lock — external evidence work remaining

- [ ] expand real open-access extraction corpus across journals, layouts, and statistical object types
- [ ] add real-world adversarial examples for continuation tables, multi-panel layouts, footnotes, repeated labels, and OCR-like extraction failures
- [ ] complete independent double review and adjudication for extraction gold targets
- [ ] run geometry/native threshold calibration on locked DEVELOPMENT data using the development-only selection API
- [ ] freeze a genuinely untouched extraction TEST set from reviewed real-paper gold
- [ ] publish coverage–selectivity curves on that locked development/TEST protocol

These items require new real-paper evidence and genuinely independent human review. The repository now contains the sampling-frame/seed commitment, review, split, calibration, TEST sealing, curve, and release-receipt machinery; Veritas must not fabricate reviewer independence or claim held-out results before that evidence exists.

## v0.12 — end-to-end empirical claim graph

Primary goal: connect publication language to the statistical object being audited.

### Claim-identity substrate — implemented

- [x] extract candidate `Claim -> Estimate -> Sample -> Data -> Code -> Assumption` links from artifact-derived graph nodes
- [x] align abstract/main-text claims with exact table/figure estimands
- [x] normalize scale transformations and outcome/treatment identities
- [x] require high-confidence identity before cross-location E3 findings
- [x] propagate source spans and extraction uncertainty through graph edges
- [x] evaluate claim identity independently from detector correctness

The v0.12 implementation is a deterministic graph/identity and fail-closed audit substrate. It does not claim that arbitrary papers can already be converted into perfect claim graphs without held-out real-paper evaluation. See `docs/CLAIM_GRAPH_IDENTITY.md`.

## v0.13 — reproducibility artifacts

Primary goal: add stronger evidence when authors provide code/data, while keeping unavailable artifacts neutral.

### Reproducibility-artifact substrate — implemented

- [x] isolated R and Python replication runners with network disabled
- [x] environment and dependency capture
- [x] generated table/figure to publication-object matching
- [x] processed-data and code provenance graph
- [x] optional licensed Stata adapter
- [x] E4 reproduction-contradiction evidence path

The v0.13 implementation builds on the v0.11 fail-closed reproduction control plane. OCI execution requires a compatible host runtime; CI validates the isolation command contract and security gates rather than pretending to certify a daemon that is not present. The optional Stata adapter requires explicit licensed-runtime authorization from the deployment. The public E4 constructor internally invokes the canonical fully-attested report builder and cannot accept a caller-forged `ReproductionReport`. See `docs/REPRODUCIBILITY_ARTIFACTS.md` and `docs/reproduction-security-invariants-v0.11.md`.

These software capabilities remain separate from held-out production certification and from case-specific independent artifact/method review.

## v0.14 — data and preregistration integrity

### Data/provenance integrity substrate — implemented

- [x] preregistration / PAP / registry comparison
- [x] raw-to-analysis sample lineage
- [x] undocumented exclusion and transformation checks
- [x] survey careless-response modules with multi-signal applicability gates
- [x] provenance and randomization-record checks where artifacts permit
- [x] E5 direct data/provenance concern path with human-review escalation rules

The v0.14 implementation distinguishes protocol deviations, review signals, and direct provenance contradictions. Undocumented analysis operations and survey-response diagnostics do not create E5 findings by themselves. E5 requires a verified direct artifact/randomization/lineage identity mismatch, forces human-review escalation, forbids intent inference, and remains non-production by default. Missing raw/registration/randomization artifacts remain neutral or `UNVERIFIABLE`. See `docs/DATA_PREREGISTRATION_INTEGRITY.md`.

## Production-certification milestone — external evidence work remaining

Production hard-finding authority remains a separate milestone rather than a version checkbox. It requires a sufficiently large, locked, held-out paper corpus to satisfy the certification policy for the **exact** parser/schema/promotion-spec/source-tree/detector/numerical-runtime combination being deployed.

Until then, benchmark/research detector outputs may support methodological development and expert review but must remain `production_hard_finding_authorized = false`.
