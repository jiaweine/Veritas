# Veritas Product Workbench

This document records the product-layer architecture introduced in the research audit workbench. It is intentionally additive: Veritas' deterministic detectors, dual-parser evidence model, audit identities, reproduction tooling, and locked evaluation remain the source of truth.

## Product principles

1. **Evidence is the primary object.** Chat is a command surface, not the product data model. A result should resolve back to artifact → page → table → row/source.
2. **The Agent is a sidecar.** The default product is a dashboard, tables, evidence viewer, findings, and traces. Agent collaboration can expand into a workbench but should not consume the entire UI.
3. **Runs are inspectable.** Tool execution is represented as structured events with identity, status, evidence, and result coverage.
4. **No synthetic metrics.** Dashboard KPIs are derived from stored audit records only. Empty states stay empty rather than showing demo scores.
5. **Local-first remains the default.** The product layer does not add mandatory hosted storage or telemetry.
6. **Web and mobile share one versioned contract.** `/api/v1` is the compatibility boundary; legacy `/api/*` routes remain available.

These choices mirror the supplied GrowthEvo design package: information-dense cockpit pages, compact/sidecar/workbench Agent modes, a global command palette, evidence-native objects, and a Harness trace rather than an opaque chat transcript.

## What was added

### Web / PWA

- Research audit cockpit with real workspace KPIs.
- Audits, findings, evidence, runs, reproduction, benchmark, and settings surfaces.
- Three-column audit workbench with paper structure, PDF evidence viewer, latest detector result, findings, and trace.
- Collapsible Audit Agent sidecar and `⌘K` command palette.
- Live Reproduction control surface that streams structured ACP events when a server-side agent is configured.
- Mobile responsive layout, bottom navigation, installable web app manifest, and offline shell cache. API/PDF responses are deliberately excluded from the service-worker cache.

### Backend API

The product API adds versioned views while preserving the existing local Harness contract:

```text
GET  /api/v1/capabilities
GET  /api/v1/overview
GET  /api/v1/findings
GET  /api/v1/runs
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

The start trace stores only a hash and length of a reproduction prompt, not the raw prompt. Structured ACP updates are still persisted because they are the inspectable execution trace.

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

The Reproduction UI reads `/api/v1/capabilities`, shows this boundary explicitly, and streams NDJSON events into a live trace. The same terminal events appear in `/api/v1/runs`.

### Native mobile

`mobile/` is an Expo SDK 57 / React Native 0.86 client with:

- audit cockpit;
- paper list;
- evidence-linked findings;
- native PDF document picker + upload;
- audit detail and run trace;
- deterministic Harness command composer.

The native client shares `/api/v1` with the web client rather than embedding the web product in a WebView.

## Reference implementations and research considered

The implementation borrows **architecture and interaction patterns, not copied source code**, from mature open projects:

- **Langfuse** — structured traces as a first-class product object and an observability UI for agent/tool activity. <https://github.com/langfuse/langfuse>
- **OpenHands / Agent Canvas** — a control surface separated from the runtime, plus a sandbox boundary for code execution. <https://github.com/OpenHands/OpenHands>
- **OpenAI Agents SDK** — trace/span semantics around agent turns, tool calls, guardrails, and handoffs. <https://github.com/openai/openai-agents-python>
- **Docling** — a high-quality optional future adapter for richer document parsing; Veritas keeps its independent parser strategy rather than silently replacing it. <https://github.com/docling-project/docling>
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

The branch keeps the repository's existing release gates and adds client-side checks:

- `ruff check src tests`;
- full `pytest` suite, including product API and streamed fake-ACP lifecycle coverage;
- PDF regression benchmark;
- PDF geometry holdout;
- adversarial extraction fail-closed benchmark;
- Expo dependency compatibility check;
- mobile TypeScript `tsc --noEmit`;
- Node syntax checks for the dependency-free web modules.

## Next integration points

- Add an optional Docling/MinerU parser adapter behind the existing independent parser interfaces and evaluate it against locked parser fixtures before enabling it by default.
- Export the now-correlated run/span records through optional OpenTelemetry/Langfuse adapters without making hosted observability mandatory.
- Add repository/code/data artifact intake to the reproduction workspace through existing provenance and security primitives rather than expanding the browser's authority.
- Add benchmark comparison views only after benchmark runs are available; never fabricate benchmark scores in the product UI.
