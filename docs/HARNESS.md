# Veritas Research Audit Harness

The Research Audit Harness is the product interface for Veritas. It keeps the paper, deterministic checks, evidence, findings, reproduction artifacts, benchmark execution provenance, and inspectable run traces in one local-first workspace.

## Run locally

```bash
python -m pip install -e ".[web,pdf]"
veritas-harness
```

Open `http://127.0.0.1:8765`.

Audit data is stored under `~/.veritas/harness` by default. Set `VERITAS_HARNESS_DATA` or pass `--data-dir` to use another local workspace.

Operator metadata is available without creating an audit:

```bash
veritas-harness --version
curl http://127.0.0.1:8765/api/v1/health
```

The FastAPI application version, `/api/v1/health`, `/api/v1/capabilities`, and the public Veritas CLIs resolve the installed `veritas-audit` package version from the same package metadata. Source-only checkouts that have not been installed report `0+unknown` rather than maintaining another hard-coded release number.

## Product surfaces

The UI is not chat-first. It follows an evidence-native product model:

- **Overview** — real workspace KPIs, verification coverage, activity, attention queue, and recent audits.
- **Audits** — persistent paper workspaces and run state.
- **Findings** — contradiction objects linked to a paper and its source.
- **Evidence** — source-linked result inventory.
- **Agent runs** — structured detector/reproduction traces, timing, parser metadata, evidence linkage, and failure state.
- **Reproduction** — immutable code/data/environment artifact intake plus a server-selected ACP agent running in a per-run workspace.
- **Benchmarks** — the repository's actual release-gate/probe inventory plus explicitly recorded execution provenance; no fabricated benchmark scores or trend lines.
- **Audit workbench** — paper structure, PDF evidence viewer, detector result, findings, and trace in one three-column workspace.
- **Audit Agent sidecar** — deterministic command surface that can stay compact until collaboration is needed.
- **`⌘K` command palette** — jump to product surfaces, papers, and matching audit events.

The browser does not execute Veritas algorithms, benchmark commands, or uploaded research artifacts directly. It talks to the Python harness API, and the harness calls the existing extraction, detector, and optional reproduction layers.

```text
Web / PWA / Expo mobile
  │
  ├── bounded upload / query / NDJSON streams
  ▼
Versioned Harness API (/api/v1)
  │
  ├── audit + event store
  ├── benchmark result provenance store
  ├── derived product views
  ├── immutable paper / reproduction artifacts
  ├── paper tools
  │     ├── independent PDF parsing
  │     ├── regression table extraction
  │     └── source localization
  ├── AuditEngine
  │     └── deterministic detector results
  └── optional ACP reproduction adapter
        └── per-run workspace + structured trace
```

## Commands

`/inspect` shows the detected paper structure.

A regression row can be audited directly:

```text
/audit row="Treatment" table=2 page=1
```

`table` and `page` are optional when the row label is unique enough to resolve safely.

The response stream is NDJSON. Every event has an `event_id`, `audit_id`, `kind`, status, timestamp, and optional structured payload. Detector and reproduction executions share a stable `run_id`, so the UI can reopen one correlated start/update/finish-or-error trace instead of reconstructing execution from prose.

### Benchmark execution provenance

Benchmark commands remain repository/CI responsibilities. The Harness does not add a second command executor. After a known benchmark has actually completed, an operator or CI integration can persist that execution fact:

```bash
veritas-benchmark-result record \
  --benchmark-id pdf-regression \
  --exit-code 0 \
  --commit-sha 0123456789abcdef \
  --duration-ms 4210
```

Inspect persisted records with:

```bash
veritas-benchmark-result list --limit 20
veritas-benchmark-result --version
```

Each result gets a generated id and snapshots the known suite metadata together with pass/fail status, exit code, optional Git commit, duration, and timestamp. Result objects are written as unique append-only files under `<harness-data>/benchmark-results/<benchmark-id>/` and include a canonical payload SHA-256 that is checked on read. This is an integrity/self-consistency check, not a signature or remote attestation mechanism.

Only benchmark ids in the repository catalog can be recorded. There is no Web POST endpoint for results, and the product still reports `scores_available=false`: execution provenance is not a benchmark score. Comparison/trend views must wait for an explicit versioned score schema rather than deriving scores from exit codes or CI badges.

## Agent and reproduction boundary

The default Veritas agent is a **research audit agent**, not a general coding agent. Its tool surface is centered on papers and evidence: parse, locate, audit, reproduce, and verify provenance.

Code execution belongs in a separate **Replication workspace**. Veritas provides an optional ACP client adapter for that layer; see [`REPLICATION_AGENT_BACKENDS.md`](REPLICATION_AGENT_BACKENDS.md).

