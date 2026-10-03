# Repository completion boundary

This document separates **repository-completable engineering work** from evidence and governance milestones that require genuinely independent humans or external historical trust. It exists to prevent two opposite errors: treating an open evidence milestone as evidence that the core product is unfinished, or treating a green repository as proof that external validation has already happened.

## Engineering state

The repository-side Research Audit Harness is implemented as an evidence-first system with distinct authority boundaries:

- source-addressable Statistical Claim Graph objects preserve raw display strings, source locations, parsed values, precision/operators, extraction confidence, and claim-identity confidence;
- parser-independent detector-input reconstruction covers the supported statistical object families and DiD / IV / RDD design descriptors through a unified reconstruction entrypoint;
- deterministic detector families cover regression consistency, sample accounting, correlation feasibility, standardized-regression reconstruction, discrete feasibility, logit/odds-ratio arithmetic, mediation products, SEM fit arithmetic, DiD/IV/RDD design linting, and additional registered detector packs;
- paper-only design lint remains methodological-risk evidence rather than an inference about author intent;
- ambiguous extraction or applicability fails closed rather than being silently promoted to stronger evidence;
- Research Audit and Replication remain separate authority domains: successful code execution is a reproduction trace and does not automatically verify a scientific claim;
- the product shell includes persistent audit notes, evidence/finding inspection, projects, replication review, paged run observability, model-provider controls, PWA support, and real Chromium acceptance paths;
- Runs consume bounded keyset pagination end-to-end rather than materializing unbounded history;
- a byte-locked synthetic AuditBench CI regression gate executes real detectors and blocks exact-status, false-hard-alert, evidence-grade, and extraction-error regressions.

The synthetic AuditBench gate is intentionally marked `production_certificate=false`. It is a regression-control mechanism, not real-paper production certification.

## Open issues and their true remaining boundary

### #2 — Statistical Claim Graph and extraction boundary

Repository code is complete for the schema, round-trip preservation, uncertainty boundary, supported typed objects, parser-independent reconstruction, and unified detector-input dispatch.

The remaining acceptance item is a **genuinely manually annotated cross-discipline mini-corpus** covering economics, psychology/management, and sociology/political-science tables. Synthetic fixtures or AI-authored labels must not be relabeled as manual human annotation.

### #3 — paper-only reconstruction detector pack

The requested detector families are implemented, including the SEM fit-index arithmetic path and applicability/fail-closed behavior. Synthetic/adversarial tests and the locked synthetic AuditBench regression gate cover repository regressions.

The remaining production-evidence condition is manually adjudicated real-paper validation and a qualifying locked benchmark before broad E3 production enablement. That evidence is governed by #5 and #26.

### #5 — AuditBench

The repository contains a locked synthetic controlled-corruption CI gate with byte-level SHA-256 commitments, exact status checks, precision/recall, clean-paper false-hard-alert measurement, evidence-grade ceilings, extraction-error checks, and discipline/reporting-style slices.

The remaining milestone is the **production-grade real-paper benchmark** with independently reviewed/adjudicated evidence and untouched evaluation. The synthetic CI gate must not be represented as satisfying that requirement.

### #26 — independently reviewed real-paper extraction corpus

This milestone is intentionally outside what repository code or an AI coding agent can manufacture. Remaining work includes genuine reviewer A/B assignments, distinct human identities, independent adjudication, independent pre-TEST historical trust/archive material, DEVELOPMENT-only calibration, untouched TEST evaluation, and external provenance/trust verification.

No generated reviewer identities, copied submissions, synthetic adjudication, post-hoc trust roots, or self-authored correctness labels count as completion.

## Completion rule

Repository engineering may be considered complete when its code/tests/CI/documentation are green and no repository-completable implementation gaps remain. Evidence milestones remain open until their stated human/external evidence exists.

Accordingly, an open #2/#3/#5/#26 does **not** mean the core code is unfinished. It means Veritas is preserving a stricter claim: software implementation and scientific-validation authority are different things.
