# Veritas

**Evidence-first auditing for empirical social science research.**

Veritas is a research-oriented platform for auditing the internal consistency, methodological robustness, reproducibility, and provenance of empirical claims in social science papers.

> Veritas does **not** estimate a "fraud probability" and does not infer author intent. It separates **verification coverage** from **review priority**, and every finding must be backed by inspectable evidence.

## Why Veritas starts with paper-only auditing

Many empirical papers do not publish raw data or replication code. Veritas treats unavailable artifacts as a **coverage limitation**, not as evidence of misconduct. Paper-only auditing therefore focuses on checks that can be performed from the publication itself and expands when appendices, registrations, code, or data become available.

## Core principles

1. **Missing data is not evidence of misconduct.** Unavailable data or code lowers verification coverage; it does not automatically increase review priority.
2. **Applicability before detection.** A detector runs only when its statistical assumptions and required evidence are satisfied.
3. **Deterministic checks before model judgments.** LLMs may extract and align claims; numerical contradiction tests are performed by auditable statistical code.
4. **Evidence grades, not accusations.** Findings range from `UNVERIFIABLE` and weak signals to internal or reproduction contradictions.
5. **Materiality matters.** A typo in an appendix and a contradiction in the primary causal estimate are not scored equally.
6. **Correlated findings are not double counted.** Multiple consequences of the same underlying numerical error belong to one evidence family.
7. **Protocol locking.** Artifact identities, calibration, parser versions, object schemas, detector versions, promotion policies, and numerical runtime identities are locked for an audit run.
8. **Detector readiness is not production authority.** Benchmark and research calibrations may exercise the full detector pipeline without being allowed to publish a production-authorized hard finding.

## Current core

- statistical object and empirical claim schemas
- evidence grade, materiality, coverage, and review-priority models
- applicability-gated detector registry
- rounding-aware regression consistency checks (`beta`, `SE`, `t/z`, `p`, confidence intervals)
- conservative sample accounting checks
- correlation, discrete-summary, algebraic, ANOVA/group-summary, meta-analysis, SEM, standardized-regression, DID/IV/RDD experimental detectors
- native dual-parser PDF extraction with geometry fallback and precise source provenance
- conformal extraction gates with `PROMOTE` / `REVIEW` / `UNVERIFIABLE` behavior
- benchmark, research, and production calibration scopes
- held-out paper-level production-certification infrastructure
- source-tree, detector-registry, numerical-backend, parser, schema, and promotion-spec identity locking

## Detector promotion vs production authority

Veritas deliberately separates three questions:

1. **Was the reported statistical object extracted reliably enough to enter a detector?**
2. **What does the deterministic detector find?**
3. **Is this exact pipeline certified to issue a production-authorized hard finding?**

A benchmark run may therefore produce a mathematically valid E3 contradiction while still carrying:

```text
production_hard_finding_authorized = false
```

Production authority requires a held-out `ProductionCalibrationCertificate` tied to the exact calibration, parser versions, object schema, promotion spec, locked TEST benchmark, Veritas source tree, detector registry, and numerical backend. `AuditEngine.audit_production_verified()` also rechecks the current system identity before authorizing production findings.

The certificate is an auditable hash-bound provenance artifact, **not** a cryptographic signature, institutional endorsement, or finding of misconduct.

## Current real-PDF status

The current open-access PDF smoke, fail-closed, and selective-promotion benchmarks are **not production certification**. They run under benchmark scope to validate extraction and detector-promotion behavior. Production hard-authority coverage is intentionally expected to remain zero until a sufficiently large locked held-out corpus passes the strict paper-level certification policy for the exact deployed pipeline.

## Minimal example

```python
from veritas import AuditEngine, RegressionResult, ReportedNumber
from veritas.types import Materiality

result = RegressionResult(
    object_id="table4-col3",
    beta=ReportedNumber(0.183, decimals=3),
    se=ReportedNumber(0.041, decimals=3),
    p_value=ReportedNumber(0.017, decimals=3),
    materiality=Materiality.MAIN_EMPIRICAL_CLAIM,
)

summary = AuditEngine().audit([result])
print(summary.verification_coverage)
print(summary.review_priority)  # review priority, NOT fraud probability
print(summary.findings)
```

## Roadmap

Next layers include broader claim-graph extraction, preregistration comparison, isolated replication runners, raw-data/provenance forensics, larger real-paper extraction benchmarks, and a locked held-out certification corpus for production hard findings.

See [`docs/METHODS.md`](docs/METHODS.md), [`docs/DETECTOR_CARDS.md`](docs/DETECTOR_CARDS.md), [`docs/ROADMAP.md`](docs/ROADMAP.md), and [`docs/methods/pdf_ingestion_promotion.md`](docs/methods/pdf_ingestion_promotion.md).

## Status

Early research prototype. Findings are intended to support expert review, not to constitute a determination of research misconduct. The repository contains production-authority infrastructure, but the current real-PDF benchmark calibration is explicitly **not production-certified**.
