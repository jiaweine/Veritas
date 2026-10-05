from __future__ import annotations

import colorsys
import re
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
STATIC = ROOT / "src/veritas/harness/static"


def replace_once(path: Path, old: str, new: str) -> None:
    text = path.read_text()
    count = text.count(old)
    if count != 1:
        raise SystemExit(f"expected one match in {path}: {count} for {old[:80]!r}")
    path.write_text(text.replace(old, new))


def neutral_rgb(r: int, g: int, b: int) -> tuple[int, int, int]:
    h, s, _ = colorsys.rgb_to_hsv(r / 255, g / 255, b / 255)
    deg = h * 360
    if s < 0.12 or not (180 <= deg <= 285):
        return r, g, b
    gray = round(0.2126 * r + 0.7152 * g + 0.0722 * b)
    return gray, gray, gray


def neutralize_colors(text: str) -> str:
    def hex_repl(match: re.Match[str]) -> str:
        raw = match.group(0)
        digits = raw[1:]
        alpha = ""
        if len(digits) == 8:
            alpha = digits[6:]
            digits = digits[:6]
        r, g, b = (int(digits[i : i + 2], 16) for i in (0, 2, 4))
        nr, ng, nb = neutral_rgb(r, g, b)
        if (nr, ng, nb) == (r, g, b):
            return raw.lower()
        return f"#{nr:02x}{ng:02x}{nb:02x}{alpha.lower()}"

    text = re.sub(r"#[0-9a-fA-F]{8}\b|#[0-9a-fA-F]{6}\b", hex_repl, text)

    def rgb_repl(match: re.Match[str]) -> str:
        prefix = match.group(1)
        r, g, b = (int(match.group(i)) for i in (2, 3, 4))
        tail = match.group(5) or ""
        nr, ng, nb = neutral_rgb(r, g, b)
        if (nr, ng, nb) == (r, g, b):
            return match.group(0)
        return f"{prefix}({nr},{ng},{nb}{tail})"

    return re.sub(
        r"\b(rgb|rgba)\(\s*(\d{1,3})\s*,\s*(\d{1,3})\s*,\s*(\d{1,3})(\s*,\s*[^)]+)?\)",
        rgb_repl,
        text,
    )


# 1) Give ordinary language a real, evidence-grounded conversational intent.
planner = ROOT / "src/veritas/harness/planner.py"
planner.write_text(
    '''from __future__ import annotations

import re
import shlex
from dataclasses import dataclass


@dataclass(frozen=True)
class AuditCommand:
    action: str
    row_label: str | None = None
    table_label: str | None = None
    expected_page: int | None = None


_SUMMARY_REQUESTS = {
    "summary",
    "summarize",
    "summarise",
    "summarize this paper",
    "summarise this paper",
    "summarize this audit",
    "summarise this audit",
    "what needs attention",
    "what should i review",
    "show findings",
    "show me the findings",
    "what are the findings",
    "current result",
    "audit result",
    "总结",
    "总结一下",
    "总结这篇论文",
    "总结这次审计",
    "有哪些问题",
    "有什么问题",
    "需要关注什么",
    "审计结果",
    "当前结果",
}

_INSPECT_REQUESTS = {
    "/inspect",
    "inspect",
    "inspect this paper",
    "show paper structure",
    "paper structure",
    "查看论文",
    "查看",
    "论文结构",
    "看看论文结构",
}


def _normalize_prompt(text: str) -> str:
    return re.sub(r"[?.!。！？]+$", "", text.strip().casefold()).strip()


def parse_command(message: str) -> AuditCommand:
    text = message.strip()
    if not text:
        raise ValueError("message is empty")

    lowered = _normalize_prompt(text)
    if lowered in {"/help", "help", "帮助"}:
        return AuditCommand("help")
    if lowered in _SUMMARY_REQUESTS:
        return AuditCommand("summary")
    if lowered in _INSPECT_REQUESTS:
        return AuditCommand("inspect")

    if lowered.startswith("/audit"):
        body = text[len("/audit") :].strip()
        return _parse_audit_body(body)
    if lowered.startswith("audit "):
        return _parse_audit_body(text[6:].strip())
    if text.startswith("审计"):
        return _parse_audit_body(text[2:].strip())
    if text.startswith("检查"):
        return _parse_audit_body(text[2:].strip())

    return AuditCommand("chat")


def help_text() -> str:
    return (
        'Ask “What needs attention?” for a summary grounded in the latest persisted audit, '
        'or “inspect this paper” to review detected structure. For a specific regression row, '
        'run `/audit row="Treatment" table=2 page=1`; table and page are optional when the row label is unique.'
    )


def _parse_audit_body(body: str) -> AuditCommand:
    if not body:
        raise ValueError(
            'audit requires a row label, for example `/audit row="Treatment" table=2 page=1`'
        )

    try:
        tokens = shlex.split(body)
    except ValueError as exc:
        raise ValueError(f"could not parse audit command: {exc}") from exc

    values: dict[str, str] = {}
    free: list[str] = []
    for token in tokens:
        if "=" in token:
            key, value = token.split("=", 1)
            key = key.casefold().strip()
            if key in {"row", "variable", "table", "page"}:
                values[key] = value.strip()
                continue
        free.append(token)

    row_label = values.get("row") or values.get("variable")
    if row_label is None and free:
        row_label = " ".join(free).strip()
    if not row_label:
        raise ValueError("audit requires a non-empty row label")

    table_label = values.get("table")
    if table_label:
        normalized = table_label.strip()
        if not re.search(r"\\btable\\b", normalized, flags=re.IGNORECASE):
            normalized = f"Table {normalized}"
        table_label = normalized

    page_value = values.get("page")
    expected_page = None
    if page_value is not None:
        try:
            expected_page = int(page_value)
        except ValueError as exc:
            raise ValueError("page must be an integer") from exc
        if expected_page <= 0:
            raise ValueError("page must be positive")

    return AuditCommand(
        "audit_regression",
        row_label=row_label,
        table_label=table_label,
        expected_page=expected_page,
    )
'''
)

