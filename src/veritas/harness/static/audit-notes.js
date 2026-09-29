const main = document.querySelector("#main-content");

const SESSION_PREFIX = "veritas:audit-harness:session:v1:";
const DRAFT_PREFIX = "veritas:audit-harness:notes-draft:v1:";
const MAX_NOTES_CHARS = 50000;

const notesState = {
  auditId: "",
  active: false,
  loadedAuditId: "",
  serverText: "",
  serverUpdatedAt: null,
  loading: false,
  saving: false,
  error: "",
  requestToken: 0,
};

const esc = (value = "") => String(value)
  .replaceAll("&", "&amp;")
  .replaceAll("<", "&lt;")
  .replaceAll(">", "&gt;")
  .replaceAll('"', "&quot;")
  .replaceAll("'", "&#039;");

function auditRoot() {
  return main?.querySelector("[data-audit-harness='true']") || null;
}

function activeAuditId(root = auditRoot()) {
  return root?.dataset.auditId || "";
}

function sessionKey(auditId) {
  return `${SESSION_PREFIX}${auditId}`;
}

function draftKey(auditId) {
  return `${DRAFT_PREFIX}${auditId}`;
}

function readSession(auditId) {
  try {
    const raw = localStorage.getItem(sessionKey(auditId));
    return raw ? JSON.parse(raw) : {};
  } catch {
    return {};
  }
}

function saveSessionPatch(auditId, patch) {
  if (!auditId) return;
  try {
    localStorage.setItem(sessionKey(auditId), JSON.stringify({ ...readSession(auditId), ...patch }));
  } catch {}
}

function readDraft(auditId) {
  try {
    const value = localStorage.getItem(draftKey(auditId));
    return value === null ? null : value;
  } catch {
    return null;
  }
}

function writeDraft(auditId, value) {
  try { localStorage.setItem(draftKey(auditId), value); } catch {}
}

function clearDraft(auditId) {
  try { localStorage.removeItem(draftKey(auditId)); } catch {}
}

function formatTimestamp(value) {
  if (!value) return "Not saved yet";
  const date = new Date(value);
  return Number.isNaN(date.getTime()) ? "Saved" : `Saved ${date.toLocaleString()}`;
}

function notesButton(root) {
  return root.querySelector("[data-ah-notes-tab]");
}

function ensureNotesTab(root) {
  let button = notesButton(root);
  if (!button) {
    const provenance = root.querySelector(".ah-workspace-tabs [data-ah-tab='provenance']");
    if (!provenance) return null;
    button = document.createElement("button");
    button.type = "button";
    button.dataset.ahNotesTab = "true";
    button.textContent = "Notes";
    provenance.replaceWith(button);
  }
  if (button.dataset.ahNotesBound !== "true") {
    button.dataset.ahNotesBound = "true";
    button.addEventListener("click", () => openNotes(auditRoot()));
  }
  return button;
}

function ensureAuditExit(root) {
  const button = root.querySelector(".ah-workspace-tabs button:first-child");
  if (!button || button.dataset.ahNotesExitBound === "true") return;
  button.dataset.ahNotesExitBound = "true";
  button.addEventListener("click", () => {
    if (!notesState.active) return;
    const auditId = activeAuditId(root);
    notesState.active = false;
    saveSessionPatch(auditId, { tab: "source" });
    root.querySelector("[data-ah-tab='source']")?.click();
  });
}

function setTopTabState(root, active) {
  const workspaceTabs = root.querySelectorAll(".ah-workspace-tabs button");
  if (active) workspaceTabs.forEach((node) => node.classList.remove("active"));
  notesButton(root)?.classList.toggle("active", active);
}

function noteValue(auditId) {
  const draft = readDraft(auditId);
  return draft === null ? notesState.serverText : draft;
}

