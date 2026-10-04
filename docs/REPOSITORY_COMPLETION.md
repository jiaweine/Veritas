# Repository completion boundary

This document separates **repository-completable engineering work** from evidence and governance milestones that require genuinely independent humans, external historical trust, or repository-admin hosting controls. It exists to prevent two opposite errors: treating an open evidence/governance milestone as evidence that the core product is unfinished, or treating a green repository as proof that external validation or host-level protection has already happened.

## Engineering state

The repository-side Research Audit Harness is implemented as an evidence-first system with distinct authority boundaries:

- source-addressable Statistical Claim Graph objects preserve raw display strings, source locations, parsed values, precision/operators, extraction confidence, and claim-identity confidence;
- the product Claim Graph surface consumes validated persisted `StatisticalClaimGraph` payloads rather than synthesizing claims/edges from detector output; when no publication claim identity is bound, no claim edge is inferred, and detector findings remain non-edge annotations;
- parser-independent detector-input reconstruction covers the supported statistical object families and DiD / IV / RDD design descriptors through a unified reconstruction entrypoint;
- deterministic detector families cover regression consistency, sample accounting, correlation feasibility, standardized-regression reconstruction, discrete feasibility, logit/odds-ratio arithmetic, mediation products, SEM fit arithmetic, DiD/IV/RDD design linting, and additional registered detector packs;
- paper-only design lint remains methodological-risk evidence rather than an inference about author intent;
- ambiguous extraction or applicability fails closed rather than being silently promoted to stronger evidence;
- Research Audit and Replication remain separate authority domains: successful code execution is a reproduction trace and does not automatically verify a scientific claim;
- the product shell includes persistent audit notes, evidence/finding inspection, projects, replication review, model-provider controls, native mobile/PWA support, and real Chromium acceptance paths;
- Runs, Audits, Findings, and persisted Benchmark history use bounded keyset/cursor feeds on product-facing paths instead of materializing unbounded history into the browser; legacy compatibility APIs remain separate from those bounded product paths;
- Benchmark results use strict result envelopes for product ingestion while detailed AuditBench reports remain separate raw artifacts; the Benchmarks UI exposes catalog/history state without turning heterogeneous suites into a fabricated global score;
- byte-locked synthetic AuditBench CI gates execute real detectors and block exact-status, false-hard-alert, evidence-grade, and extraction-error regressions across the supported paper-only detector families;
- package release readiness is machine-checked from built wheel/sdist artifacts, including package metadata, four console entry points, critical Web/PWA assets, clean-environment installation, and CLI version paths;
- governed `vX.Y.Z` publication requires tag/package/changelog identity, containment in `main`, immutable release assets, and both package artifact smoke and the reusable full detector/PDF CI on the exact tagged commit.

The synthetic AuditBench gates are intentionally marked `production_certificate=false`. They are regression-control mechanisms, not real-paper production certification. Likewise, a green software build or GitHub Release does not grant scientific-validation authority.

## Repository hosting boundary

Source-controlled CI and release orchestration are implemented, but they cannot prevent an authorized GitHub user from bypassing those workflows through repository-hosting configuration alone.

At the completion audit on 2026-10-04, GitHub reported:

- `main` is not a protected branch; and
- the repository has no active repository rulesets.

A governed hosting configuration should require pull requests and the intended required checks on `main`, and should reject force-pushes and branch deletion. Applying those controls requires repository-administration capability in GitHub and is not equivalent to a source-tree change. See `docs/RELEASE_PROCESS.md` for the release-policy boundary.

## Open issues and their true remaining boundary

### #2 — Statistical Claim Graph and extraction boundary

Repository code is complete for the schema, round-trip preservation, uncertainty boundary, supported typed objects, parser-independent reconstruction, unified detector-input dispatch, and the product-side persisted-graph authority boundary.

The remaining acceptance item is a **genuinely manually annotated cross-discipline mini-corpus** covering economics, psychology/management, and sociology/political-science tables. Synthetic fixtures or AI-authored labels must not be relabeled as manual human annotation.

### #3 — paper-only reconstruction detector pack

The requested detector families are implemented, including the SEM fit-index arithmetic path and applicability/fail-closed behavior. Synthetic/adversarial tests and the locked synthetic AuditBench regression gates cover repository regressions.

The remaining production-evidence condition is manually adjudicated real-paper validation and a qualifying locked benchmark before broad E3 production enablement. That evidence is governed by #5 and #26.

### #5 — AuditBench

The repository contains locked synthetic controlled-corruption CI gates with byte-level SHA-256 commitments, exact status checks, precision/recall, clean-paper false-hard-alert measurement, evidence-grade ceilings, extraction-error checks, and discipline/reporting-style slices. Their standard Benchmark Result Envelopes and detailed raw reports are kept distinct.

The remaining milestone is the **production-grade real-paper benchmark** with independently reviewed/adjudicated evidence and untouched evaluation. The synthetic CI gates must not be represented as satisfying that requirement.

### #26 — independently reviewed real-paper extraction corpus

This milestone is intentionally outside what repository code or an AI coding agent can manufacture. Remaining work includes genuine reviewer A/B assignments, distinct human identities, independent adjudication, independent pre-TEST historical trust/archive material, DEVELOPMENT-only calibration, untouched TEST evaluation, and external provenance/trust verification.

No generated reviewer identities, copied submissions, synthetic adjudication, post-hoc trust roots, or self-authored correctness labels count as completion.

## Completion rule

Repository engineering may be considered complete when its code/tests/CI/documentation are green and no repository-completable implementation gaps remain. Evidence milestones remain open until their stated human/external evidence exists, and repository-hosting governance remains incomplete until the required GitHub administration controls are actually enabled.

Accordingly, an open #2/#3/#5/#26 does **not** mean the core code is unfinished. It means Veritas is preserving a stricter claim: software implementation, scientific-validation authority, and repository-hosting authority are different things.
