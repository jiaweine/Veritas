# Veritas

**Evidence-first auditing for empirical social science research.**

Veritas is a research-oriented platform for auditing the internal consistency, methodological robustness, reproducibility, and provenance of empirical claims in social science papers.

> Veritas does **not** estimate a "fraud probability" and does not infer author intent. It separates **verification coverage** from **review priority**, and every finding must be backed by inspectable evidence.

## Why Veritas starts with paper-only auditing

Many empirical papers do not publish raw data or replication code. Veritas treats unavailable artifacts as a **coverage limitation**, not as evidence of misconduct. v0.1 therefore focuses on checks that can be performed from the paper itself and is designed to expand when appendices, registrations, code, or data become available.

## Core principles

1. **Missing data is not evidence of misconduct.** Unavailable data or code lowers verification coverage; it does not automatically increase review priority.
2. **Applicability before detection.** A detector runs only when its statistical assumptions and required evidence are satisfied.
3. **Deterministic checks before model judgments.** LLMs may extract and align claims; numerical contradiction tests are performed by auditable statistical code.
4. **Evidence grades, not accusations.** Findings range from `UNVERIFIABLE` and weak signals to internal or reproduction contradictions.
5. **Materiality matters.** A typo in an appendix and a contradiction in the primary causal estimate are not scored equally.
6. **Correlated findings are not double counted.** Multiple consequences of the same underlying numerical error belong to one evidence family.
7. **Protocol locking.** Detector versions, thresholds, assumptions, and artifact identities are frozen for an audit run.

## v0.1 core

- statistical object and empirical claim schemas
- evidence grade, materiality, coverage, and review-priority models
- applicability-gated detector registry
- rounding-aware regression consistency checks (`beta`, `SE`, `t/z`, `p`, confidence intervals)
- conservative sample accounting checks
- immutable audit-protocol locks
- detector cards and benchmark-ready tests

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

Next layers are correlation-matrix reconstruction, GRIM-style discrete-data feasibility, logit/odds-ratio algebra, SEM/mediation checks, DID/IV/RDD design linting, preregistration comparison, isolated replication runners, and raw-data/provenance forensics.

See [`docs/METHODS.md`](docs/METHODS.md), [`docs/DETECTOR_CARDS.md`](docs/DETECTOR_CARDS.md), and [`docs/ROADMAP.md`](docs/ROADMAP.md).

## Status

Early research prototype. Findings are intended to support expert review, not to constitute a determination of research misconduct.
