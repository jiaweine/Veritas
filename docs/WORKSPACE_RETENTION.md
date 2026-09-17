# Replication workspace retention

Veritas keeps immutable paper/attachment artifacts and persisted run traces as the audit record. Per-run `replication-workspaces/<run_id>` directories are execution copies and may accumulate on long-running local installations.

Workspace cleanup is therefore an explicit **operator maintenance action**, not a browser feature and not a background job.

## Inspect

```bash
veritas-workspace-retention list
```

The command reads the local Harness data directory (`VERITAS_HARNESS_DATA` or `~/.veritas/harness`, unless `--data-dir` is supplied) and reports workspace state without modifying anything.

## Dry-run a retention cutoff

```bash
veritas-workspace-retention prune --older-than-hours 168
```

`prune` is a dry-run unless `--apply` is present. Workspace age is derived from the persisted terminal replication event (`finish` or `error`), not from filesystem modification time. A replication process can change workspace mtimes, so mtime is not treated as provenance.

## Apply cleanup

```bash
veritas-workspace-retention prune --older-than-hours 168 --apply
```

A workspace is eligible only when all of the following are true:

- its directory is a direct `replication-workspaces/<run_id>` child rather than a symlink;
- its `artifacts.json` is a regular JSON file with schema version `1` and the same `run_id` as the directory;
- the audit contains a persisted terminal replication event for that run;
- the terminal event is at least the requested number of hours old.

The command re-reads the audit and revalidates the workspace immediately before deletion. Running runs, unknown directories, malformed manifests, missing terminal provenance, and workspaces newer than the cutoff are left untouched.

## What cleanup never deletes

Retention never deletes or rewrites:

- the audit directory itself;
- `audit.json` or persisted detector/replication events;
- the immutable source `paper.pdf`;
- immutable audit attachments;
- benchmark result envelopes.

Only the per-run replication workspace copy is removed. Applied cleanup writes `maintenance` start/finish (or error) events to the audit. Those events record the target run id, terminal phase/time, workspace byte count, retention cutoff, and that cleanup was operator-driven; they do not record an absolute local path.

There is intentionally no `/api/v1` DELETE endpoint and no automatic cleanup scheduler. Operators remain in control of destructive maintenance, while the durable audit trace continues to show that a completed run existed and that its workspace copy was later pruned.
