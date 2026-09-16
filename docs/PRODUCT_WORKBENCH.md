# Veritas Product Workbench

This document records the product-layer architecture introduced in the research audit workbench. It is intentionally additive: Veritas' deterministic detectors, independent-parser evidence model, audit identities, reproduction tooling, and locked evaluation remain the source of truth.

## Product principles

1. **Evidence is the primary object.** Chat is a command surface, not the product data model. A result should resolve back to artifact → page → table → row/source.
2. **The Agent is a sidecar.** The default product is a dashboard, tables, evidence viewer, findings, and traces. Agent collaboration can expand into a workbench but should not consume the entire UI.
3. **Runs are inspectable.** Tool execution is represented as structured events with identity, status, evidence, timing, parser metadata, and result coverage.
4. **No synthetic metrics.** Dashboard KPIs are derived from stored audit records only. Empty states stay empty rather than showing demo scores.
5. **Local-first remains the default.** The product layer does not add mandatory hosted storage or telemetry.
6. **Web and mobile share one versioned contract.** `/api/v1` is the compatibility boundary; legacy `/api/*` routes remain available.
7. **Optional capabilities cannot silently weaken evidence policy.** Third-party parsing, reproduction agents, and hosted observability are explicit opt-ins with fail-closed defaults.

These choices mirror the supplied GrowthEvo design package: information-dense cockpit pages, compact/sidecar/workbench Agent modes, a global command palette, evidence-native objects, and a Harness trace rather than an opaque chat transcript.

## What was added

### Web / PWA

- Research audit cockpit with real workspace KPIs.
- Audits, findings, evidence, runs, reproduction, benchmark, and settings surfaces.
- Three-column audit workbench with paper structure, PDF evidence viewer, latest detector result, findings, and trace.
- Collapsible Audit Agent sidecar and `⌘K` command palette.
- Live Reproduction control surface that streams structured ACP events when a server-side agent is configured.
- Correlated Agent Runs inspector that resolves a `run_id` into start/update/finish events, timing, evidence, parser metadata, and failure state.
- Live Settings capability surface for parser policy, ACP execution boundaries, API contract, and OTLP export state without exposing collector URLs or secrets.
- Mobile responsive layout, bottom navigation, installable web app manifest, and offline shell cache. API/PDF responses are deliberately excluded from the service-worker cache.

### Backend API

The product API adds versioned views while preserving the existing local Harness contract:

```text
GET  /api/v1/capabilities
GET  /api/v1/overview
GET  /api/v1/findings
GET  /api/v1/runs
GET  /api/v1/runs/{run_id}
GET  /api/v1/search?q=...
GET  /api/v1/audits
GET  /api/v1/audits/{id}
GET  /api/v1/audits/{id}/paper
POST /api/v1/audits
POST /api/v1/audits/{id}/messages
POST /api/v1/audits/{id}/replication
```

The old `/api/audits*` contract is preserved. Mobile/browser cross-origin access can be enabled explicitly with `VERITAS_CORS_ORIGINS`.

### Trace contract

Detector and replication executions use a shared run envelope. Completed or failed runs exposed by `/api/v1/runs` include:

- stable `run_id` shared by the start/update/finish events;
- `run_kind` (`detector` or `replication`);
- `phase` (`start`, `update`, `finish`, or `error` where applicable);
- wall-clock `duration_ms` on terminal tool events;
- immutable paper `artifact_id`;
- parser snapshot metadata for deterministic detector runs;
- evidence linkage and verification coverage when the underlying tool produces evidence;
- a persisted error type for failed tool runs.

`GET /api/v1/runs/{run_id}` projects the persisted audit event history into one correlated run detail object so clients do not need to reconstruct trace boundaries independently.

The start trace stores only a hash and length of a reproduction prompt, not the raw prompt. Structured ACP updates are still persisted because they are the inspectable execution trace.

### Parser stack and optional Docling adapter

The product parser stack keeps the locked native baseline as the authority:

```text
pymupdf_native      family=mupdf_native
pdfplumber_native   family=pdfminer_native
```

An optional Docling adapter can be enabled with:

```text
VERITAS_PDF_THIRD_PARSER=docling
pip install -e '.[docling]'
```