service = ROOT / "src/veritas/harness/service.py"
service_text = service.read_text()
marker = "\n\nclass AuditHarness:"
if marker not in service_text:
    raise SystemExit("AuditHarness class marker missing")
helper = '''


def _conversation_summary(record: dict[str, Any]) -> tuple[str, str, str, dict[str, Any]]:
    """Derive a conversational answer only from persisted authoritative audit state."""
    paper = record.get("paper_summary") or {}
    result = record.get("latest_result") or {}
    if not result:
        pages = int(paper.get("pages") or 0)
        tables = int(paper.get("tables_detected") or 0)
        return (
            "No verification result yet",
            f"This paper has {pages} pages and {tables} detected tables. "
            "Inspect the paper structure or audit a specific reported row before asking for findings.",
            "review",
            {"conversation_intent": "summary", "has_result": False},
        )

    counts = result.get("counts") or {}
    verified = int(counts.get("verified") or 0)
    needs_review = int(counts.get("needs_review") or 0)
    contradictions = int(counts.get("contradictions") or 0)
    audit_status = str(result.get("status") or "review_required").replace("_", " ")
    findings = list(result.get("findings") or [])
    source = result.get("source") or {}
    location = " · ".join(
        part
        for part in (
            str(source.get("table") or "").strip(),
            f'p.{source.get("page")}' if source.get("page") else "",
            str(source.get("row") or "").strip(),
        )
        if part
    )

    detail = (
        f"Latest audit status: {audit_status}. "
        f"{verified} verified, {needs_review} need review, {contradictions} contradictions."
    )
    if findings:
        finding = findings[0]
        finding_title = str(finding.get("title") or "Finding")
        explanation = str(finding.get("explanation") or "").strip()
        detail += f" First persisted finding: {finding_title}."
        if explanation:
            detail += f" {explanation}"
    else:
        detail += " No persisted contradiction findings are attached to the latest result."
    if location:
        detail += f" Source: {location}."

    tone = "danger" if contradictions else "review" if needs_review else "success"
    return (
        "Current audit summary",
        detail,
        tone,
        {
            "conversation_intent": "summary",
            "has_result": True,
            "audit_status": result.get("status"),
            "counts": counts,
            "finding_count": len(findings),
            "source": source,
        },
    )
'''
if "def _conversation_summary(" not in service_text:
    service_text = service_text.replace(marker, helper + marker, 1)
old_branch = '''        if command.action == "help" or command.action == "chat":
            event = HarnessEvent(
                audit_id=audit_id,
                kind="assistant_message",
                title="Ready to audit this paper.",
                detail=help_text(),
                status="info",
                payload={"commands": ["/inspect", '/audit row="Treatment" table=2 page=1']},
            )
            self.store.append_event(event)
            yield event.to_dict()
            return
'''
new_branch = '''        if command.action == "help":
            event = HarnessEvent(
                audit_id=audit_id,
                kind="assistant_message",
                title="How to work with this paper",
                detail=help_text(),
                status="info",
                payload={
                    "commands": [
                        "What needs attention?",
                        "inspect this paper",
                        '/audit row="Treatment" table=2 page=1',
                    ]
                },
            )
            self.store.append_event(event)
            yield event.to_dict()
            return

        if command.action == "summary":
            title, detail, status, payload = _conversation_summary(record)
            event = HarnessEvent(
                audit_id=audit_id,
                kind="assistant_message",
                title=title,
                detail=detail,
                status=status,
                payload=payload,
            )
            self.store.append_event(event)
            yield event.to_dict()
            return

        if command.action == "chat":
            event = HarnessEvent(
                audit_id=audit_id,
                kind="assistant_message",
                title="I stay grounded in this audit.",
                detail=(
                    "I can summarize the latest persisted findings, inspect detected paper structure, "
                    "or run a deterministic audit on a reported row. I will not invent an answer beyond "
                    f"the evidence and tools available here. {help_text()}"
                ),
                status="review",
                payload={"conversation_intent": "bounded_help"},
            )
            self.store.append_event(event)
            yield event.to_dict()
            return
'''
if old_branch not in service_text:
    raise SystemExit("legacy chat/help branch missing")
service.write_text(service_text.replace(old_branch, new_branch, 1))

