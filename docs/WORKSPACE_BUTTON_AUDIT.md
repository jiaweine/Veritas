# Veritas workspace control audit

Reviewed 2026-10-12 on the open UI/API integration PR. This is an audit
of *wired interactions and failure handling*, not a certification that every
device, browser, server configuration, and live Agent tool path has been tested.

## Buttons and clickable surfaces

| Surface | Main controls | Expected observable result | Changes / evidence |
| --- | --- | --- | --- |
| Top bar & global navigation | Sidebar, avatar/settings, command search, Conversation | The correct SPA route, dialog or composer opens; Back and Forward restore route state | Previously inert avatar is a labelled Settings shortcut; shared search owner, route tests |
| Overview | Refresh, New audit, View audits, All runs, View all, Quick start cards | GET updates metrics, navigation opens real page, upload modal opens | Existing bindings; persist retryable GET errors |
| Audits | All / Ready / Running / Error, audit rows, Load more, New audit | Filter **loaded** rows without lying about older pages, keyboard opens a paper, load-more uses real server cursor | Status filter wired to paginated feed, zero-result message, aria-pressed, button/browser tests |
| Findings | Finding rows, Evidence, Reproduce, Claim Graph | Open audit/source context or move selected finding to Review/Replication | Existing finding-navigation/claim-graph handlers retained; source transitions remain server-grounded |
| Evidence | Paper rows, table/page selection, Open PDF | Open authoritative paper or source page; don't synthesize evidence | Existing PDF and page controls; keyboard activation on evidence rows |
| Audit Workbench | Audit, Files, Findings, Notes, Reproduction, sidebar commands | Only the active inspector tab is highlighted; Notes does not reopen after selecting Files/Audit | Removed hardcoded Audit selected class, wired source tab, accessible tab states, Notes session synchronization |
| Audit Notes | Save, Copy draft, Reload latest | Server revision checked; stale writes get 409, local draft survives network failure; reload prompts before discard | Existing notes tests and new live-tab regression |
| Projects | Create, assign, filter, Unassigned, Retry, Show all | Server-confirmed association; rejected mutation restores previous selection | Prior PR fixes; existing Projects Chromium smoke |
| Runs | Select row, Open paper, Load 50 more, Retry | Correlated detail, real PDF, validated page cursor or read-only retry | Existing pagination; retry error state; row and GET tests |
| Reproduction | Attach files, select paper/run, tabs, Refresh, Stop, Run Agent, permission decisions | Real API calls, no duplicate submits; live transcript persists across tab/history refresh; permission decisions are bound to the active live request | Live-event state, in-flight approval IDs, partial-upload reconciliation, error handlers, disconnect test |
| Benchmarks | History pagination, Retry | Read-only page extension and retry | Existing pagination/browser smoke, new failed-read recovery smoke |
| Settings | Provider quick look, Pin, Copy ID, Probe, API docs, Retry | Read-only server info, bounded model probe, clipboard behavior, proper error recovery | Existing power-interaction Chromium coverage; API docs route verified |
| Web upload | Choose file / drop PDF, Submit, Cancel, Close | Validate file; prevent false cancellation during POST; preserve write outcome | Added real drop handler, pending controls and browser regression |
| Expo | Tab bar, paper upload/selection, audit composer, reproduction approval | Same API contracts where implemented, protected against stale paper refresh | Existing mobile CI; native pagination and organizer parity remain incomplete |

## Correctness rules

1. An apparent button must have an observable action. If a server-side
   feature is unavailable, disable it with an explanation rather than
   displaying a nonfunctional control.
2. A click that sends a non-idempotent POST must not be auto-repeated after
   a timeout or disconnect. Browser navigation or modal dismissal must not
   be represented as cancelling an already submitted server write.
3. During a long-running Replication stream, the live trace and permissions
   must survive inspector/list rerenders. A *replayed* pending permission
   event is **not** a valid approval channel. Decisions are locked across
   a complete request, including rerender while the decision POST is pending.
4. Paginated filter counts and visible row sets are different facts. Audit
   status filters only hide loaded rows; users can explicitly load further
   pages. The independent Project filter also remains active.
5. User-initiated click and keyboard activation must have the same result
   for clickable audit/source table rows. Native <button> controls use
   aria-pressed or aria-selected where selection matters.
6. All module GET failures should have a recoverable read path, while
   mutation failures preserve user state and communicate partial success.

## Deliberate omissions / remaining gaps

- The search API currently indexes **audits and audit events**, not direct
  first-class finding/run entities. The placeholder is now honest:
  "Search papers and audit activity…". Search can still navigate to the
  Findings and Agent runs **views**. True entity search needs a validated
  indexed projection and stable destination links.
- The real live-Agent permission protocol is not resumable from persisted
  events; a disconnected Run can be inspected by GET, but cannot obtain
  a fresh approval UI without a server-validated reacquisition protocol.
- Native still lacks some Web organizer and pagination controls.
- An offline PWA shell is not a queued/offline editing implementation.
- This PR exercises representative controls in Chromium. Manual hardware
  testing, accessibility screen readers and failure injection with a
  real configured ACP Agent remain necessary before declaring parity.

## Acceptance coverage

- `scripts/smoke_workspace_buttons_browser.py`: settings shortcut, status
  filters and paging, drag-and-drop PDF, in-flight upload modal protection.
- `scripts/smoke_workspace_tabs_browser.py`: Audit/Files/Findings/Notes
  and return to Audit.
- `scripts/smoke_replication_disconnect_browser.py`: live pending permission
  across inspector refresh, disconnected run reconciliation, rejection of
  replayed permissions, no duplicate reproduction POST.
- `scripts/smoke_workspace_read_recovery_browser.py`: Runs, Settings and
  Benchmarks retry after a synthetic 503.
- Earlier screenshot, Projects, pagination, model provider and permissions
  browser smoke scripts still run in existing workflows.

Do not treat queued checks as passing; inspect the latest head SHA results
before merging.
