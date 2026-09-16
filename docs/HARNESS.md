# Veritas Research Audit Harness

The Research Audit Harness is the product interface for Veritas. It keeps the paper, deterministic checks, evidence, findings, reproduction artifacts, benchmark result envelopes, and inspectable run traces in one local-first workspace.

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

The FastAPI application version, `/api/v1/health`, `/api/v1/capabilities`, and Veritas CLIs resolve the installed `veritas-audit` package version from the same package metadata. Source-only checkouts that have not been installed report `0+unknown` rather than maintaining another hard-coded release number.

## Product surfaces

The UI is not chat-first. It follows an evidence-native product model:

- **Overview** — real workspace KPIs, verification coverage, activity, attention queue, and recent audits.
- **Audits** — persistent paper workspaces and run state.
- **Findings** — contradiction objects linked to a paper and its source.
- **Evidence** — source-linked result inventory.
- **Agent runs** — structured detector/reproduction traces, timing, parser metadata, evidence linkage, and failure state.
- **Reproduction** — immutable code/data/environment artifact intake plus a server-selected ACP agent running in a per-run workspace.
- **Benchmarks** — the repository's actual release-gate/probe inventory plus explicitly ingested, versioned result envelopes; no fabricated global scores or trends.
- **Audit workbench** — paper structure, PDF evidence viewer, detector result, findings, and trace in one three-column workspace.
- **Audit Agent sidecar** — deterministic command surface that can stay compact until collaboration is needed.
- **`⌘K` command palette** — jump to product surfaces, papers, and matching audit events.

The browser does not execute Veritas algorithms or uploaded research artifacts directly. It talks to the Python harness API, and the harness calls the existing extraction, detector, and optional reproduction layers.

```text
Web / PWA / Expo mobile
  │
  ├── bounded upload / query / NDJSON streams
  ▼
Versioned Harness API (/api/v1)
  │
  ├── audit + event store
  ├── append-only benchmark result store
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

## Benchmark result persistence

The CI command catalog and execution results are separate objects. `GET /api/v1/benchmarks` always describes the seven repository benchmark/probe commands wired to CI. Durable results appear only after an operator explicitly ingests a **Benchmark Result Envelope v1**:

```bash
veritas-benchmark-result ./benchmark-result.json
```

The CLI uses `VERITAS_HARNESS_DATA` or `~/.veritas/harness` by default and accepts `--data-dir` for another workspace. Result files are limited to 1 MiB and must be UTF-8 JSON. The v1 envelope is strict: unknown fields, unknown benchmark ids, command drift, timezone-free timestamps, nested metric values, non-finite numbers, and malformed CI commit ids are rejected.

A minimal CI-sourced envelope looks like:

```json
{
  "schema_version": "1",
  "benchmark_id": "pdf-regression",
  "command": "python scripts/benchmark_pdf_regression.py",
  "status": "passed",
  "source": "ci",
  "started_at": "2026-09-16T15:00:00Z",
  "finished_at": "2026-09-16T15:00:02.500Z",
  "commit_sha": "aaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaa",
  "run_url": "https://github.com/example/repo/actions/runs/123",
  "summary": "PDF regression benchmark passed.",
  "metrics": {
    "cases": 4,
    "verification_rate": 1.0
  }
}
```

Accepted statuses are `passed`, `failed`, `error`, and `skipped`; accepted sources are `ci` and `operator`. A `ci` envelope requires a full 40-character Git commit SHA. Metrics are deliberately limited to a flat map of JSON scalar values. This prevents an unversioned arbitrary payload from becoming a de facto second result schema.

The canonicalized envelope is content-addressed as `bmr_<hash>`. Re-ingesting the same semantic envelope is idempotent. The stored record also carries the source-file SHA-256, ingestion time, derived duration, and catalog-derived title/kind/gating metadata. Records are written read-only where supported and revalidated on every read; payload or derived-metadata tampering fails closed instead of being skipped.

Persistence is local-first and does **not** imply that Veritas automatically captures historical GitHub Actions runs. CI or another operator must intentionally emit and ingest envelopes. The UI shows only persisted status/provenance/scalar metrics and never collapses heterogeneous metrics into a synthetic global score or trend.

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
- `GET /api/v1/benchmark-results`
- `GET /api/v1/benchmark-results/{result_id}`
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

`GET /api/v1/benchmarks` describes the benchmark/probe commands wired to the repository CI and includes actual persisted-result availability/latest-result metadata. `GET /api/v1/benchmark-results` returns the validated append-only result history, optionally filtered by `benchmark_id`; neither endpoint synthesizes a score.

## PWA and mobile

The web client ships an installable manifest and an offline **application shell**. Audit API responses, PDFs, attachments, benchmark results, and other `/api/` data are never cached by the service worker.

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