# 2) Make conversation the primary product entry point instead of a right-side utility.
index = STATIC / "index.html"
index_text = index.read_text()
replacements = {
    '<meta name="theme-color" content="#071116" />': '<meta name="theme-color" content="#0b0b0a" />',
    '<meta name="application-name" content="Research Audit Workbench" />': '<meta name="application-name" content="Veritas Research Conversation" />',
    '<title>Veritas · Research Audit Harness · Workbench</title>': '<title>Veritas · Evidence-grounded research conversation</title>',
    '<div class="brand-tagline">Research audit system</div>': '<div class="brand-tagline">Evidence-grounded research</div>',
    '<button id="new-audit" class="primary-button sidebar-primary">＋ New audit</button>': '<button id="new-audit" class="primary-button sidebar-primary">＋ New paper</button>',
    '<button class="nav-item active" data-view="overview"><span class="nav-icon">⌂</span><span>Overview</span></button>': '<button id="conversation-nav" class="nav-item active" type="button"><span class="nav-icon">✦</span><span>Conversation</span></button>\n          <button class="nav-item" data-view="overview"><span class="nav-icon">⌂</span><span>Workspace</span></button>',
    '          <a class="ghost-button desktop-only" href="/api/docs" target="_blank" rel="noreferrer">API</a>\n': '',
    '<button id="agent-toggle" class="ghost-button">Agent <span class="agent-indicator"></span></button>': '<button id="agent-toggle" class="ghost-button" aria-pressed="false">Conversation <span class="agent-indicator"></span></button>',
    '<aside id="agent-sidecar" class="agent-sidecar" aria-label="Audit agent">': '<aside id="agent-sidecar" class="agent-sidecar" aria-label="Research conversation">',
    '<strong>Audit Agent</strong>\n          <span class="online-label"><i></i> deterministic tools</span>': '<strong>Research conversation</strong>\n          <span class="online-label"><i></i> evidence-grounded</span>',
    '<button id="agent-close" class="icon-button" aria-label="Close agent">×</button>': '<button id="agent-close" class="icon-button" aria-label="Close conversation">×</button>',
    '<button data-agent-command="/inspect">Inspect</button>\n          <button data-agent-command="/audit ">Audit row</button>\n          <button data-agent-command="/help">Help</button>': '<button data-agent-command="What needs attention?">Summarize</button>\n          <button data-agent-command="inspect this paper">Inspect</button>\n          <button data-agent-command="/audit ">Audit row</button>',
    'placeholder="Ask about the selected paper…"': 'placeholder="Ask from this paper’s evidence…"',
    '<small>Commands are executed by Veritas\' deterministic audit harness.</small>': '<small>Answers stay attached to persisted audit evidence and deterministic tools.</small>',
    '<button class="mobile-nav-item active" data-view="overview"><span>⌂</span><small>Overview</small></button>': '<button class="mobile-nav-item" data-view="overview"><span>⌂</span><small>Workspace</small></button>',
    '<button id="mobile-new" class="mobile-create" aria-label="New audit">＋</button>': '<button id="mobile-new" class="mobile-create" aria-label="New paper">＋</button>',
    '<button id="mobile-agent" class="mobile-nav-item"><span>⌁</span><small>Agent</small></button>': '<button id="mobile-agent" class="mobile-nav-item active"><span>✦</span><small>Chat</small></button>',
    '<div><span class="eyebrow">New audit</span><h2>Upload a research paper</h2></div>': '<div><span class="eyebrow">New paper</span><h2>Add evidence to the conversation</h2></div>',
    '<button id="upload-submit" type="submit" class="primary-button" disabled>Parse & create audit</button>': '<button id="upload-submit" type="submit" class="primary-button" disabled>Parse & start conversation</button>',
}
for old, new in replacements.items():
    count = index_text.count(old)
    if count != 1:
        raise SystemExit(f"index replacement mismatch {count}: {old[:80]!r}")
    index_text = index_text.replace(old, new, 1)
index.write_text(index_text)

app = STATIC / "app.js"
app_text = app.read_text()

old_set_view = '''function setView(view, { push = true } = {}) {
  state.view = view;
  $$('[data-view]').forEach((node) => node.classList.toggle("active", node.dataset.view === view));
  document.body.classList.remove("sidebar-open");
  if (push) history.replaceState(null, "", `#${view}`);
  renderMain();
  els.main.focus({ preventScroll: true });
}
'''
new_set_view = '''function setView(view, { push = true } = {}) {
  if (state.agentOpen) setAgent(false);
  state.view = view;
  $$('[data-view]').forEach((node) => node.classList.toggle("active", node.dataset.view === view));
  document.body.classList.remove("sidebar-open");
  if (push) history.replaceState(null, "", `#${view}`);
  renderMain();
  els.main.focus({ preventScroll: true });
}
'''
if old_set_view not in app_text:
    raise SystemExit("setView block missing")
app_text = app_text.replace(old_set_view, new_set_view, 1)
app_text = app_text.replace(
    '${pageHead("Research audit cockpit", "Good morning. What needs verification?", "Veritas turns papers into inspectable evidence, deterministic checks, findings, and reproducible audit traces.",',
    '${pageHead("Research workspace", "Evidence, findings, and runs", "Conversation is the primary workflow; this workspace keeps the underlying papers, checks, findings, and execution traces inspectable.",',
    1,
)
app_text = app_text.replace(
    '{ kind: "view", id: "overview", title: "Overview", detail: "Research audit cockpit", icon: "⌂" },',
    '{ kind: "view", id: "overview", title: "Workspace", detail: "Evidence, findings, and audit state", icon: "⌂" },',
    1,
)
app_text = app_text.replace(
    '<button class="primary-button" data-action="agent-open">Open Agent</button>',
    '<button class="primary-button" data-action="agent-open">Open conversation</button>',
    1,
)
app_text = app_text.replace(
    'Open the Agent and run /audit row=\\"…\\" table=2 page=1 to create evidence-linked results.',
    'Open the conversation and audit a reported row to create evidence-linked results.',
    1,
)
app_text = app_text.replace(
    '    await openAudit(audit.audit_id);\n  } catch (error) { showToast(error.message); }\n  finally { state.sending = false; els.uploadSubmit.textContent = "Parse & create audit";',
    '    await openAudit(audit.audit_id);\n    await openConversation({ autoSelect: false });\n  } catch (error) { showToast(error.message); }\n  finally { state.sending = false; els.uploadSubmit.textContent = "Parse & start conversation";',
    1,
)

