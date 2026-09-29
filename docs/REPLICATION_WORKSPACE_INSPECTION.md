# Replication Workspace Inspection

Veritas can inspect the exact per-run workspace left behind by a persisted ACP replication run. This surface exists for **auditability**: it lets an operator see which bytes Veritas staged, whether those staged copies changed during the run, and which files the agent created.

It is deliberately **not** a sandbox claim, a reproduction-success verdict, or an evidence-authority upgrade.

## Scope

A replication run uses a directory shaped like:

```text
<audit>/replication-workspaces/<run_id>/
├── paper.pdf
├── artifacts.json
├── attachments/
│   └── <attachment_id>/
│       └── <sanitized filename>
└── ... agent-created outputs ...
```

Before the ACP agent starts, the Harness already verifies the immutable audit-store paper and attachments. Only verified bytes are copied into the run workspace. `audit.json` is never staged.

After the run has produced a persisted `replication.acp` run id, the workspace inspector can classify the run directory without exposing arbitrary host paths.

## Authorization model

Workspace inspection is authorized by repository state, not by a client-provided filesystem path.

The server requires all of the following:

1. the requested audit exists;
2. the run id matches the canonical `run_<12 lowercase hex>` form;
3. the audit event history contains that exact run id;
4. the matching event identifies `run_kind=replication` and `tool=replication.acp`;
5. the workspace root is a real directory rather than a symlink;
6. the resolved workspace remains inside the requested audit directory.

A run from another audit therefore cannot be used to browse that audit's workspace.

## Staged-input integrity

The inspector reconstructs the expected staged object identities from trusted audit metadata rather than trusting a potentially modified workspace manifest.

The expected set is:

- `paper.pdf`, bound to the audit's stored paper SHA-256;
- each attachment, bound to its stored attachment id, sanitized filename, SHA-256, and byte size;
- `artifacts.json`, reconstructed using the same canonical content written when the run workspace was created.

Workspace entries are classified as:

- `staged_unchanged` — an expected staged regular file still matches its expected identity;
- `staged_modified` — an expected staged path exists but no longer matches, or has been replaced by a non-regular object;
- `staged_deleted` — an expected staged path no longer exists;
- `created` — a regular file not in the expected staged set;
- `created_symlink` — an agent-created symlink;
- `created_other` — another non-regular agent-created object.

The snapshot field:

```text
integrity_scope = veritas_staged_inputs_only
```

is intentional. `integrity_ok=true` means only that the Veritas-staged paper, attachments, and `artifacts.json` copies still match their expected identities at inspection time.

It does **not** mean that:

- the generated outputs are correct;
- the code actually reproduces the paper;
- the agent executed in a secure sandbox;
- network or dependency behavior was controlled;
- a human independently reviewed the run;
- external custody or institutional control exists;
- the result is production-authorized.

Agent-created files remain untrusted reproduction outputs until separately reviewed and, where appropriate, bound into a stronger provenance workflow.

## Symlink and path handling

Directory enumeration uses non-following metadata reads. Symlinks are reported as objects but are never traversed.

The file-preview endpoint also fails closed on path ambiguity:

- absolute paths are rejected;
- `.` and `..` components are rejected;
- empty components and backslash-separated paths are rejected;
- NUL-containing paths are rejected;
- every path component is checked with `lstat` before traversal;
- any symlink component is rejected;
- the final target must be a regular file;
- the resolved final file must remain inside the exact run workspace.

These checks prevent the workspace browser from becoming a generic host-file reader. They do not turn the local workspace itself into an operating-system sandbox; the selected ACP runtime remains responsible for execution isolation.

## Resource bounds

Inspection is intentionally bounded even when an agent produces hostile or accidental output volume.

Current limits are:

| Operation | Bound |
| --- | ---: |
| Workspace entries scanned | 1,000 |
| Staged regular file hashed | 96 MiB per file |
| Agent-created regular file hashed | 8 MiB per file |
| Total agent-created bytes hashed per snapshot | 64 MiB |
| UTF-8 file preview | first 256 KiB |

A workspace exceeding the entry limit fails the snapshot request rather than recursively walking an unbounded tree.

Generated files larger than the created-file hashing bounds may still be listed, but their `hash_computed` field is false. Veritas does not pretend that a hash was computed when it was intentionally omitted.

Binary or non-UTF-8 files are listed but are not returned as text previews. A preview response states that the file is not previewable instead of decoding arbitrary bytes into the UI.

## API

Inspect one persisted run workspace:

```text
GET /api/v1/audits/{audit_id}/replication-runs/{run_id}/workspace
```

The response includes:

- `audit_id` and `run_id`;
- `workspace_is_security_boundary=false`;
- `integrity_scope=veritas_staged_inputs_only`;
- `integrity_ok`;
- bounded summary counts;
- per-entry path, type, status, size, optional SHA-256, and staged role;
- a note that generated outputs remain untrusted.

Preview one regular file from that exact workspace:

```text
GET /api/v1/audits/{audit_id}/replication-runs/{run_id}/workspace/file?path=outputs/result.txt
```

The response is metadata plus either a bounded UTF-8 `content` value or a non-previewable reason such as `binary_content` or `non_utf8_content`.

All `/api/` responses use `Cache-Control: no-store` through the Harness middleware.

## UI behavior

The Reproduction surface keeps three concepts visually separate:

1. **Live replication trace** — ACP/session/tool/permission activity persisted to the audit run history;
2. **Run workspace** — post-run file inventory and staged-input integrity state;
3. **Read-only preview** — bounded text viewing for one regular file.

After a streamed run finishes or fails and a run id has been persisted, the web client loads the exact run-scoped workspace snapshot. It does not ask the browser for a local path and it does not expose a download-anything endpoint.

The UI highlights staged modification/deletion as review-required state. Generated files are shown as created outputs rather than as evidence-backed findings.

## Relationship to the ACP backend

ACP is the client/agent protocol boundary. The workspace inspector is a Veritas observability layer above that boundary.

A backend such as Codex may provide its own sandbox, approval, terminal, file-change, plan, or subagent semantics. Veritas can render those structured events while still independently checking the run directory it staged.

The two responsibilities are intentionally separate:

```text
ACP backend                 Veritas Harness
-----------                 ---------------
execute agent         ->    persist correlated run events
sandbox/permissions   ->    keep browser command-free
write run outputs     ->    inspect exact run workspace
                         ->  verify staged-copy integrity
                         ->  expose bounded read-only previews
```

This separation lets Veritas reuse strong coding-agent runtimes without making the research-audit agent itself a general shell-capable agent.
