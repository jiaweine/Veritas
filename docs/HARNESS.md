# Veritas Research Audit Harness

The Research Audit Harness is the product interface for Veritas. It keeps the paper, deterministic checks, evidence, findings, and inspectable run traces in one local-first workspace.

## Run locally

```bash
python -m pip install -e ".[web,pdf]"
veritas-harness
```

Open `http://127.0.0.1:8765`.

Audit data is stored under `~/.veritas/harness` by default. Set `VERITAS_HARNESS_DATA` or pass `--data-dir` to use another local workspace.

## Product surfaces

The UI is no longer chat-first. It follows an evidence-native product model:

- **Overview** — real workspace KPIs, verification coverage, activity, attention queue, and recent audits.
- **Audits** — persistent paper workspaces and run state.
- **Findings** — contradiction objects linked to a paper and its source.
- **Evidence** — source-linked result inventory.
- **Agent runs** — structured tool traces and result coverage.
- **Audit workbench** — paper structure, PDF evidence viewer, detector result, findings, and trace in one three-column workspace.
- **Audit Agent sidecar** — deterministic command surface that can stay compact until collaboration is needed.
- **`⌘K` command palette** — jump to product surfaces, papers, and matching audit events.

The browser does not execute Veritas algorithms directly. It talks to the Python harness API, and the harness calls the existing extraction and detector library.

```text
Web / PWA / Expo mobile
  │
  ├── upload / query / NDJSON message stream
  ▼
Versioned Harness API (/api/v1)
  │
  ├── thread + event store
  ├── derived product views
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

Code execution belongs in a separate **Replication workspace** where source trees can be isolated, commands can require approval, and proposed changes can be reviewed as diffs. Veritas provides an optional ACP client adapter for that layer; see [`REPLICATION_AGENT_BACKENDS.md`](REPLICATION_AGENT_BACKENDS.md).

```text
Audit workbench       → evidence tools → read / verify
Replication workspace → ACP agent      → execute / propose / review
```

The audit browser deliberately does not become an arbitrary code execution surface.

## API

Legacy routes remain supported:

- `GET /api/health`
- `GET /api/audits`
- `POST /api/audits`
- `GET /api/audits/{audit_id}`
- `GET /api/audits/{audit_id}/paper`
- `POST /api/audits/{audit_id}/messages`

Versioned product routes:

- `GET /api/v1/capabilities`
- `GET /api/v1/overview`
- `GET /api/v1/findings`
- `GET /api/v1/runs`
- `GET /api/v1/search?q=...`
- `GET /api/v1/audits`
- `POST /api/v1/audits`
- `GET /api/v1/audits/{audit_id}`
- `GET /api/v1/audits/{audit_id}/paper`
- `POST /api/v1/audits/{audit_id}/messages`

Interactive regression audits run in `interactive_research` scope and report the exact source location, parser candidates, consensus values, detector checks, and findings returned by Veritas.

## PWA and mobile

The web client ships an installable manifest and an offline **application shell**. Audit API responses and PDFs are never cached by the service worker.

The native client lives in `mobile/` and shares `/api/v1`. For a physical phone, point the app at an address reachable from the device:

```bash
cd mobile
npm install
EXPO_PUBLIC_VERITAS_API_URL=http://192.168.1.20:8765 npm start
```

For browser-origin clients hosted on another origin, CORS is opt-in:

```bash
VERITAS_CORS_ORIGINS=http://localhost:8081,http://127.0.0.1:8081 veritas-harness
```

See [`PRODUCT_WORKBENCH.md`](PRODUCT_WORKBENCH.md) for the design rationale, research references, and future integration points.