old_agent = '''function setAgent(open) {
  state.agentOpen = open;
  document.body.classList.toggle("agent-open", open);
  renderAgent();
  if (open && state.activeAudit) setTimeout(() => els.agentMessage.focus(), 100);
}

function renderAgent() {
  const audit = state.activeAudit;
  els.agentMessage.disabled = !audit || state.sending;
  els.agentSend.disabled = !audit || state.sending;
  if (!audit) {
    els.agentContext.innerHTML = `<div class="context-label">Current context</div><div class="context-title">No paper selected</div><div class="context-meta">Open an audit to give the harness evidence context.</div>`;
    els.agentTimeline.innerHTML = `<div class="agent-empty"><div><div class="empty-mark">⌁</div><strong>Agent is a collaboration layer</strong><p>It operates on the selected paper and emits structured tool events, findings, and evidence—not hidden state.</p></div></div>`;
    return;
  }
  const summary = audit.paper_summary || {};
  els.agentContext.innerHTML = `<div class="context-label">Current paper</div><div class="context-title">${escapeHtml(audit.title)}</div><div class="context-meta">${num(summary.pages)} pages · ${num(summary.tables_detected)} tables · ${escapeHtml(audit.status)}</div>`;
  const events = audit.events || [];
  els.agentTimeline.innerHTML = events.length ? events.slice(-18).map((event) => `<div class="trace"><span class="trace-dot ${escapeHtml(event.status || "")}">${event.kind === "tool" ? "⌁" : event.kind === "finding" ? "!" : event.kind === "user_message" ? "→" : "·"}</span><div class="trace-card"><strong>${escapeHtml(event.title)}</strong>${event.detail ? `<p>${escapeHtml(event.detail)}</p>` : ""}<div class="trace-meta">${escapeHtml(event.kind)} · ${shortTime(event.created_at)}</div></div></div>`).join("") : `<div class="agent-empty">Run <span class="mono">/inspect</span> to start the trace.</div>`;
  els.agentTimeline.scrollTop = els.agentTimeline.scrollHeight;
}
'''
new_agent = '''async function openConversation({ autoSelect = true } = {}) {
  if (!state.activeAudit && autoSelect && state.audits.length) {
    try {
      const auditId = state.audits[0].audit_id;
      state.activeAudit = await api(`/api/v1/audits/${encodeURIComponent(auditId)}`).then((r) => r.json());
    } catch (error) {
      showToast(error.message);
    }
  }
  setAgent(true);
}

function setAgent(open) {
  state.agentOpen = open;
  document.body.classList.toggle("agent-open", open);
  $("#conversation-nav")?.classList.toggle("active", open);
  $("#agent-toggle")?.setAttribute("aria-pressed", String(open));
  $("#mobile-agent")?.classList.toggle("active", open);
  if (open) {
    $$('[data-view]').forEach((node) => node.classList.remove("active"));
  } else {
    $$('[data-view]').forEach((node) => node.classList.toggle("active", node.dataset.view === state.view));
  }
  renderAgent();
  if (open && state.activeAudit) setTimeout(() => els.agentMessage.focus(), 100);
}

function renderAgent() {
  const audit = state.activeAudit;
  els.agentMessage.disabled = !audit || state.sending;
  els.agentSend.disabled = !audit || state.sending;
  if (!audit) {
    els.agentContext.innerHTML = `<div class="context-label">Research context</div><div class="context-title">Start with a paper</div><div class="context-meta">Veritas conversations stay attached to inspectable evidence instead of inventing a context.</div>`;
    els.agentTimeline.innerHTML = `<div class="agent-empty"><div><div class="empty-mark">V</div><strong>Add a paper to begin</strong><p>Upload a PDF, then ask what needs attention, inspect its structure, or audit a reported row.</p><button class="primary-button" type="button" data-conversation-upload="true">＋ Add paper</button></div></div>`;
    $("[data-conversation-upload]", els.agentTimeline)?.addEventListener("click", openUpload);
    return;
  }
  const summary = audit.paper_summary || {};
  els.agentContext.innerHTML = `<div class="context-label">Current paper</div><div class="context-title">${escapeHtml(audit.title)}</div><div class="context-meta">${num(summary.pages)} pages · ${num(summary.tables_detected)} tables · ${escapeHtml(audit.status)} · responses use persisted audit state</div>`;
  const events = audit.events || [];
  els.agentTimeline.innerHTML = events.length ? events.slice(-24).map((event) => `<div class="trace" data-kind="${escapeHtml(event.kind || "event")}"><span class="trace-dot ${escapeHtml(event.status || "")}">${event.kind === "tool" ? "⌁" : event.kind === "finding" ? "!" : event.kind === "user_message" ? "→" : event.kind === "assistant_message" ? "V" : "·"}</span><div class="trace-card"><strong>${escapeHtml(event.title)}</strong>${event.detail ? `<p>${escapeHtml(event.detail)}</p>` : ""}<div class="trace-meta">${event.kind === "user_message" ? "You" : event.kind === "assistant_message" ? "Veritas" : escapeHtml(event.kind)} · ${shortTime(event.created_at)}</div></div></div>`).join("") : `<div class="agent-empty"><div><strong>Ask from the evidence</strong><p>Try “What needs attention?” or inspect the paper structure.</p></div></div>`;
  els.agentTimeline.scrollTop = els.agentTimeline.scrollHeight;
}
'''
if old_agent not in app_text:
    raise SystemExit("legacy agent block missing")
