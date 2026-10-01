# Validated run pagination

The product Runs surface has two compatibility layers:

- `GET /api/v1/runs` keeps the historical full-list response.
- `GET /api/v1/run-pages?limit=...&cursor=...` is the bounded product feed.

The default product runtime builds a compact in-memory terminal-run projection while it validates each authoritative audit event journal. A cold process still scans the authoritative journal once. After that validation watermark is current, repeated Runs reads use the terminal projection instead of reparsing unrelated history.

The projection is not evidence and is never allowed to make an invalid journal look healthy. Before rows from an audit are returned, the current journal fingerprint must still match the fingerprint that was validated. A corrupt or concurrently changed journal is excluded from the projected page until a later successful validation rebuilds its projection.

Pagination uses an opaque keyset cursor over `(created_at, run_id)` in descending order. Clients must not decode or synthesize the cursor. The cursor is bounded, versioned, and rejected fail-closed when malformed. The maximum page size is 200 rows.

Explicitly supplied legacy/custom `AuditHarness` instances continue to work. Their pagination fallback may use a different opaque cursor representation; clients must treat all cursor values as server-owned tokens.

The run projection keeps scientific semantics unchanged: a completed replication agent run remains a reproduction trace, not detector verification or scientific evidence.