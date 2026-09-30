# Harness stress hardening

The research harness now has a dedicated concurrency and adversarial-payload stress lane in addition to the normal full test suite.

`python scripts/stress_harness_runtime.py` exercises three pressure points that are easy to miss in ordinary unit tests:

- many concurrent read-modify-write operations against the same audit through multiple `HarnessStore` instances;
- repeated replication control-plane activation/cancellation/deactivation cycles;
- oversized and deeply nested ACP event payloads that must be bounded before they can accumulate in the streaming queue or persisted event stream.

The `harness-stress` GitHub Actions workflow runs this lane for harness/replication changes and on `main`. It is a correctness stress test rather than a benchmark: timings are reported for diagnosis, but the job gates only on integrity and safety invariants so shared-runner variance does not create flaky failures.

The local JSON audit store remains a single-process design. Store instances inside one process share a root-scoped lock, and metadata writes use a unique fsync'd temporary file followed by atomic replacement. Deployments that intentionally run multiple OS worker processes against the same harness data directory should put an external serialization/storage layer in front of that directory rather than assuming the local store is a distributed database.
