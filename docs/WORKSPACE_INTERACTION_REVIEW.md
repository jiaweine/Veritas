# Workspace interaction review and design contract

This document reviews **non-Code-Agent** product interactions in Web/PWA
and Expo. It distinguishes implemented behavior from future design work. The
API is authoritative for persisted evidence; transient client state is not.

## Capability matrix

| Surface | Server contract | Current client behavior | Remaining gap |
| --- | --- | --- | --- |
| Overview | `GET /api/v1/overview` | Summary metrics, refresh, navigation to details | No event push, only explicit refresh and reload |
| PDF intake | `POST /api/v1/audits` | Web and Expo upload, size/extension checks, duplicate-submit guard | No resumable upload or server-side progress endpoint |
| Audit & conversation | Audit detail and NDJSON messages | Incremental events; route-specific state fencing | Network interruption cannot resume from an event cursor |
| Evidence Lens | Immutable paper and source annotations | Source-linked paper preview, inspector, finding navigation | Some context transfers depend on hash/session storage |
| Findings | Cursor pages + persisted audit details | Web first 50 with load-more; cross-link to paper | Native reads complete findings collection, no paging |
| Runs | Cursor pages + correlated detail/events | Bounded Web history, inspector and pagination | No live subscription; failed initial reads now have explicit Retry |
| Projects | Projects + audit assignment mutation | Create, filter and assign; errors roll back selectors | UI modules duplicate projection/refresh; no cross-tab sync |
| Notes | Audit record + `/notes` mutation | Local draft, keyboard save, persisted server snapshot | Concurrent editing across devices lacks revision conflicts |
| Search | `GET /api/v1/search` | One debounced abortable palette with retry | No search facets or server-side fuzzy ranking |
| Benchmarks | Catalog + paginated results | Read-only metrics and evaluation history | No client-side benchmark job submission flow |
| Settings | Capabilities + provider route probe | Inspect server config and perform controlled probe | No persisted server-authenticated configuration editor |
| Reproduction | ACP run/control, workspace/diffs | Streaming, cancellation and approval with explicit boundaries | On disconnect, persisted run state can be refreshed by ID; no full event resume or verified approval reacquisition |
| Native | Versioned `/api/v1` endpoints | Upload, audit chat and reproduction | Missing Web page-level pagination and most organizer tools |
| PWA | Static cache only | Shell available offline | Evidence, edits and execution require a live API; no offline queue |

## Ownership and consistency rules

1. **One owner per visible state.** `command-search.js` owns the palette;
   `app.js` only opens the dialog. The same event must not be attached to
   the same input by two independent modules.
2. **Selection always wins over completion order.** A selected paper, view,
   run, file, or inspector context has an identity/generation. Results for
   an older identity are ignored, not rendered.
3. **Committed mutations are separate from refresh.** A successful POST
   remains committed when a subsequent GET fails. Show that distinction,
   keep the authoritative resource ID, and offer a retry for the read.
4. **Unsaved user input is never discarded by stale responses.** A save
   snapshots its submitted content; text entered while it is in flight
   remains a new dirty draft. For notes across devices, add ETag/revision
   or `updated_at` preconditions before introducing auto-save.
5. **Browser history is navigable.** User-initiated cross-view actions
   create history entries, while initial render and popstate/hashchange
   reconciliation do not add new entries.
6. **Only the backend confirms success.** A locally selected project,
   resolved warning or optimistic audit message is not a persisted result.
   On a rejected mutation, restore the confirmed state.
7. **Offline shell is not offline data.** The service worker must never
   treat missing API connectivity as a successful mutation, cache paper
   evidence as public static shell data, or queue non-idempotent POSTs
   without an explicit design.

## Recoverable reads and uncertain execution state

The Web modules for **Runs, Settings and Benchmarks** now use an explicit
read-only retry path after the first API error. Their error state is an
accessible alert with a Retry button. A retry reissues the corresponding
GET, and route identity is checked before accepting its response. No
mutation is automatically replayed.

