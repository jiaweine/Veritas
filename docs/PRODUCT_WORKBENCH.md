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
- Mobile responsive layout, bottom navigation, installable web app manifest, and offline shell cache. API/PDF responses are deliberately excluded from the service-worker cache.

### Backend API

New derived, read-oriented endpoints:

```text
GET /api/v1/capabilities
GET /api/v1/overview
GET /api/v1/findings
GET /api/v1/runs
GET /api/v1/search?q=...
GET /api/v1/audits
GET /api/v1/audits/{id}
GET /api/v1/audits/{id}/paper
POST /api/v1/audits
POST /api/v1/audits/{id}/messages
```

The old `/api/audits*` contract is preserved. Mobile/browser cross-origin access can be enabled explicitly with `VERITAS_CORS_ORIGINS`.

### Native mobile

`mobile/` is an Expo SDK 57 / React Native 0.86 client with:

- audit cockpit;
- paper list;
- evidence-linked findings;
- native PDF document picker + upload;
- audit detail and run trace;
- deterministic Harness command composer.

## Reference implementations and research considered

The implementation borrows **architecture and interaction patterns, not copied source code**, from mature open projects:

- **Langfuse** — structured traces as a first-class product object and an observability UI for agent/tool activity. <https://github.com/langfuse/langfuse>
- **OpenHands / Agent Canvas** — a control surface separated from the runtime, plus a sandbox boundary for code execution. <https://github.com/OpenHands/OpenHands>
- **OpenAI Agents SDK** — trace/span semantics around agent turns, tool calls, guardrails, and handoffs. <https://github.com/openai/openai-agents-python>
- **Docling** — a high-quality optional future adapter for richer document parsing; Veritas keeps its independent parser strategy rather than silently replacing it. <https://github.com/docling-project/docling>
- **shadcn/ui** and **TanStack Query** — design-system and async-state patterns considered for a future bundled React client. The current web client remains dependency-light to preserve the repository's single-command Python install. <https://github.com/shadcn-ui/ui> <https://github.com/TanStack/query>
- **Expo SDK 57** — current stable mobile baseline in mid-2026, using React Native 0.86. <https://expo.dev/changelog/sdk-57>

Recent research reinforced the evidence-first and trace-first choices:

- **CLAIM-BENCH (2025)** evaluates scientific claim→evidence extraction/validation and reports meaningful limitations in current LLMs on complex full-paper evidence linkage. This supports keeping deterministic verification and explicit source objects beneath any LLM interface. <https://arxiv.org/abs/2506.08235>
- **Automated reproducibility assessments in the social and behavioral sciences using LLMs (2026)** demonstrates that automated reproducibility assessment is viable but not perfect, motivating explicit uncertainty, coverage, and inspectable outcomes rather than a single opaque verdict. <https://arxiv.org/abs/2606.13670>
- **DeployBench (2026)** finds research-artifact deployment is still a major bottleneck and highlights weak completion judgments; this supports an isolated reproduction runtime plus paper-specific evidence checks instead of declaring success from process completion alone. <https://arxiv.org/abs/2606.05238>
- **AgentActionBench / NLPCC 2026 Shared Task 11** evaluates the *process* of experiment reproduction using captured action traces and paper-specific rubrics, aligning closely with Veritas' Harness run/trace surface. <https://arxiv.org/abs/2609.11117>
- **LLM-Based Scientific Peer Review: Methods, Benchmarks, and Reliability Challenges (2026)** emphasizes reliability, robustness, retrieval vulnerabilities, and transparency concerns in automated review; Veritas therefore keeps AI assistance downstream of evidence and deterministic checks. <https://arxiv.org/abs/2606.25057>

## Why no full React migration in this change

The repository already ships a zero-build FastAPI/static Harness. Replacing it with a Node build would increase installation and deployment complexity without improving the underlying audit engine. This change therefore implements the product layer as a high-quality dependency-free web client and a separate Expo mobile client. The `/api/v1` boundary makes a future React/shadcn/TanStack client possible without another backend migration.

## Next integration points

- Add an optional Docling/MinerU parser adapter behind the existing independent parser interfaces and evaluate it against locked parser fixtures before enabling it by default.
- Emit richer span records (latency, detector version, parser version, policy result) from the Harness, then optionally export them via OpenTelemetry/Langfuse adapters.
- Run reproduction jobs in an isolated runtime (OpenHands-compatible or repository replication bridge) and stream structured execution traces back into `/api/v1/runs`.
- Add benchmark comparison views only after benchmark runs are available; never fabricate benchmark scores in the product UI.
