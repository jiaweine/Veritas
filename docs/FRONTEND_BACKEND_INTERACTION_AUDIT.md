# Web and native interaction audit

Status: PR #133 changes under review. This is a source-level contract inventory,
not evidence of a multi-user production security review.

## Supported pathways

| Workflow | Client | Backend | Server-owned record |
| --- | --- | --- | --- |
| PDF intake | Web + Expo | `POST /api/v1/audits` | Audit and immutable PDF |
| Audit conversation | Web + Expo | `POST /api/v1/audits/{audit_id}/messages` | Persisted audit events and result |
| Document and result review | Web + Expo | `GET /api/v1/audits/{audit_id}` | Latest audit snapshot |
| Paginated history | Web | `/api/v1/audit-pages`, `/api/v1/finding-pages`, `/api/v1/run-pages` | Store projections |
| Evidence downloads | Web | `GET /api/v1/audits/{audit_id}/paper` | Immutable paper bytes |
| Reproduction | Web + Expo | `POST /api/v1/audits/{audit_id}/replication` | Replication run events and artifacts |
| Permission approval | Web + Expo | `POST /api/v1/replication/runs/{run_id}/permissions/{request_id}` | Server-controlled request state |
| Run cancellation | Web + Expo | `POST /api/v1/replication/runs/{run_id}/cancel` | Cancellation state, 409 when inactive |
| Workspace and diff | Web + Expo | `GET /api/v1/runs/{run_id}/workspace[/file]` | Bounded inspector, not a sandbox |
| Projects and notes | Web | `/api/v1/projects`, `/api/v1/audits/{audit_id}/project`, `/notes` | Persisted grouping and review notes |
| Model provider diagnostic | Web | `POST /api/v1/model-providers/probe` | Non-generative probe; server-side credentials |

## Interoperability decisions in this PR

- `ndjson-stream.js`: shared streaming parser for Web chat, Audit Workbench,
  and Reproduction. Handles arbitrary chunk boundaries, UTF-8 splits, and an
  unterminated final event; malformed frames raise a clear error.
- `mobile/stream.ts`: shared Expo parser for audit chat and replication. A
  non-streaming runtime falls back to full-response parsing for ordinary audit
  commands, but interactive permission approval requires incremental transport.
- Streamed audit events update only their initiating audit, avoiding accidental
  cross-paper UI state mutation when a user navigates mid-request.
- Runs and Reproduction discard stale run details, workspace files, and
  initialization responses rather than repainting the newly selected view.
- Settings ignores delayed provider/capability responses after navigation away.
- Error envelopes from the audit composer use the API's `detail` field when
  available, rather than only displaying an HTTP status phrase.

## Server boundaries and limitations

- The Web API is local-first. CORS must be enabled explicitly by
  `VERITAS_CORS_ORIGINS` for cross-origin browser clients. This is not a
  multi-user authentication or role-based access-control implementation.
- Replication commands/permission options remain server-controlled; the client
  does not choose the agent executable. A per-run inspection workspace is **not**
  a process isolation or security boundary.
- An NDJSON stream is a live response, not a resumable event subscription. If a
  client disconnects, use persisted audit and run details to reconcile state.
  Network disconnect should not be interpreted as a cancelled agent run; use
  the explicit cancel endpoint.
- `GET /api/v1/replication/runs/{run_id}/control` currently exposes
  pending permission IDs, option IDs, and timestamps, but does not include the
  complete action context needed to safely re-authorize after reconnecting.
  Neither client should reconstruct an approval UI from options alone. A
  future resumable approval flow should preserve an explicit, human-readable
  tool/action description in server-controlled state and provide a safe
  reacquisition protocol, with automatic denial on loss of context.
- Settings probes an existing server-side model provider configuration. The UI
  does **not** persist arbitrary runtime provider switches or credentials.
- The Expo overview and reproduction modules still request some full
  `/api/v1/audits`, `/api/v1/findings` and `/api/v1/runs` lists; they
  do not yet implement the browser's bounded history pagination.
- A POST request is not automatically retried after a partially received stream:
  it might have already created persisted results or run-side effects.

## Verification

- `scripts/smoke_ndjson_stream_browser.py` runs a real Chromium parser check
  across byte-split UTF-8, no final newline, invalid payloads, unsupported
  streaming bodies, and consumer errors.
- `scripts/smoke_workspace_theme_browser.py` includes route and modal smoke.
- Existing smoke scripts cover audit uploads, Evidence Lens, runs pagination,
  replication review, permission handling, and search. Review the PR's latest
  GitHub Actions results before merging; CI status is not implied by this document.