Reproduction's live NDJSON transport is **not a resumable subscription**.
An EOF or network error without a persisted terminal event now produces a
visible `unconfirmed` state. If a Run ID was observed, the UI provides
`Refresh persisted status` using only `GET /api/v1/runs/{run_id}`,
then refreshes its correlated history. It only clears the uncertainty when
the server reports a terminal `finish`, `error` or `cancelled` phase.
If no Run ID was observed, the API outcome is unknown and a retrying POST
could duplicate execution. **No automatic POST retries are allowed.**

Persisted permission events may still contain `decision=pending`, but a
replayed event cannot authorize a tool: approval buttons appear only while
the initiating Run's live stream remains active. Reconnect-time approval
requires a separate server-verified permission context protocol.

Feature-level errors can dispatch `veritas:notice` to the single Web toast
owner. Reproduction now uses this rather than directly editing the toast
element and auto-dismissing failure messages.

## State model for shared async primitives

- **Reads:** `idle → loading → ready | empty | error`. The response
  belongs to a route and resource key, not merely a DOM node. Retrying
  reuses the same endpoint and keeps errors accessible with `role=alert`.
- **Writes:** `clean → dirty → submitting → committed | rejected`.
  Preserve editable input across rejection. A committed write can still
  have a **refresh warning**; do not label that a write failure.
- **Streams:** `preparing → running → cancelling → completed | cancelled
  | failed | disconnected`. Network disconnect does not imply the
  server-side process has stopped. Reconcile via persisted run state.
- **Cross-view context:** pass an immutable ID (audit/finding/run) and
  resolve it from the API. Never trust only a title or a DOM selector.

## Prioritized remaining work

**P0: correctness and reliability**

- Finish event-cursor-based resynchronization for long-running audit and
  reproduction streams, with explicit terminal state reconciliation.
- Add revision preconditions for audit notes if multi-device collaboration
  is enabled. Preserve user data on conflict rather than last-write-wins.
- Build a safe, complete permission recovery contract before permitting
  reconnect-time approval of a running agent action.

**P1: scalability and parity**

- Move native Audit / Findings / Runs list views to the existing cursor
  endpoints, with visible load-more and correct empty/last-page UI.
- Replace duplicated Projects UI reads with a single subscribed local
  projection and refresh event; support another tab changing assignments.
- Add a shared versioned API error format, connection/offline banner, and
  permission-aware action disablement across platforms.
- Audit evidence selection IDs for stable navigation from tables, graph,
  findings, and replication review after page reload.

**P2: UX and accessibility**

- Keyboard and screen-reader tests for all modal and inspector variants;
  ensure proper focus return, accessible labels and sufficient text size.
- Saved Search filters, sorting, and clearer zero-result suggestions.
- Add carefully scoped optional live refresh to Runs/Overview without
  replacing user-selected inspector content.

## Acceptance gates for changes in this PR

- `scripts/smoke_workspace_interactions_browser.py`: one search request
  per query; Back restores a view; slow paper A cannot overwrite B;
  wrong/empty PDF is rejected without a POST.
- `scripts/smoke_async_navigation_browser.py`: delayed Settings, Runs and
  Reproduction API results do not repaint another route.
- `scripts/smoke_workspace_read_recovery_browser.py`: failed read-only Runs, Settings and Benchmarks GETs recover using in-place Retry.
- `scripts/smoke_replication_disconnect_browser.py`: a disconnected ACP live stream is reconciled through saved run detail without resubmitting POST.
- `scripts/smoke_ndjson_stream_browser.py`: split UTF-8, EOF and malformed
  frame behavior is consistent.
- Existing page/pagination, project and permissions smoke tests should
  continue to pass. Run the latest PR CI before considering merge.

No claim of complete native/Web parity or multi-user authentication is made
by the current implementation.
