# Replication Workspace

The Replication Workspace is the code-capable surface of Veritas. It is deliberately separate from the deterministic Research Audit Agent.

```text
Research Audit Agent  -> paper/evidence tools -> read + verify
Replication Workspace -> ACP coding agent    -> execute + inspect + review
```

Product clients submit a natural-language reproduction goal. They never supply an executable command or an agent process command. The server operator chooses the ACP backend.

## Recommended Codex setup

Install Veritas with the optional ACP client dependency and configure an ACP agent server:

```bash
python -m pip install -e ".[web,pdf,replication]"
export VERITAS_REPLICATION_AGENT="npx -y @agentclientprotocol/codex-acp"
export VERITAS_REPLICATION_AGENT_NAME="Codex"
export VERITAS_REPLICATION_PERMISSION_POLICY="interactive"
```

Forward credentials only when the selected backend actually needs them:

```bash
export VERITAS_REPLICATION_FORWARD_ENV="OPENAI_API_KEY"
```

Veritas does not forward arbitrary parent-process environment variables.

## Permission modes

`VERITAS_REPLICATION_PERMISSION_POLICY` supports:

- `deny` — default. Every ACP permission request is rejected.
- `allow_once` — automatically selects only an explicit `allow_once` option offered by the agent. It never selects `allow_always`.
- `interactive` — an explicitly activated product run may pause for a human decision. A connected UI can reject or select only an `allow_once` option that the agent actually offered. Without an explicitly activated control plane this mode fails closed.

Interactive approval is a run-time control, not evidence of reviewer independence or external authority.

## Workspace model

Every replication run receives a new directory containing staged copies of:

- `paper.pdf`;
- immutable reproduction attachments under `attachments/`;
- `artifacts.json`, which records the source hashes and paths.

The source PDF and attachments in the Harness store remain authoritative. A coding agent may change its staged copies, but those changes do not mutate the stored source artifacts.

The workspace `cwd` is **not** a security boundary. Filesystem, process and network isolation remain the responsibility of the configured coding-agent runtime (for example, the Codex sandbox or an external container/workspace implementation).

## Bounded server-side workspace inspector

The UI does not trust an agent to report its own file changes. Veritas reuses the bounded run inspector documented in [`REPLICATION_WORKSPACE_INSPECTION.md`](REPLICATION_WORKSPACE_INSPECTION.md).

The lower-level inspector:

- binds the request to the audit that actually owns the replication `run_id`;
- never follows symlinks;
- rejects traversal and non-normalized paths;
- caps a scan at 1,000 entries;
- hashes Veritas-staged files only up to the documented staged-file bound;
- hashes created files only within per-file and aggregate created-output budgets;
- caps UTF-8 preview reads at 256 KiB;
- records when a hash was intentionally omitted because an inspection bound was reached.

Its integrity result is intentionally narrow: it covers only the Veritas-staged paper, attachments and `artifacts.json`. Generated files remain untrusted reproduction outputs until separately reviewed.

The product adapter projects those bounded results into `original`, `created`, `modified`, `deleted`, `unsafe_link`, and `unsafe_other` states for the UI. A changed staged input is surfaced as staged-input drift; this means only that the run copy changed, not that the immutable source artifact changed.

## Product API

Streaming execution remains:

```text
POST /api/v1/audits/{audit_id}/replication
```

The response is NDJSON and persists the correlated run events to the audit history.

Active-run controls:

```text
GET  /api/v1/replication/runs/{run_id}/control
POST /api/v1/replication/runs/{run_id}/permissions/{request_id}
POST /api/v1/replication/runs/{run_id}/cancel
```

Permission decisions accept only `reject` or `allow_once`. `allow_once` can select only an option the ACP agent actually offered with kind `allow_once`.

The stable bounded inspector API remains audit-scoped:

```text
GET /api/v1/audits/{audit_id}/replication-runs/{run_id}/workspace
GET /api/v1/audits/{audit_id}/replication-runs/{run_id}/workspace/file?path=<relative-path>
```

The Product Workbench additionally exposes run-centric projections for its inspector panes:

```text
GET /api/v1/runs/{run_id}/workspace
GET /api/v1/runs/{run_id}/workspace/file?path=<relative-path>
```

Persisted run history remains available through:

```text
GET /api/v1/runs
GET /api/v1/runs/{run_id}
```

## Web UI

The web Reproduction surface is a three-pane Replication Workspace:

1. **Project rail** — paper selection, immutable attachments and prior replication runs.
2. **Agent conversation** — streamed agent messages, reasoning, plans, tool/terminal events, permission cards and run lifecycle state.
3. **Workspace inspector** — Changes, Files and Run tabs backed by bounded server-side filesystem inspection.

The workspace can reopen prior runs from persisted Harness events and the retained run-specific workspace directory. Historical pending-permission events are evidence of what happened in the run; only a currently active streamed run can resolve a live permission request.

## Mobile UI

The Expo client uses the same product contract rather than a separate execution path. Its narrower screen stacks the same three logical surfaces vertically:

1. **Project** — paper selection and immutable reproduction artifacts.
2. **Agent conversation** — incremental NDJSON consumption, live ACP events, human permission cards, and cancel control.
3. **Workspace inspector** — Changes, Files and Run tabs using the same server-side snapshot, safe preview, and unified-diff endpoints as the web client.

For `interactive` permission policy, the mobile runtime must expose streaming fetch support so a permission event can be rendered while the server-side ACP request is paused. The client fails closed instead of falling back to a whole-response read when interactive streaming is unavailable. `deny` and `allow_once` runs can still use the non-streaming fallback.

## Cancellation

An active product run can request cancellation through the run control API. Veritas resolves any pending permission fail-closed, cancels the active ACP prompt and tears down the child-agent process context. Persisted product views normalize this terminal condition as `cancelled`; it is not reported as successful reproduction.

## Non-goals

This feature does not establish external custody, reviewer independence, untouched TEST history, institutional key ownership or production authorization. Those remain external evidence questions governed by the v0.15 evidence workflow.