```text
Audit workbench       → evidence tools → read / verify
Replication workspace → ACP agent      → execute / inspect trace
```

The browser or mobile client supplies only a reproduction **goal**. It never supplies the executable ACP command. The server operator selects the agent and permission policy.

### Immutable reproduction artifacts

A paper can have append-only reproduction attachments such as source code, data, environment files, or archives. The product clients can upload and inspect these artifacts even when no ACP agent is configured.

For every attachment Veritas stores:

- a generated `attachment_id`;
- a sanitized basename rather than a client path;
- SHA-256;
- byte size and media type;
- creation time;
- the original bytes under the audit directory.

The web process does **not** unpack, import, or execute uploaded artifacts. Paper and attachment reads re-check the stored SHA-256. Integrity failures fail closed.

Before a reproduction run, Veritas preflights the immutable paper and every attachment. Only after that succeeds may the harness create a new `replication-workspaces/<run_id>` directory. The workspace receives read-only copies of `paper.pdf`, the hash-verified attachments, and an `artifacts.json` provenance manifest. `audit.json` is not staged.

If preflight fails—for example because a local file was modified outside Veritas—the ACP runner is not started, no reproduction workspace is created, and Veritas persists a correlated `start → error` run with `stage=workspace_prepare`. The raw reproduction prompt is not persisted; the start event stores only its SHA-256 and character count.

The local workspace is **not** presented as a security sandbox. The configured ACP agent/runtime remains responsible for process, filesystem, network, and dependency isolation.

## API

Legacy routes remain supported:

- `GET /api/health`
- `GET /api/audits`
- `POST /api/audits`
- `GET /api/audits/{audit_id}`
- `GET /api/audits/{audit_id}/paper`
- `POST /api/audits/{audit_id}/messages`

Versioned product routes:

- `GET /api/v1/health`
- `GET /api/v1/capabilities`
- `GET /api/v1/overview`
- `GET /api/v1/findings`
- `GET /api/v1/benchmarks`
- `GET /api/v1/benchmarks/results`
- `GET /api/v1/runs`
- `GET /api/v1/runs/{run_id}`
- `GET /api/v1/search?q=...`
- `GET /api/v1/audits`
- `POST /api/v1/audits`
- `GET /api/v1/audits/{audit_id}`
- `GET /api/v1/audits/{audit_id}/paper`
- `GET /api/v1/audits/{audit_id}/attachments`
- `POST /api/v1/audits/{audit_id}/attachments`
- `GET /api/v1/audits/{audit_id}/attachments/{attachment_id}`
- `POST /api/v1/audits/{audit_id}/messages`
- `POST /api/v1/audits/{audit_id}/replication`

`GET /api/v1/health` returns the stable service name, API contract version, and installed package version. The legacy `/api/health` endpoint returns the same payload for compatibility.

Paper and attachment uploads are limited to 80 MiB per file. The API consumes upload streams in bounded chunks and rejects an over-limit payload before handing it to the audit/artifact store.

Interactive regression audits run in `interactive_research` scope and report the exact source location, parser candidates, consensus values, detector checks, and findings returned by Veritas.

`GET /api/v1/benchmarks` describes the benchmark/probe commands wired to repository CI and attaches each suite's latest explicitly recorded execution when one exists. It also reports the exact persisted result count and still keeps `scores_available=false`.

`GET /api/v1/benchmarks/results` is a read-only history endpoint with optional `benchmark_id` and bounded `limit` filters. Benchmark result API responses inherit the Harness-wide `Cache-Control: no-store` policy. If a persisted result fails its payload-integrity check, the benchmark API fails closed with HTTP 409 instead of silently dropping the record.

## PWA and mobile

The web client ships an installable manifest and an offline **application shell**. Audit API responses, PDFs, attachments, benchmark provenance, and other `/api/` data are never cached by the service worker.

The native client lives in `mobile/` and shares `/api/v1`. It includes PDF upload, reproduction artifact intake, ACP execution controls, persisted run history, and correlated run detail without embedding the web product in a WebView.

For a physical phone, point the app at an address reachable from the device:

```bash
cd mobile
npm install
EXPO_PUBLIC_VERITAS_API_URL=http://192.168.1.20:8765 npm start
```

For browser-origin clients hosted on another origin, CORS is opt-in:

```bash
VERITAS_CORS_ORIGINS=http://localhost:8081,http://127.0.0.1:8081 veritas-harness
```

See [`PRODUCT_WORKBENCH.md`](PRODUCT_WORKBENCH.md) for the design rationale, research references, parser/observability policy, and future integration points.