function renderNotesSurface(root) {
  const auditId = activeAuditId(root);
  const right = root.querySelector(".ah-right");
  const head = right?.querySelector(".ah-inspector-head");
  const tabs = right?.querySelector(".ah-tabs");
  const inspector = right?.querySelector("#ah-inspector");
  if (!auditId || !right || !head || !tabs || !inspector) return;

  setTopTabState(root, true);
  right.classList.add("ah-notes-active");
  tabs.hidden = true;
  head.innerHTML = `<div><strong>Audit Notes</strong><small>working context for this paper</small></div><span>${esc(formatTimestamp(notesState.serverUpdatedAt))}</span>`;

  if (notesState.loading) {
    inspector.innerHTML = `<div class="ah-notes-loading"><span class="ah-notes-spinner"></span><strong>Loading notes…</strong></div>`;
    return;
  }

  const value = noteValue(auditId);
  const draft = readDraft(auditId);
  const dirty = draft !== null && draft !== notesState.serverText;
  if (draft !== null && draft === notesState.serverText) clearDraft(auditId);
  inspector.innerHTML = `<section class="ah-notes-pane" data-ah-notes-pane="true">
    <div class="ah-notes-copy"><span>Workspace notes</span><p>Capture review context, follow-ups, and handoff details here. Evidence stays in the linked Source and Provenance views.</p></div>
    ${notesState.error ? `<div class="ah-notes-error" role="alert">${esc(notesState.error)}</div>` : ""}
    <textarea id="ah-notes-editor" maxlength="${MAX_NOTES_CHARS}" spellcheck="true" placeholder="Write notes about this audit…">${esc(value)}</textarea>
    <div class="ah-notes-footer">
      <div><strong id="ah-notes-status">${esc(notesState.error || (dirty ? "Unsaved changes" : formatTimestamp(notesState.serverUpdatedAt)))}</strong><small><span id="ah-notes-count">${value.length.toLocaleString()}</span> / ${MAX_NOTES_CHARS.toLocaleString()} characters · plain text</small></div>
      <button id="ah-notes-save" type="button" ${dirty ? "" : "disabled"}>Save notes</button>
    </div>
  </section>`;
  bindNotesEditor(root, auditId);
}

function updateEditorState(root, auditId) {
  const editor = root.querySelector("#ah-notes-editor");
  const status = root.querySelector("#ah-notes-status");
  const count = root.querySelector("#ah-notes-count");
  const save = root.querySelector("#ah-notes-save");
  if (!editor || !status || !count || !save) return;
  const dirty = editor.value !== notesState.serverText;
  count.textContent = editor.value.length.toLocaleString();
  status.textContent = notesState.error || (dirty ? "Unsaved changes" : formatTimestamp(notesState.serverUpdatedAt));
  save.disabled = !dirty || notesState.saving;
  save.textContent = notesState.saving ? "Saving…" : "Save notes";
  if (dirty) writeDraft(auditId, editor.value);
  else clearDraft(auditId);
}

function bindNotesEditor(root, auditId) {
  const editor = root.querySelector("#ah-notes-editor");
  const save = root.querySelector("#ah-notes-save");
  if (!editor || !save) return;
  editor.addEventListener("input", () => {
    notesState.error = "";
    root.querySelector(".ah-notes-error")?.remove();
    updateEditorState(root, auditId);
  });
  editor.addEventListener("keydown", (event) => {
    if ((event.metaKey || event.ctrlKey) && event.key.toLowerCase() === "s") {
      event.preventDefault();
      saveNotes(root, auditId);
    }
  });
  save.addEventListener("click", () => saveNotes(root, auditId));
}

