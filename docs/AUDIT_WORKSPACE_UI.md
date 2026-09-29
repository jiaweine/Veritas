# Audit Workspace UI

The paper audit surface is an evidence-first agent harness, not a generic chat page.

## Product layout

The audit route is organized as three persistent panes:

1. **Project rail** — immutable paper/attachments, detected tables, and run history.
2. **Audit Agent thread** — user requests plus structured tool, finding, and assistant events.
3. **Evidence Inspector** — source PDF, findings, parsed structure, provenance, and persisted run detail.

Selecting a detected table or evidence-linked event moves the Evidence Inspector to the corresponding PDF page. The agent thread remains visible while the evidence changes so that a claim, action, and source can be reviewed together.

On desktop, the two pane boundaries are draggable. The chosen left-rail and Evidence Inspector widths are stored locally as presentation preferences; they do not alter audit data or provenance.

## Interaction persistence

The web client persists only interaction state that is safe to reconstruct locally:

- pane widths;
- the last selected source page / inspector tab for each audit;
- the last inspected persisted run id;
- an unsent Audit Agent composer draft.

Scientific results, findings, run traces, paper metadata, and source locations are never reconstructed from this browser state. They continue to come from the server-backed audit record and `/api/v1/runs/{run_id}`.

The global command palette also gains audit-scoped commands while a paper audit is open. `/inspect` can be executed immediately, while `/audit` is pre-filled from the selected table/page and leaves the row label for the researcher to specify.

## Agent boundary

The Audit Agent is intentionally restricted to the research-audit capability set:

- read
- parse
- inspect
- verify

It does not receive terminal, package-install, network, or arbitrary filesystem-write capability. Those operations belong to the separate **Replication Workspace**, where ACP-backed coding agents run inside an agent-owned sandbox and sensitive operations are mediated by explicit permissions.

This keeps the product split clear:

```text
Research Audit Workspace                 Replication Workspace
paper / tables / claims                  code / data / environment
        |                                        |
read / parse / inspect / verify                 ACP
        |                                        |
structured audit events                 coding-agent events
        |                                        |
Evidence Inspector                terminal / files / changes
        |                                        |
        +--------------- provenance -------------+
```

## Streaming contract

Audit commands continue to use the existing NDJSON message endpoint:

```text
POST /api/v1/audits/{audit_id}/messages
```

The browser projects streamed events directly into the thread. Detector results update the selected evidence page when they contain a source location. The UI does not synthesize scientific results client-side.

## Run inspection

The project rail is an entry point into persisted run history. Selecting a run loads the existing run projection:

```text
GET /api/v1/runs/{run_id}
```

The Evidence Inspector then shows run timing, coverage/counts, artifact/parser metadata, and the correlated event trace. If the run carries a source page, the researcher can jump back to that evidence without leaving the audit thread.

## Source-of-truth rules

- PDFs and uploaded artifacts remain server-owned immutable inputs.
- Findings are rendered from persisted detector output.
- Run history is loaded from `/api/v1/runs` and filtered to the active audit.
- Run detail is loaded from `/api/v1/runs/{run_id}` and is not synthesized in the browser.
- Provenance displays the artifact hash and parser families already recorded by the backend.
- Local storage contains presentation/session preferences only, never detector output.
- The Audit Agent never exposes a shell control.
- Reproduction remains a separate workspace and permission domain.

## Responsive behavior

Desktop uses the full three-pane evidence IDE with draggable separators. At narrower widths the separators disappear, the Evidence Inspector drops below the project rail and thread, and on mobile each pane becomes a full-width stacked surface while preserving the same data and permission boundaries.
