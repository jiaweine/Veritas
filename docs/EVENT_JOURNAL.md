# Harness event journal

Veritas persists each audit under its local Harness data directory. Mutable audit metadata remains in `audit.json`, while structured Harness events are stored in an append-only `events.ndjson` journal once the audit receives its first event.

This split exists to keep long detector and replication traces from repeatedly rewriting the entire event history. A replication agent can emit hundreds or thousands of structured updates; appending one NDJSON record and then updating compact metadata avoids quadratic metadata write amplification.

## On-disk shape

```text
audit_<id>/
├── audit.json
├── events.ndjson
├── paper.pdf
├── attachments/
└── replication-workspaces/
```

After journal activation, `audit.json` keeps `events: []` plus a versioned marker:

```json
{
  "event_journal": {
    "schema_version": "1",
    "path": "events.ndjson"
  },
  "events": []
}
```

Public Harness reads remain compatible: `HarnessStore.get_audit()` and `list_audits()` hydrate the journal back into the returned `events` array. The split is an on-disk storage detail, not a change to event identity or run semantics.

## Legacy migration

Older workspaces may contain their complete event history inline in `audit.json`. Veritas leaves those audits readable as-is. On the first subsequent event append it writes the existing history to a temporary NDJSON file, fsyncs it, atomically replaces `events.ndjson`, records the journal marker, and then appends the new event. A completed journal is authoritative if a crash happens between journal replacement and metadata compaction, preventing duplicate migration.

## Integrity behavior

Journal reads are fail-closed. Veritas rejects malformed JSON entries, blank lines, missing journals referenced by metadata, symlink replacements, and non-regular journal files. On platforms that provide `O_NOFOLLOW`, journal reads and appends also open the file descriptor without following a final symlink and verify the opened descriptor is a regular file.

The existing same-process root-scoped lock serializes writes from multiple `HarnessStore` instances that share one data root. This does **not** turn the local filesystem store into a multi-process or distributed database. Deployments with multiple worker processes or replicas still require a storage layer designed for cross-process serialization.

## Durability boundary

Each event line is flushed and fsynced before `append_event()` returns. `audit.json` metadata continues to use write-to-temporary + fsync + atomic replacement. Optional telemetry export remains downstream of the durable local event append and cannot change the stored audit result.
