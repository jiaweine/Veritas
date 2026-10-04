# Changelog

All notable repository-engineering changes should be recorded here before a governed software release is tagged.

Veritas deliberately separates software release state from scientific-validation authority. A changelog entry, package version, or GitHub Release does not by itself grant production evidence authority.

## Unreleased

No changes yet.

## 0.14.1 — 2026-10-04

This is the first governed Veritas software release. It packages the current repository engineering state without changing the documented scientific-evidence authority boundary.

### Added

- governed wheel/source-distribution release artifact smoke, including package metadata, console-entry-point, Web/PWA asset, clean-install, and CLI-version checks;
- tag/version equality enforcement and automated GitHub Release artifact publication with SHA-256 manifests;
- an exact-tag reusable full-CI gate that must succeed before GitHub Release publication;
- immutable full-commit pins for third-party actions used by active main/PR workflows, plus a regression gate that rejects future mutable action refs;
- an explicit release process documenting software/evidence authority boundaries.

### Fixed

- the `web` optional dependency set now declares `httpx`, which the Harness model-provider routes import at runtime; clean wheel installs no longer rely on the `dev` extra to make `veritas-harness` importable;
- the `dev` dependency set now includes `httpx2` for Starlette/FastAPI `TestClient`; CI promotes `StarletteDeprecationWarning` to an error so the legacy TestClient fallback cannot silently return;
- tag publication can no longer race an independent full-CI workflow: release creation now has an explicit dependency on the full detector/PDF CI result for the tagged commit.

### Product and reliability state carried by current `main`

- evidence-first Research Audit Workbench with separate Replication Runtime authority;
- persistent Audit Notes, Projects, Findings/Evidence inspection, Reproduction review, model-provider controls, native mobile client, PWA support, and real Chromium acceptance;
- bounded product-facing keyset/cursor pagination for Runs, Audits, Findings, and Benchmark history rather than unbounded history materialization in the browser;
- persisted Claim Graph authority in the product surface: validated graph payloads drive graph nodes/edges, unbound publication claim identity stays unbound, and detector findings remain non-edge annotations;
- strict Benchmark Result Envelope ingestion with detailed AuditBench raw reports kept separate from product envelopes;
- locked synthetic AuditBench detector regression gates, PDF extraction/geometry/adversarial gates, real-PDF research probes, and fail-closed evidence handling;
- parser-independent Claim Graph reconstruction and paper-only DiD/IV/RDD plus additional deterministic detector families;
- governed package artifact validation and exact-tag full-CI release orchestration, without equating software release readiness with scientific certification.

### Hosting governance boundary

- source-controlled CI/release gates are present, but GitHub hosting controls remain an administrator responsibility;
- at the 2026-10-04 completion audit, `main` was not protected and the repository had no active rulesets, so host-level prevention of authorized direct pushes/force-pushes/deletion is not yet machine-enforced by GitHub repository settings.

### Evidence boundary

- the locked synthetic AuditBench remains `production_certificate=false`;
- the frozen v0.15 real-paper extraction evidence path remains a non-production pilot;
- issues #2, #3, #5, and #26 remain open where completion requires genuine manual annotation, independent human review/adjudication, untouched evaluation, or external historical trust.

## History before governed releases

When this changelog was introduced, `pyproject.toml` declared package version `0.14.0`, while the repository had no GitHub Release. This file therefore does **not** invent or backfill a historical release record. Earlier implementation history remains authoritative in Git commits and merged pull requests.

See [`docs/RELEASE_PROCESS.md`](docs/RELEASE_PROCESS.md) for the release procedure and [`docs/REPOSITORY_COMPLETION.md`](docs/REPOSITORY_COMPLETION.md) for the engineering-versus-evidence completion boundary.
