# Veritas Research Audit Harness

The Research Audit Harness is the conversational interface for Veritas. It keeps the paper, the agent run, deterministic checks, and source evidence in one workspace.

## Run locally

```bash
python -m pip install -e ".[web,pdf]"
veritas-harness
```

Open `http://127.0.0.1:8765`.

Audit data is stored under `~/.veritas/harness` by default. Set `VERITAS_HARNESS_DATA` or pass `--data-dir` to use another local workspace.

## Workspace model

The UI follows a three-pane research workflow:

- **Audits** — persistent paper threads and run state.
- **Conversation** — user instructions plus structured tool events and findings.
- **Evidence Inspector** — the source PDF, detected tables, findings, and parser provenance.

The browser does not execute Veritas algorithms directly. It talks to the Python harness API, and the harness calls the existing extraction and detector library.

```text
Browser
  │
  ├── upload / message stream
  ▼
Harness API
  │
  ├── thread + event store
  ├── paper tools
  │     ├── dual PDF parsing
  │     ├── regression table extraction
  │     └── source localization
  └── AuditEngine
        └── deterministic detector results
```

## Commands

`/inspect` shows the detected paper structure.

A regression row can be audited directly:

```text
/audit row="Treatment" table=2 page=1
```

`table` and `page` are optional when the row label is unique enough to resolve safely.

The response stream is NDJSON. Every event has an `event_id`, `audit_id`, `kind`, status, timestamp, and optional structured payload. The UI renders tool events directly instead of turning tool execution into prose.

## Agent boundary

The default Veritas agent is a **research audit agent**, not a general coding agent. Its tool surface is centered on papers and evidence: parse, locate, audit, reproduce, and verify provenance.

Code execution belongs in a separate **Replication workspace** where source trees can be isolated, commands can require approval, and proposed changes can be reviewed as diffs. Veritas now provides an optional ACP client adapter for that layer; see [`REPLICATION_AGENT_BACKENDS.md`](REPLICATION_AGENT_BACKENDS.md).

```text
Audit thread       → evidence tools → read / verify
Replication thread → ACP agent      → execute / propose / review
```

The ACP adapter does not make the current paper-audit browser code-capable. Browser replication panels, interactive permission cards, terminal views, and diff review are separate product surfaces built on top of that adapter.

## API

- `GET /api/health`
- `GET /api/audits`
- `POST /api/audits`
- `GET /api/audits/{audit_id}`
- `GET /api/audits/{audit_id}/paper`
- `POST /api/audits/{audit_id}/messages`

Interactive regression audits run in `interactive_research` scope and report the exact source location, parser candidates, consensus values, detector checks, and findings returned by Veritas.
