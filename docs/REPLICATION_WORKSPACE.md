# Replication Workspace

The Replication Workspace is the code-capable surface of Veritas. It is deliberately separate from the deterministic Research Audit Agent.

```text
Research Audit Agent  -> paper/evidence tools -> read + verify
Replication Workspace -> ACP coding agent    -> execute + inspect + review
```

The browser submits a natural-language reproduction goal. It never supplies an executable command or an agent process command. The server operator chooses the ACP backend.

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
- `interactive` — Web Harness runs may pause for a human decision. The UI can reject or select only an `allow_once` option that the agent actually offered. Without an explicitly activated Web Harness control plane this mode fails closed.

Interactive approval is a run-time control, not evidence of reviewer independence or external authority.

## Workspace model

Every replication run receives a new directory containing staged copies of:

- `paper.pdf`;
- immutable reproduction attachments under `attachments/`;
- `artifacts.json`, which records the source hashes and paths.

The source PDF and attachments in the Harness store remain authoritative. A coding agent may change its staged copies, but those changes do not mutate the stored source artifacts.

The workspace `cwd` is **not** a security boundary. Filesystem, process and network isolation remain the responsibility of the configured coding-agent runtime (for example, the Codex sandbox or an external container/workspace implementation).

## Server-side workspace inspector

The UI does not trust an agent to report its own file changes. Veritas independently scans the run directory and computes SHA-256 identities for regular files. The inspector classifies paths as:

- `original`;
- `created`;
- `modified`;
- `deleted`;
- `unsafe_link`.

Text previews and unified diffs are capped at 512 KiB. Inspector file reads reject absolute paths, `..`, symlinks and paths that resolve outside the run directory. Symlink targets are never followed.

A changed staged paper, attachment or `artifacts.json` is surfaced as `staged_input_drift`. This means only that the run copy changed; it does not imply the immutable source artifact changed.

## Product API

Existing streaming execution remains:

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

Permission decisions accept only `reject` or `allow_once`. `allow_once` can select only an offered option with ACP kind `allow_once`.

Workspace inspection:

```text
GET /api/v1/runs/{run_id}/workspace
GET /api/v1/runs/{run_id}/workspace/file?path=<relative-path>
```

Persisted run history remains available through:

```text
GET /api/v1/runs
GET /api/v1/runs/{run_id}
```

## UI

The web Reproduction surface is a three-pane Replication Workspace:

1. **Project rail** — paper selection, immutable attachments and prior replication runs.
2. **Agent conversation** — streamed messages, reasoning, plans, tool/terminal events, permission cards and run lifecycle state.
3. **Workspace inspector** — Changes, Files and Run tabs backed by server-side filesystem inspection.

The workspace can reopen prior runs from persisted Harness events and the retained run-specific workspace directory.

## Non-goals

This feature does not establish external custody, reviewer independence, untouched TEST history, institutional key ownership or production authorization. Those remain external evidence questions governed by the v0.15 evidence workflow.
