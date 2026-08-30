# Numerical Backend Governance

Numerical solvers are part of the Veritas methodology, not invisible implementation details.

## Why versions are locked

During v0.3 development, a clean GitHub Actions environment upgraded SCS from the previously validated `3.2.11` to `3.3.0`. The existing correlation-matrix SDP process terminated during solver execution rather than returning a normal Python exception. The same tests had passed with SCS `3.2.11`.

This incident established a project rule: a numerical detector may not assume that a newer solver release is behaviorally interchangeable with a validated release.

## Current policy

- `SCS==3.2.11` is pinned for the current SDP detectors.
- SDP detectors check the runtime SCS version before invoking the backend.
- A non-validated solver version produces `UNVERIFIABLE`; it does not attempt the solve.
- Solver versions are stored in `AuditProtocol.solver_versions` and therefore affect the protocol SHA-256.
- Solver-based high-severity promotion still requires AuditBench certification on the locked runtime stack.

## Separation of proof types

Veritas distinguishes solver-independent and solver-dependent evidence.

### Solver-independent

Examples:

- direct arithmetic contradictions;
- exponentiation/product identities with interval arithmetic;
- independently re-verified integer histogram witnesses;
- a constructed PSD correlation matrix whose implied beta vector satisfies the published intervals.

These checks do not become invalid merely because an optimizer package changes.

### Solver-dependent

Examples:

- semidefinite infeasibility;
- McCormick/SDP outer-relaxation infeasibility;
- MILP infeasibility.

These results must carry backend identity and remain subject to detector-specific severity ceilings and benchmark certification.

## Fail-closed rule

A timeout, inaccurate status, backend exception, unvalidated version, or numerical witness that fails independent re-verification is never converted into evidence of inconsistency. The detector returns `UNVERIFIABLE`.

## Future backend promotion

A newer solver release may replace a validated backend only after:

1. the complete detector unit suite passes;
2. constructive feasible cases show no new false alerts;
3. AuditBench development cases show no unexplained classification drift;
4. a locked benchmark comparison is recorded;
5. the methodology/runtime snapshot is versioned.

A solver upgrade therefore creates a new reproducible audit environment rather than silently changing past results.