The adapter emits the same immutable `NativePDFSnapshot` shape with parser identity, artifact hash, page provenance, words, and tables. Before a third snapshot is accepted, Veritas checks that it belongs to the same source artifact and uses a parser family independent from the baseline families.

This opt-in does **not** change the existing two-family consensus/promotion requirement. The third snapshot is observational unless a future locked evaluation explicitly changes promotion policy. Unknown `VERITAS_PDF_THIRD_PARSER` values fail closed rather than silently selecting another parser.

### ACP reproduction boundary

Veritas reuses the repository's existing Agent Client Protocol replication adapter instead of introducing a second execution engine. The browser or mobile client supplies only a reproduction **goal**. It cannot supply an executable command.

Server-side configuration:

```text
VERITAS_REPLICATION_AGENT="<server-selected ACP command>"
VERITAS_REPLICATION_AGENT_NAME="Optional display name"
VERITAS_REPLICATION_FORWARD_ENV="OPTIONAL,EXPLICIT,VARIABLES"
VERITAS_REPLICATION_PERMISSION_POLICY="deny|allow_once"
```

Security behavior is fail-closed:

- no `VERITAS_REPLICATION_AGENT` → the replication endpoint returns HTTP 503;
- permission policy defaults to `deny`;
- an invalid permission-policy value also falls back to `deny` and is exposed as invalid in capabilities;
- `allow_once` can only select an explicit `allow_once` option offered by the ACP agent;
- the audit metadata file is not exposed to the replication workspace; only a copy of the immutable paper is staged there;
- the local workspace is **not** claimed to be a security sandbox. The selected ACP agent/runtime remains responsible for its execution isolation.

The Reproduction UI reads `/api/v1/capabilities`, shows this boundary explicitly, and streams NDJSON events into a live trace. The same terminal events appear in `/api/v1/runs` and can be reopened through the correlated run endpoint.

### Optional OTLP observability

Local event storage remains authoritative. Optional OpenTelemetry export can be enabled with:

```text
pip install -e '.[observability]'
VERITAS_OTEL_EXPORT=true
OTEL_EXPORTER_OTLP_ENDPOINT=http://collector:4318
```

A terminal detector or reproduction event is exported only **after** the local event append is durable. Export errors are best-effort and cannot change a detector verdict or local run state.

The OTLP span payload is intentionally metadata-only. It may include run/audit/tool identity, duration, artifact identity, parser ids, evidence page/table locator, verification coverage, check counts, and error type. It does not export the PDF, raw reproduction prompt, evidence quote/text, arbitrary ACP message payload, or collector endpoint through the product API.

`/api/v1/capabilities` exposes whether export is enabled, whether the optional dependencies and endpoint are configured, and the metadata-only privacy contract. The live Settings surface renders those facts without revealing secrets.

### Native mobile

`mobile/` is an Expo SDK 57 / React Native 0.86 client with:

- audit cockpit;
- paper list;
- evidence-linked findings;
- native PDF document picker + upload;
- audit detail and event trace;
- deterministic Harness command composer;
- ACP reproduction workspace with the same server-side fail-closed capability boundary;
- persisted detector/reproduction run history backed by `/api/v1/runs`;
- correlated native run detail backed by `/api/v1/runs/{run_id}`.

The native client shares `/api/v1` with the web client rather than embedding the web product in a WebView. React Native currently parses the replication NDJSON response at request completion for compatibility across native fetch implementations, while the web surface renders streamed events incrementally.

## Reference implementations and research considered

The implementation borrows **architecture and interaction patterns, not copied source code**, from mature open projects:

- **Langfuse** — structured traces as a first-class product object and an observability UI for agent/tool activity. <https://github.com/langfuse/langfuse>
- **OpenHands / Agent Canvas** — a control surface separated from the runtime, plus a sandbox boundary for code execution. <https://github.com/OpenHands/OpenHands>
- **OpenAI Agents SDK** — trace/span semantics around agent turns, tool calls, guardrails, and handoffs. <https://github.com/openai/openai-agents-python>
- **Docling** — richer document layout/table parsing behind an optional independent adapter; Veritas does not silently replace its baseline parser strategy. <https://github.com/docling-project/docling>
- **shadcn/ui** and **TanStack Query** — design-system and async-state patterns considered for a future bundled React client. The current web client remains dependency-light to preserve the repository's single-command Python install. <https://github.com/shadcn-ui/ui> <https://github.com/TanStack/query>
- **Expo SDK 57** — current stable mobile baseline in mid-2026, using React Native 0.86. <https://expo.dev/changelog/sdk-57>

