# AuditBench

`auditbench-v1-ci` is a locked **synthetic controlled-corruption regression gate** for deterministic detector behavior. It exists to catch trust-boundary regressions in CI; it is not a production certification and it does not replace the independently reviewed real-paper evidence milestone tracked in issue #26.

The exact UTF-8 bytes of `v1_protocol.json` and `v1_cases.json` are pinned by `v1_lock.json`. `scripts/run_auditbench_v1.py` refuses to evaluate modified bytes unless the lock is explicitly changed in the same reviewed change.

The gate measures exact status stability, alert precision/recall, paper-level false hard alerts, evidence-grade ceiling violations, extraction-error hard alerts, and slices by detector, materiality, discipline, and reporting style. The first CI corpus covers coefficient/SE/p-value arithmetic, confidence-interval mismatch, hidden rounding compatibility, adjusted-p benign handling, missing-evidence fail-closed behavior, sample arithmetic, and non-exhaustive subgroup controls.

A passing synthetic gate does **not** authorize E3+ production promotion. Production evidence remains governed by detector cards, development-only calibration, a locked untouched test split, independently reviewed/adjudicated real-paper gold, and the external trust/archive requirements tracked by issue #26.
