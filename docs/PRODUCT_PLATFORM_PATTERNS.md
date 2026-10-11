# Product interaction patterns from mature platforms

Reviewed 2026-10-12. This is a source-based design comparison, not a claim
that Veritas has feature parity with GitHub, Linear, Notion or Atlassian.

## Platform reference → Veritas decision

| Source and published guidance | Adapted rule | Implemented in this PR |
| --- | --- | --- |
| [GitHub Primer: Saving](https://primer.style/product/ui-patterns/saving/) — favor explicit saving for text forms; preserve contents when saving fails | Audit Notes use explicit Save and a server revision precondition; drafts survive failure and conflict | `store.set_notes(expected_updated_at=...)`, HTTP 409; `audit-notes.js` local revisions, Copy / Reload |
| [GitHub Primer: Empty states](https://primer.github.io/design/ui-patterns/empty-states/) — distinguish first use, no results and errors with an appropriate next action | Never present unavailable API data as a genuinely empty workspace | Retryable error notice on product refresh |
| [GitHub Primer: Loading](https://primer-docs-preview.github.com/product/ui-patterns/loading/) — visibly identify work in progress and make it accessible | Loading, upload, and streaming should not appear like silently failed operations | Upload pending state and explicit visible status |
| [GitHub Primer: Degraded experiences](https://primer.github.io/design/ui-patterns/degraded-experiences/) — do not imply data loss if content cannot be loaded | Keep previously known local context; show an unavailable/read failure separate from empty state | Error alert on failed workspace refresh, retryable read |
| [Linear: Search](https://linear.app/docs/search) — unified workspace search, shortcuts, recent work and resource navigation | One owner for the command palette; handle stale responses, server search and keyboard navigation in one place | Removed app.js duplicate; `command-search.js` owns search |
| [Atlassian Design: Flag](https://atlassian.design/components/flag) — error messages must not auto-dismiss, show a remedy | Failure notice remains until dismissed; optional Retry is keyboard-focusable | `showToast` role=alert / action, dark-theme action styles |
| [Notion: Offline pages](https://www.notion.com/help/use-pages-offline) — offline availability is explicit and limited; offline edits can conflict | Never describe the PWA's cached HTML as saved offline research; prevent silent last-writer-wins for notes | Documented PWA limits and Notes revision check |
| [Apple HIG: Buttons](https://developer.apple.com/design/human-interface-guidelines/buttons) — at least 44×44 pt touch targets; [Feedback](https://developer.apple.com/design/human-interface-guidelines/feedback) — clear state and consequences | Prioritize reachable primary mobile controls and readable labels, with distinct loading/error states | Enlarged native upload/back/send hit areas and bottom navigation text |

## Veritas-specific design decisions

- **Scientific evidence is server-owned**: optimistic UI may display a pending
  command, but it never manufactures a verification result. Immutable paper
  and source annotations stay linked to a real audit ID.
- **A note is editable text, not an instant toggle**: default to explicit
  Save. A new browser sends the last observed `notes_updated_at` (including
  explicit null). If it differs from the stored revision, API returns 409 and
  does not overwrite the record. Older clients that omit the version are
  supported temporarily for compatibility; they are *not* concurrency safe.
- **Conflict recovery does not drop work**: local draft and its base revision
  are stored under an audit-specific key. The UI can copy the draft before
  reloading remote content; failed reloads cannot discard it. This is not
  collaborative editing or a three-way merge.
- **Actionable errors persist**: short success confirmations may disappear.
  Important errors have an accessible label, a dismiss control, and a retry
  when a safe idempotent GET is available. Non-idempotent POSTs are not
  retried automatically.
- **Never infer server health from browser network availability alone**:
  `navigator.onLine` can distinguish a known offline device, but a server
  503 is an unavailable service, not proof that the browser is offline.
- **Nav context is an identity**: stale requests may resolve, but cannot
  repaint a newer audit, page or selected item. Browser Back/Forward
  restores the corresponding view.
- **Avoid pretending that the native app is feature complete**: Web has
  bounded history and review panes, while native parity for Notes, Projects
  and cursor pagination remains separate work.

## Follow-up design priorities (not yet implemented)

1. API-wide standard error schema with retryability and correlation ID;
   include precise accessible messages without leaking server secrets.
2. True audit/run event resumption using monotonically ordered cursors and
   reconciled terminal states; no repeated POST on disconnect.
3. Native cursor pagination, better accessible text scaling throughout the
   app, and dedicated loading/empty/error views.
4. Cross-tab project invalidation and user-visible filter chips.
5. A versioned notes migration policy so all clients eventually send
   preconditions; collaborative simultaneous editing would require further
   versioned merge semantics.

## Verification

- `tests/test_harness_audit_notes.py` checks initial/null revision, stale
  updates, compatibility, and two store instances.
- `scripts/smoke_workspace_interactions_browser.py` checks persistent
  retryable errors, single-owner search, browser history, audit selection
  ordering, and invalid PDF rejection.
- Latest GitHub Actions on the PR must still pass. No local Docker sandbox
  certification, cross-device end-to-end certification, or offline queue
  verification is claimed.
