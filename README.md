# Veritas

**Evidence-first auditing for empirical social science research.**

Veritas is a research-oriented platform for auditing the internal consistency, methodological robustness, reproducibility, and provenance of empirical claims in social science papers.

> Veritas does **not** estimate a "fraud probability" and does not infer author intent. It separates **verification coverage** from **reliability risk**, and every finding must be backed by inspectable evidence.

## Core principles

1. **Missing data is not evidence of misconduct.** Unavailable data or code lowers verification coverage; it does not automatically increase reliability risk.
2. **Applicability before detection.** A detector runs only when its statistical assumptions and required evidence are satisfied.
3. **Deterministic checks before model judgments.** LLMs may extract and align claims; numerical contradiction tests are performed by auditable statistical code.
4. **Evidence grades, not accusations.** Findings range from `UNVERIFIABLE` and weak signals to internal or reproduction contradictions.
5. **Materiality matters.** A typo in an appendix and a contradiction in the primary causal estimate are not scored equally.
6. **Correlated findings are not double counted.** Multiple consequences of the same underlying numerical error belong to one evidence family.
7. **Protocol locking.** Detector versions, thresholds, assumptions, and artifact identities are frozen for an audit run.

## v0.1 scope

The first release focuses on **paper-only auditing**, because many social-science papers do not expose raw data or replication code.

- statistical object and empirical claim schemas
- evidence grade, materiality, coverage, and review-priority models
- applicability-gated detector registry
- rounding-aware regression consistency checks (`beta`, `SE`, `t`, `p`, confidence intervals, stars)
- sample accounting and arithmetic consistency checks
- immutable audit-protocol locks
- detector cards and benchmark-ready test cases

Planned next: correlation-matrix feasibility, standardized-regression reconstruction, GRIM-style discrete-data checks, DID/IV/RDD design linting, preregistration comparison, replication runners, and raw-data forensics.

## Status

Early research prototype. Findings are intended to support expert review, not to constitute a determination of research misconduct.