Recent research reinforced the evidence-first and trace-first choices:

- **SciVer (ACL 2025)** introduces a 3,000-example, expert-annotated multimodal scientific claim-verification benchmark over 1,113 papers and reports a substantial gap between current foundation models and human experts. That supports keeping page/table/source evidence visible and inspectable instead of hiding it behind generated prose. <https://aclanthology.org/2025.acl-long.420/>
- **FIRE (NAACL 2025 Findings)** couples iterative evidence retrieval with verification and explicitly decides whether evidence is sufficient or another retrieval step is needed. Veritas follows the same high-level principle—evidence acquisition and verdict production remain separable, observable steps—even though its current statistical checks are deterministic rather than LLM fact-checking. <https://aclanthology.org/2025.findings-naacl.158/>
- **CLAIM-BENCH (2025)** evaluates scientific claim→evidence extraction/validation and reports meaningful limitations in current LLMs on complex full-paper evidence linkage. This supports keeping deterministic verification and explicit source objects beneath any LLM interface. <https://aclanthology.org/2025.ijcnlp-long.127/>
- **Automated reproducibility assessments in the social and behavioral sciences using LLMs (2026)** demonstrates that automated reproducibility assessment is viable but not perfect, motivating explicit uncertainty, coverage, and inspectable outcomes rather than a single opaque verdict. <https://arxiv.org/abs/2606.13670>
- **DeployBench (2026)** finds research-artifact deployment is still a major bottleneck and highlights weak completion judgments; this supports an isolated reproduction runtime plus paper-specific evidence checks instead of declaring success from process completion alone. <https://arxiv.org/abs/2606.05238>
- **AgentActionBench / NLPCC 2026 Shared Task 11** evaluates the *process* of experiment reproduction using captured action traces and paper-specific rubrics, aligning closely with Veritas' Harness run/trace surface. <https://arxiv.org/abs/2609.11117>
- **LLM-Based Scientific Peer Review: Methods, Benchmarks, and Reliability Challenges (2026)** emphasizes reliability, robustness, retrieval vulnerabilities, and transparency concerns in automated review; Veritas therefore keeps AI assistance downstream of evidence and deterministic checks. <https://arxiv.org/abs/2606.25057>

## Why no full React migration in this change

The repository already ships a zero-build FastAPI/static Harness. Replacing it with a Node build would increase installation and deployment complexity without improving the underlying audit engine. This change therefore implements the product layer as a high-quality dependency-free web client and a separate Expo mobile client. The `/api/v1` boundary makes a future React/shadcn/TanStack client possible without another backend migration.

## Validation gates

The branch keeps the repository's existing release gates and adds product/client checks:

- `ruff check src tests`;
- full `pytest` suite, including product API, parser-stack, metadata-only telemetry, run-detail, and streamed fake-ACP lifecycle coverage;
- PDF regression benchmark;
- PDF geometry holdout;
- adversarial extraction fail-closed benchmark;
- existing real-PDF non-gating probes;
- Expo dependency compatibility check;
- mobile TypeScript `tsc --noEmit`;
- Node syntax checks for the dependency-free web modules.

## Next integration points

- Evaluate the optional Docling snapshot on locked extraction fixtures and real-PDF holdouts before considering any promotion-policy change.
- Add repository/code/data artifact intake to the reproduction workspace through existing provenance and security primitives rather than expanding the browser's authority.
- Add benchmark result persistence and comparison views only when benchmark executions have durable, versioned output objects; never fabricate benchmark scores in the product UI.
- Add a Langfuse-specific adapter only if needed; OTLP remains the vendor-neutral optional observability boundary.
- Add native incremental NDJSON consumption when React Native's supported fetch/runtime surface provides a stable streaming reader across target platforms.