app_text = app_text.replace(old_agent, new_agent, 1)
app_text = app_text.replace(
    '  } catch (error) { showToast(error.message); }\n  finally { state.sending = false; els.agentMessage.disabled = !state.activeAudit; els.agentSend.disabled = !state.activeAudit; }\n}\n\nfunction commandDefaults()',
    '  } catch (error) { els.agentMessage.value = message; showToast(error.message); }\n  finally { state.sending = false; els.agentMessage.disabled = !state.activeAudit; els.agentSend.disabled = !state.activeAudit; }\n}\n\nfunction commandDefaults()',
    1,
)
app_text = app_text.replace(
    '  $("#agent-toggle").addEventListener("click", () => setAgent(!state.agentOpen));\n  $("#mobile-agent").addEventListener("click", () => setAgent(true));',
    '  $("#conversation-nav").addEventListener("click", () => openConversation());\n  $("#agent-toggle").addEventListener("click", () => state.agentOpen ? setAgent(false) : openConversation());\n  $("#mobile-agent").addEventListener("click", () => openConversation());',
    1,
)
app_text = app_text.replace(
    '  $$('["'"'][data-action="agent-open"]'["'"'], els.main).forEach((node) => node.addEventListener("click", () => setAgent(true)));',
    '  $$('["'"'][data-action="agent-open"]'["'"'], els.main).forEach((node) => node.addEventListener("click", () => openConversation()));',
    1,
)
old_boot = '''  if (hash.startsWith("audit=")) {
    await openAudit(decodeURIComponent(hash.split("=").slice(1).join("=")));
  } else if (["overview","audits","findings","runs","evidence","reproduction","benchmarks","settings"].includes(hash)) {
    setView(hash, { push: false });
  } else renderMain();
  renderAgent();
'''
new_boot = '''  if (hash.startsWith("audit=")) {
    await openAudit(decodeURIComponent(hash.split("=").slice(1).join("=")));
  } else if (["overview","audits","findings","runs","evidence","reproduction","benchmarks","settings"].includes(hash)) {
    setView(hash, { push: false });
  } else {
    renderMain();
    await openConversation();
  }
  renderAgent();
'''
if old_boot not in app_text:
    raise SystemExit("boot block missing")
app_text = app_text.replace(old_boot, new_boot, 1)
app.write_text(app_text)

# 3) Replace the old sidecar presentation with a neutral, conversation-first workspace.
styles = STATIC / "styles.css"
styles_text = styles.read_text()
root_old = ''':root {
  --bg: #f6f7f9;
  --surface: #ffffff;
  --surface-soft: #fafbfc;
  --surface-strong: #f1f3f6;
  --sidebar: #151a27;
  --sidebar-soft: #222838;
  --text: #151927;
  --text-soft: #626b7d;
  --text-faint: #8a93a4;
  --line: #e4e7ec;
  --line-strong: #d8dce4;
  --accent: #5368f5;
  --accent-soft: #eef0ff;
  --accent-ink: #3346c8;
'''
root_new = ''':root {
  --bg: #f4f3ef;
  --surface: #ffffff;
  --surface-soft: #f8f7f3;
  --surface-strong: #efede7;
  --sidebar: #0b0b0a;
  --sidebar-soft: #1c1c1a;
  --text: #191918;
  --text-soft: #65645f;
  --text-faint: #929087;
  --line: #e4e1da;
  --line-strong: #d5d1c8;
  --accent: #191918;
  --accent-soft: #efede7;
  --accent-ink: #111110;
'''
if root_old not in styles_text:
    raise SystemExit("root palette block missing")
styles_text = styles_text.replace(root_old, root_new, 1)
styles_text = styles_text.replace(
    'button:focus-visible, input:focus-visible, textarea:focus-visible, a:focus-visible { outline: 2px solid rgba(83,104,245,.45); outline-offset: 2px; }',
    'button:focus-visible, input:focus-visible, textarea:focus-visible, a:focus-visible { outline: 2px solid rgba(25,25,24,.42); outline-offset: 2px; }',
    1,
)
styles_text = styles_text.replace(
    '.sidebar { min-width: 0; height: 100dvh; background: linear-gradient(180deg, #171d2b 0%, #131823 100%); color: #eef1f7;',
    '.sidebar { min-width: 0; height: 100dvh; background: linear-gradient(180deg, #10100f 0%, #090909 100%); color: #f3f1eb;',
    1,
)
styles_text = styles_text.replace(
    '.primary-button { min-height: 36px; border-radius: 8px; background: var(--accent); color: white; padding: 0 14px; font-weight: 650; font-size: 12px; box-shadow: 0 5px 12px rgba(83,104,245,.18); }\n.primary-button:hover { background: #485de9; }',
    '.primary-button { min-height: 36px; border-radius: 8px; background: var(--accent); color: white; padding: 0 14px; font-weight: 650; font-size: 12px; box-shadow: 0 5px 12px rgba(0,0,0,.12); }\n.primary-button:hover { background: #2c2c29; }',
    1,
)
styles_text = styles_text.replace(
    '.nav-item.active { background: #283045; color: white; box-shadow: inset 2px 0 0 #6f80ff; }',
    '.nav-item.active { background: #262624; color: white; box-shadow: inset 2px 0 0 #f0eee8; }',
    1,
)
styles_text = styles_text.replace(
    '.nav-item.active .nav-icon { color: #a9b4ff; }',
    '.nav-item.active .nav-icon { color: #f0eee8; }',
    1,
)

conversation_css = r'''.agent-sidecar { position: fixed; top: 0; left: var(--sidebar-width); right: 0; bottom: 0; width: auto; background: var(--bg); border-left: 1px solid var(--line); z-index: 40; display: flex; flex-direction: column; transform: translateY(10px); opacity: 0; pointer-events: none; transition: transform .18s ease, opacity .18s ease; }
body.agent-open .agent-sidecar { transform: translateY(0); opacity: 1; pointer-events: auto; }
body.agent-open .app-main { margin-right: 0; }
.sidecar-header { min-height: 64px; border-bottom: 1px solid var(--line); display: flex; align-items: center; justify-content: space-between; padding: 0 22px; background: rgba(244,243,239,.96); backdrop-filter: blur(12px); }
.sidecar-header > div:first-child { display: flex; align-items: center; gap: 9px; }
.sidecar-header strong { font-size: 12px; letter-spacing: -.01em; }
.online-label { display: inline-flex; gap: 5px; align-items: center; color: #28745d; background: #e7f3ee; border-radius: 999px; padding: 3px 7px; font-size: 7.5px; font-weight: 650; }
.online-label i { width: 5px; height: 5px; }
.agent-context { width: min(900px, calc(100% - 40px)); margin: 24px auto 0; padding: 14px 16px; border: 1px solid var(--line); border-radius: 14px; background: var(--surface); box-shadow: var(--shadow-small); }
.context-label { color: var(--text-faint); text-transform: uppercase; letter-spacing: .09em; font-weight: 700; font-size: 7.5px; }
.context-title { margin-top: 5px; font-size: 12px; font-weight: 700; overflow: hidden; text-overflow: ellipsis; white-space: nowrap; }
.context-meta { margin-top: 4px; color: var(--text-soft); font-size: 8.5px; }
.agent-timeline { width: min(900px, calc(100% - 40px)); flex: 1; min-height: 0; overflow: auto; margin: 0 auto; padding: 24px 6px 30px; }
.agent-empty { min-height: 360px; display: grid; place-items: center; text-align: center; color: var(--text-soft); font-size: 10px; padding: 36px; }
.agent-empty > div { max-width: 430px; }
.agent-empty strong { display: block; color: var(--text); font-size: 18px; margin-top: 10px; letter-spacing: -.02em; }
.agent-empty p { margin: 8px 0 16px; line-height: 1.6; }
.trace { display: grid; grid-template-columns: 22px minmax(0,1fr); gap: 9px; position: relative; padding: 0 0 16px; }
.trace:not(:last-child)::before { content: ""; position: absolute; left: 10px; top: 21px; bottom: -1px; width: 1px; background: var(--line); }
.trace-dot { width: 20px; height: 20px; border-radius: 50%; border: 1px solid var(--line-strong); background: white; display: grid; place-items: center; font-size: 8px; color: var(--text-soft); z-index: 1; }
.trace-dot.success { color: var(--good); border-color: #bfe8d9; background: var(--good-soft); }
.trace-dot.danger { color: var(--bad); border-color: #f0c9cd; background: var(--bad-soft); }
.trace-dot.running { color: var(--text); border-color: var(--line-strong); background: var(--surface-strong); }
.trace-card { max-width: 760px; border: 1px solid var(--line); border-radius: 13px; padding: 11px 13px; background: var(--surface); }
.trace-card strong { font-size: 10px; display: block; line-height: 1.45; }
.trace-card p { margin: 5px 0 0; font-size: 9px; color: var(--text-soft); line-height: 1.55; }
.trace-meta { margin-top: 7px; color: var(--text-faint); font-size: 7.5px; }
.trace[data-kind="user_message"] { grid-template-columns: 1fr; justify-items: end; }
.trace[data-kind="user_message"]::before, .trace[data-kind="user_message"] .trace-dot { display: none; }
.trace[data-kind="user_message"] .trace-card { max-width: min(680px, 78%); background: #1a1a18; border-color: #1a1a18; color: white; }
.trace[data-kind="user_message"] .trace-card p, .trace[data-kind="user_message"] .trace-meta { color: #d5d3cd; }
.trace[data-kind="assistant_message"] .trace-card { border-color: transparent; background: transparent; padding-top: 2px; }
.trace[data-kind="assistant_message"] .trace-card strong { font-size: 12px; }
.trace[data-kind="tool"] .trace-card, .trace[data-kind="replication"] .trace-card { background: #f9f8f5; }
.agent-composer { border-top: 1px solid var(--line); padding: 12px 20px calc(14px + env(safe-area-inset-bottom)); background: rgba(244,243,239,.97); backdrop-filter: blur(14px); }
.command-chips { width: min(900px, 100%); display: flex; gap: 6px; margin: 0 auto 8px; }
.command-chips button { border: 1px solid var(--line-strong); border-radius: 999px; background: var(--surface); padding: 6px 9px; color: var(--text-soft); font-size: 8px; cursor: pointer; }
.command-chips button:hover { background: var(--surface-strong); color: var(--text); }
.composer-box { width: min(900px, 100%); margin: 0 auto; display: grid; grid-template-columns: minmax(0,1fr) 34px; align-items: end; border: 1px solid var(--line-strong); border-radius: 16px; padding: 8px; background: white; box-shadow: 0 7px 28px rgba(0,0,0,.07); }
.composer-box:focus-within { border-color: #96938a; box-shadow: 0 0 0 3px rgba(25,25,24,.08), 0 7px 28px rgba(0,0,0,.07); }
.composer-box textarea { border: 0; outline: 0; resize: none; min-height: 38px; max-height: 120px; color: var(--text); background: transparent; font-size: 10px; line-height: 1.5; padding: 7px 8px; }
.composer-box textarea::placeholder { color: #a09e96; }
.composer-box button { width: 32px; height: 32px; border: 0; border-radius: 10px; background: var(--accent); color: white; cursor: pointer; }
.composer-box button:disabled { opacity: .3; cursor: default; }
.agent-composer > small { width: min(900px, 100%); display: block; margin: 7px auto 0; color: var(--text-faint); font-size: 7.5px; padding: 0 4px; }
'''
styles_text, count = re.subn(
    r"\.agent-sidecar \{.*?\n\n\.workbench \{",
    conversation_css + "\n.workbench {",
    styles_text,
    count=1,
    flags=re.S,
)
if count != 1:
    raise SystemExit(f"conversation CSS block replacement count={count}")
styles_text = styles_text.replace(
    '.agent-sidecar { width: min(430px, 100vw); padding-bottom: calc(64px + env(safe-area-inset-bottom)); }',
    '.agent-sidecar { left: 0; width: 100vw; padding-bottom: calc(64px + env(safe-area-inset-bottom)); }',
    1,
)
styles.write_text(styles_text)

# Neutralize blue/indigo/cool-blue literals in every active web stylesheet/script and product shell asset.
html = index.read_text()
active_css = re.findall(r'<link[^>]+href="/static/([^"]+\.css)"', html)
active_js = re.findall(r'<script[^>]+src="/static/([^"]+\.js)"', html)
for name in active_css + active_js:
    path = STATIC / name
    path.write_text(neutralize_colors(path.read_text()))
for name in ("index.html", "manifest.webmanifest", "icon.svg"):
    path = STATIC / name
    path.write_text(neutralize_colors(path.read_text()))

# Brand shell details should be intentionally neutral, not merely grayscale-converted.
icon = STATIC / "icon.svg"
icon.write_text(icon.read_text().replace('fill="#191919"', 'fill="#0b0b0a"').replace('fill="#151a27"', 'fill="#0b0b0a"'))
manifest = STATIC / "manifest.webmanifest"
manifest.write_text(
    manifest.read_text()
    .replace('"background_color": "#f6f7f9"', '"background_color": "#f4f3ef"')
    .replace('"theme_color": "#f6f7f9"', '"theme_color": "#0b0b0a"')
)

# Mobile uses the same no-blue product contract and opens the latest evidence conversation on first launch.
mobile_app = ROOT / "mobile/App.tsx"
mobile_text = mobile_app.read_text().replace(
    'import React, { useCallback, useEffect, useMemo, useState } from "react";',
    'import React, { useCallback, useEffect, useMemo, useRef, useState } from "react";',
    1,
)
mobile_text = mobile_text.replace(
    '  const [message, setMessage] = useState("");\n\n  const load = useCallback(async () => {',
    '  const [message, setMessage] = useState("");\n  const didOpenInitialConversation = useRef(false);\n\n  const load = useCallback(async () => {',
    1,
)
mobile_text = mobile_text.replace(
    '      setOverview(o);\n      setAudits(a);\n      setFindings(f);\n      if (activeAudit) {',
    '      setOverview(o);\n      setAudits(a);\n      setFindings(f);\n      if (!didOpenInitialConversation.current) {\n        didOpenInitialConversation.current = true;\n        if (a[0]?.audit_id) {\n          const first = await request(`/api/v1/audits/${encodeURIComponent(a[0].audit_id)}`).then((r) => r.json());\n          setActiveAudit(first);\n        }\n      } else if (activeAudit) {',
    1,
)
mobile_text = mobile_text.replace('placeholder="Ask the audit harness…"', 'placeholder="Ask from this paper’s evidence…"')
mobile_app.write_text(neutralize_colors(mobile_text))
for mobile_file in (ROOT / "mobile").glob("*.tsx"):
    if mobile_file == mobile_app:
        continue
    mobile_file.write_text(neutralize_colors(mobile_file.read_text()))

# 4) Regression tests: conversation intent/authority + permanent no-blue design contract.
conversation_test = ROOT / "tests/test_conversation_product_contract.py"
conversation_test.write_text(
    '''from __future__ import annotations

import colorsys
import re
from pathlib import Path

from veritas.harness.planner import parse_command
from veritas.harness.service import _conversation_summary


ROOT = Path(__file__).resolve().parents[1]
STATIC = ROOT / "src/veritas/harness/static"


def test_natural_language_summary_and_inspect_intents() -> None:
    assert parse_command("What needs attention?").action == "summary"
    assert parse_command("有哪些问题？").action == "summary"
    assert parse_command("summarize this paper").action == "summary"
    assert parse_command("inspect this paper").action == "inspect"
    assert parse_command("tell me a joke").action == "chat"


def test_conversation_summary_uses_only_persisted_audit_state() -> None:
    record = {
        "paper_summary": {"pages": 12, "tables_detected": 4},
        "latest_result": {
            "status": "contradiction",
            "counts": {"verified": 2, "needs_review": 1, "contradictions": 1},
            "findings": [
                {
                    "title": "Regression reporting contradiction",
                    "explanation": "Reported p-value is incompatible with the statistic.",
                }
            ],
            "source": {"table": "Table 4", "page": 8, "row": "Minimum wage"},
        },
    }
    title, detail, status, payload = _conversation_summary(record)
    assert title == "Current audit summary"
    assert status == "danger"
    assert "2 verified" in detail
    assert "Regression reporting contradiction" in detail
    assert "Table 4" in detail and "p.8" in detail
    assert payload["counts"]["contradictions"] == 1
    assert payload["finding_count"] == 1


def test_conversation_summary_fails_closed_without_a_result() -> None:
    title, detail, status, payload = _conversation_summary(
        {"paper_summary": {"pages": 3, "tables_detected": 1}}
    )
    assert title == "No verification result yet"
    assert status == "review"
    assert "3 pages" in detail and "1 detected tables" in detail
    assert payload == {"conversation_intent": "summary", "has_result": False}


def _assert_not_blue_literal(path: Path, text: str) -> None:
    colors: list[tuple[int, int, int, str]] = []
    for match in re.finditer(r"#[0-9a-fA-F]{8}\\b|#[0-9a-fA-F]{6}\\b", text):
        value = match.group(0)
        digits = value[1:7]
        colors.append((*(int(digits[i : i + 2], 16) for i in (0, 2, 4)), value))
    for match in re.finditer(
        r"\\b(?:rgb|rgba)\\(\\s*(\\d{1,3})\\s*,\\s*(\\d{1,3})\\s*,\\s*(\\d{1,3})",
        text,
    ):
        colors.append((int(match.group(1)), int(match.group(2)), int(match.group(3)), match.group(0)))

    violations = []
    for r, g, b, literal in colors:
        h, s, _ = colorsys.rgb_to_hsv(r / 255, g / 255, b / 255)
        if s >= 0.12 and 180 <= h * 360 <= 285:
            violations.append(literal)
    assert not violations, f"blue/indigo literals remain in {path}: {violations[:12]}"


def test_active_product_palette_has_no_blue_or_indigo() -> None:
    html = (STATIC / "index.html").read_text()
    active_css = re.findall(r'<link[^>]+href="/static/([^\"]+\\.css)"', html)
    active_js = re.findall(r'<script[^>]+src="/static/([^\"]+\\.js)"', html)
    paths = [STATIC / name for name in active_css + active_js]
    paths += [STATIC / "index.html", STATIC / "manifest.webmanifest", STATIC / "icon.svg"]
    paths += sorted((ROOT / "mobile").glob("*.tsx"))
    for path in paths:
        _assert_not_blue_literal(path, path.read_text())


def test_conversation_is_the_default_product_entry_not_a_side_utility() -> None:
    html = (STATIC / "index.html").read_text()
    app = (STATIC / "app.js").read_text()
    assert 'id="conversation-nav"' in html
    assert "Research conversation" in html
    assert ">API</a>" not in html
    assert "await openConversation();" in app
    assert "els.agentMessage.value = message; showToast(error.message);" in app
'''
)

# 5) Real Chromium acceptance for the actual conversation composer, failure recovery, persistence, and workspace escape hatch.
smoke = ROOT / "scripts/smoke_conversation_browser.py"
smoke.write_text(
    '''from __future__ import annotations

import argparse
import json
from pathlib import Path

import httpx
from playwright.sync_api import Route, sync_playwright

from smoke_harness_browser import _seed_contradiction_audit, _wait_for_server


def run(base_url: str, output_dir: Path) -> None:
    output_dir.mkdir(parents=True, exist_ok=True)
    with httpx.Client(base_url=base_url, timeout=30.0) as client:
        _wait_for_server(client)
        audit_id, _ = _seed_contradiction_audit(client)
        audit = client.get(f"/api/v1/audits/{audit_id}").json()
        audit_title = audit["title"]

    with sync_playwright() as playwright:
        browser = playwright.chromium.launch()
        page = browser.new_page(viewport={"width": 1536, "height": 960})
        page.goto(f"{base_url}/", wait_until="networkidle")
        page.wait_for_function("document.body.classList.contains('agent-open')", timeout=20_000)

        sidecar = page.locator("#agent-sidecar")
        sidecar.wait_for(state="visible", timeout=10_000)
        if "Research conversation" not in sidecar.inner_text():
            raise AssertionError("Default product entry is not the research conversation")
        context = page.locator("#agent-context")
        if audit_title not in context.inner_text():
            raise AssertionError("Conversation did not select the latest authoritative paper context")

        composer = page.locator("#agent-message")
        if composer.is_disabled():
            raise AssertionError("Conversation composer stayed disabled with an active audit")

        failed_once = {"value": False}

        def fail_first_message(route: Route) -> None:
            if failed_once["value"]:
                route.continue_()
                return
            failed_once["value"] = True
            route.fulfill(
                status=503,
                content_type="application/json",
                body=json.dumps({"detail": "temporary conversation failure"}),
            )

        page.route("**/api/v1/audits/*/messages", fail_first_message)
        composer.fill("What needs attention?")
        page.locator("#agent-send").click()
        page.locator("#toast").wait_for(state="visible", timeout=10_000)
        if "temporary conversation failure" not in page.locator("#toast").inner_text():
            raise AssertionError("Conversation failure was not surfaced to the user")
        if composer.input_value() != "What needs attention?":
            raise AssertionError("Failed conversation request did not restore the user's draft")
        if composer.is_disabled():
            raise AssertionError("Conversation composer did not recover after request failure")
        page.unroute("**/api/v1/audits/*/messages", fail_first_message)

        page.locator("#agent-send").click()
        page.wait_for_function(
            """() => {
              const text = document.querySelector('#agent-timeline')?.textContent || '';
              return text.includes('Current audit summary') && text.includes('Regression reporting contradiction');
            }""",
            timeout=20_000,
        )
        if composer.input_value():
            raise AssertionError("Successful conversation send did not clear the composer")

        page.screenshot(path=output_dir / "conversation-home.png", full_page=True)
        page.reload(wait_until="networkidle")
        page.wait_for_function("document.body.classList.contains('agent-open')", timeout=20_000)
        page.wait_for_function(
            """() => (document.querySelector('#agent-timeline')?.textContent || '').includes('Current audit summary')""",
            timeout=20_000,
        )
        timeline = page.locator("#agent-timeline").inner_text()
        if "What needs attention?" not in timeline:
            raise AssertionError("Persisted user message disappeared after refresh")

        page.locator("#agent-close").click()
        page.wait_for_function("!document.body.classList.contains('agent-open')", timeout=10_000)
        workspace = page.locator("#main-content")
        if "Evidence, findings, and runs" not in workspace.inner_text():
            raise AssertionError("Closing conversation did not reveal the secondary workspace")
        page.locator("#conversation-nav").click()
        page.wait_for_function("document.body.classList.contains('agent-open')", timeout=10_000)
        browser.close()


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--base-url", default="http://127.0.0.1:8765")
    parser.add_argument("--output-dir", type=Path, required=True)
    args = parser.parse_args()
    run(args.base_url.rstrip("/"), args.output_dir)


if __name__ == "__main__":
    main()
'''
)

workflow = ROOT / ".github/workflows/ui-visual-smoke.yml"
workflow_text = workflow.read_text()
needle_path = '      - "scripts/smoke_overview_projection_browser.py"\n'
if needle_path not in workflow_text:
    raise SystemExit("ui workflow path anchor missing")
workflow_text = workflow_text.replace(
    needle_path,
    needle_path + '      - "scripts/smoke_conversation_browser.py"\n',
    2,
)
needle_run = '''          python scripts/smoke_overview_projection_browser.py \\
            --base-url http://127.0.0.1:8765 \\
            --output-dir artifacts/ui
'''
if needle_run not in workflow_text:
    raise SystemExit("ui workflow run anchor missing")
workflow_text = workflow_text.replace(
    needle_run,
    needle_run
    + '''          python scripts/smoke_conversation_browser.py \\
            --base-url http://127.0.0.1:8765 \\
            --output-dir artifacts/ui
''',
    1,
)
workflow.write_text(workflow_text)

# The diagnostic/patch machinery must never survive into the product candidate.
for temporary in (
    ROOT / ".github/workflows/product-audit-temp.yml",
    ROOT / "scripts/product_conversation_patch_temp.py",
):
    if temporary.exists():
        temporary.unlink()

print("conversation-first neutral product patch applied")