async function loadNotes(root, auditId) {
  if (!auditId || notesState.loading) return;
  const token = ++notesState.requestToken;
  notesState.loading = true;
  notesState.error = "";
  renderNotesSurface(root);
  try {
    const response = await fetch(`/api/v1/audits/${encodeURIComponent(auditId)}`, {
      headers: { Accept: "application/json" },
    });
    if (!response.ok) throw new Error(`${response.status} ${response.statusText}`);
    const audit = await response.json();
    if (token !== notesState.requestToken || auditId !== activeAuditId()) return;
    notesState.loadedAuditId = auditId;
    notesState.serverText = typeof audit.notes === "string" ? audit.notes : "";
    notesState.serverUpdatedAt = audit.notes_updated_at || null;
    const draft = readDraft(auditId);
    if (draft !== null && draft === notesState.serverText) clearDraft(auditId);
  } catch (error) {
    notesState.error = `Unable to load notes: ${error.message}`;
  } finally {
    if (token === notesState.requestToken) notesState.loading = false;
    const fresh = auditRoot();
    if (fresh && notesState.active && activeAuditId(fresh) === auditId) renderNotesSurface(fresh);
  }
}

async function saveNotes(root, auditId) {
  const editor = root.querySelector("#ah-notes-editor");
  if (!editor || notesState.saving || !auditId) return;
  const content = editor.value;
  if (content.length > MAX_NOTES_CHARS) return;
  notesState.saving = true;
  notesState.error = "";
  updateEditorState(root, auditId);
  try {
    const response = await fetch(`/api/v1/audits/${encodeURIComponent(auditId)}/notes`, {
      method: "POST",
      headers: { "Content-Type": "application/json", Accept: "application/json" },
      body: JSON.stringify({ content }),
    });
    if (!response.ok) {
      const payload = await response.json().catch(() => ({}));
      throw new Error(payload.detail || `${response.status} ${response.statusText}`);
    }
    const saved = await response.json();
    notesState.serverText = typeof saved.notes === "string" ? saved.notes : content;
    notesState.serverUpdatedAt = saved.notes_updated_at || null;
    clearDraft(auditId);
  } catch (error) {
    notesState.error = `Save failed: ${error.message}`;
  } finally {
    notesState.saving = false;
    const fresh = auditRoot();
    if (fresh && notesState.active && activeAuditId(fresh) === auditId) {
      if (notesState.error) renderNotesSurface(fresh);
      else updateEditorState(fresh, auditId);
    }
  }
}

function openNotes(root = auditRoot()) {
  const auditId = activeAuditId(root);
  if (!root || !auditId) return;
  notesState.auditId = auditId;
  notesState.active = true;
  notesState.error = "";
  saveSessionPatch(auditId, { tab: "notes" });
  renderNotesSurface(root);
  if (notesState.loadedAuditId !== auditId) loadNotes(root, auditId);
}

function deactivateNotes() {
  notesState.active = false;
}

function enhance() {
  const root = auditRoot();
  if (!root) {
    notesState.auditId = "";
    notesState.active = false;
    return;
  }
  const auditId = activeAuditId(root);
  ensureNotesTab(root);
  ensureAuditExit(root);
  const session = readSession(auditId);
  if (session.tab !== "notes" && notesState.active && notesState.auditId === auditId) {
    deactivateNotes();
  }
  if (session.tab === "notes") {
    if (!notesState.active || notesState.auditId !== auditId) {
      notesState.auditId = auditId;
      notesState.active = true;
    }
    if (!root.querySelector("[data-ah-notes-pane]") && !notesState.loading) {
      renderNotesSurface(root);
      if (notesState.loadedAuditId !== auditId) loadNotes(root, auditId);
    }
  }
}

const observer = new MutationObserver(() => queueMicrotask(enhance));
if (main) observer.observe(main, { childList: true });

document.addEventListener("click", (event) => {
  const root = auditRoot();
  if (!root || !notesState.active) return;
  const target = event.target;
  if (!(target instanceof Element)) return;
  if (target.closest("[data-ah-notes-tab], .ah-notes-pane")) return;
  if (target.closest("[data-ah-run]")) {
    deactivateNotes();
    root.querySelector("[data-ah-tab='source']")?.click();
    return;
  }
  if (target.closest("[data-ah-tab], [data-ah-page], [data-ah-nav]")) {
    deactivateNotes();
  }
}, true);

enhance();
