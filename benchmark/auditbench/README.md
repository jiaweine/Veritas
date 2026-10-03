# AuditBench

`auditbench-v1-ci` is a locked **synthetic controlled-corruption regression gate** for deterministic detector behavior. It exists to catch trust-boundary regressions in CI; it is not a production certification and it does not replace the independently reviewed real-paper evidence milestone tracked in issue #26.

The exact UTF-8 bytes of `v1_protocol.json` and `v1_cases.json` are pinned by `v1_lock.json`. `scripts/run_auditbench_v1.py` refuses to evaluate modified bytes unless the lock is explicitly changed in the same reviewed change.

The primary gate measures exact status stability, alert precision/recall, paper-level false hard alerts, evidence-grade ceiling violations, extraction-error hard alerts, and slices by detector, materiality, discipline, and reporting style. Its locked corpus covers regression and sample arithmetic plus correlation feasibility, standardized-regression reconstruction, DiD, weak-IV, and RDD frontier behavior. It deliberately includes PASS, REVIEW, and UNVERIFIABLE design cases so paper-only methodological-risk detectors cannot silently drift into E3+ hard findings, while direct numerical contradictions such as an out-of-range reported correlation remain eligible for E3.

The frontier cases reuse stable detector fixtures rather than tuning detector thresholds against this locked corpus. Design-risk cases are capped at `METHODOLOGICAL_RISK`; unresolved applicability/extraction cases are capped at `UNVERIFIABLE`.

## v0.2 paper-only detector pack

`v02_pack_cases.json` and `v02_pack_lock.json` form a second byte-locked CI pack under the same production-denial protocol. `scripts/run_auditbench_v02_pack.py` executes the remaining detector families requested by issue #3: discrete/GRIM-style feasibility, logit coefficient ↔ odds-ratio arithmetic, mediation `a*b` arithmetic, and SEM fit-index reconstruction.

The pack locks three distinct authority behaviors:

- direct arithmetic contradictions in logit/odds-ratio, mediation products, and reconstructable SEM fit indices may remain `FAIL` with an `INTERNAL_CONTRADICTION` ceiling;
- discrete-summary infeasibility remains `FAIL` but is explicitly capped at `METHODOLOGICAL_RISK` until the real-paper certification requirement exists;
- unknown weighting, unverified exp(beta) identity, incompatible mediation scales, unknown RMSEA convention, and robust/scaled SEM formulas fail closed as `UNVERIFIABLE`.

This second pack is executed independently in CI and emits its own result envelope, so changes to one locked corpus cannot silently rewrite the other corpus's evidence contract.

A passing synthetic gate does **not** authorize E3+ production promotion. Production evidence remains governed by detector cards, development-only calibration, a locked untouched test split, independently reviewed/adjudicated real-paper gold, and the external trust/archive requirements tracked by issue #26.
