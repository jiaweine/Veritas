# Stress test matrix

This matrix supplements the ordinary unit, integration, browser-smoke, PDF-regression, geometry-holdout, adversarial, and real-PDF lanes.

| Surface | Pressure case | Expected invariant |
| --- | --- | --- |
| Harness audit store | Hundreds of concurrent event appends through many store instances sharing one root | No lost events, no corrupt JSON, no leaked temporary metadata files |
| Attachment manifest | Concurrent immutable attachment creation | Every payload remains addressable by its recorded id and digest |
| Benchmark result store | Many store instances ingest the same content-addressed result concurrently | Idempotent single-record persistence with no temp-file collisions |
| Replication control plane | Repeated activation, state reads, cancellation, teardown | No stale active run and duplicate activation fails closed |
| ACP burst streaming | A real subprocess emits a dense burst below the per-turn event budget | Every accepted update is delivered without transport-order assumptions or callback deadlock |
| ACP flood limiting | A real subprocess exceeds a deliberately tiny event budget | The turn stops fail-closed with an explicit transport-limit event instead of unbounded growth |
| ACP event normalization | Oversized strings, collections, and recursive nesting | Event payloads are bounded before downstream persistence/rendering |
| Existing scientific pipeline | Full pytest plus extraction/PDF/adversarial/real-PDF jobs | Stress hardening must not change detector or evidence semantics |

The stress runner intentionally avoids pass/fail timing thresholds. Shared CI runners are noisy; correctness and bounded-resource invariants are the gate, while elapsed times are emitted for regression diagnosis.
