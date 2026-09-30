const sidebar = document.querySelector("#sidebar");
const main = document.querySelector("#main-content");

const ACTIVE_PROJECT_KEY = "veritas:projects:active:v1";
const UNASSIGNED = "__unassigned__";

const refProjectState = {
  snapshot: null,
  loading: false,
  queued: false,
  requestToken: 0,
};

const esc = (value = "") => String(value)
  .replaceAll("&", "&amp;")
  .replaceAll("<", "&lt;")
  .replaceAll(">", "&gt;")
  .replaceAll('"', "&quot;")
  .replaceAll("'", "&#039;");

function activeAuditId() {
  return main?.querySelector("[data-audit-harness='true']")?.dataset.auditId || "";
}

function projects() {
  return Array.isArray(refProjectState.snapshot?.projects) ? refProjectState.snapshot.projects : [];
}

function assignments() {
  const value = refProjectState.snapshot?.assignments;
  return value && typeof value === "object" ? value : {};
}

function unassignedAuditIds() {
  return Array.isArray(refProjectState.snapshot?.unassigned_audit_ids)
    ? refProjectState.snapshot.unassigned_audit_ids
    : [];
}

function activeProjectId() {
  try { return localStorage.getItem(ACTIVE_PROJECT_KEY) || ""; } catch { return ""; }
}

function setActiveProject(projectId) {
  try {
    if (projectId) localStorage.setItem(ACTIVE_PROJECT_KEY, projectId);
    else localStorage.removeItem(ACTIVE_PROJECT_KEY);
  } catch {}
}

async function requestJson(path, options = {}) {
  const { headers: optionHeaders = {}, ...rest } = options;
  const response = await fetch(path, {
    ...rest,
    headers: { Accept: "application/json", ...optionHeaders },
  });
  if (!response.ok) {
    let detail = `${response.status} ${response.statusText}`;
    try { detail = (await response.json()).detail || detail; } catch {}
    throw new Error(detail);
  }
  return response.json();
}

async function refreshProjects() {
  if (refProjectState.loading) return;
  refProjectState.loading = true;
  const token = ++refProjectState.requestToken;
  try {
    const snapshot = await requestJson("/api/v1/projects");
    if (token !== refProjectState.requestToken) return;
    refProjectState.snapshot = snapshot;
  } catch (error) {
    console.error("Unable to hydrate reference project navigation", error);
  } finally {
    if (token === refProjectState.requestToken) refProjectState.loading = false;
    queueEnhance();
  }
}

function projectRows() {
  const active = activeProjectId();
  const rows = projects().map((project) => `<button class="ref-sidebar-link pw-ref-project-link ${active === project.project_id ? "active" : ""}" type="button" data-pw-ref-open="${esc(project.project_id)}"><span>▱</span><strong>${esc(project.name)}</strong><em>${Number(project.audit_count) || 0}</em></button>`).join("");
  const unassignedCount = unassignedAuditIds().length;
  return `${rows || `<div class="ref-sidebar-empty">No projects yet.</div>`}${unassignedCount ? `<button class="ref-sidebar-link pw-ref-project-link ${active === UNASSIGNED ? "active" : ""}" type="button" data-pw-ref-open="${UNASSIGNED}"><span>○</span><strong>Unassigned</strong><em>${unassignedCount}</em></button>` : ""}`;
}

function assignmentControl(auditId) {
  const current = assignments()[auditId] || "";
  const options = projects().map((project) => `<option value="${esc(project.project_id)}" ${current === project.project_id ? "selected" : ""}>${esc(project.name)}</option>`).join("");
  return `<div class="pw-ref-current">
    <div><span>Current paper</span><small>Organization only · outside evidence provenance</small></div>
    <select data-pw-ref-assignment="${esc(auditId)}" aria-label="Project for current audit"><option value="">Unassigned</option>${options}</select>
    <span class="pw-ref-status" data-pw-ref-status></span>
  </div>`;
}

function openProject(projectId) {
  setActiveProject(projectId);
  document.body.classList.remove("reference-audit-active");
  const auditsNavigation = document.querySelector("#sidebar [data-view='audits']");
  if (auditsNavigation) {
    auditsNavigation.click();
    return;
  }
  window.location.assign("/#audits");
}

async function assignCurrentAudit(select) {
  const auditId = select.dataset.pwRefAssignment || "";
  if (!auditId) return;
  const status = select.closest(".pw-ref-current")?.querySelector("[data-pw-ref-status]");
  select.disabled = true;
  if (status) status.textContent = "Saving…";
  try {
    await requestJson(`/api/v1/audits/${encodeURIComponent(auditId)}/project`, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ project_id: select.value || null }),
    });
    if (status) status.textContent = "Saved";
    await refreshProjects();
  } catch (error) {
    if (status) status.textContent = error.message;
  } finally {
    select.disabled = false;
  }
}

function ensureReferenceProjects() {
  const shell = sidebar?.querySelector("[data-reference-sidebar]");
  const auditId = activeAuditId();
  if (!shell || !auditId || !refProjectState.snapshot) return;

  const signature = `${projects().map((project) => `${project.project_id}:${project.audit_count}`).join("|")}|${assignments()[auditId] || ""}|${activeProjectId()}`;
  let section = shell.querySelector("[data-pw-reference-projects]");
  if (section?.dataset.pwSignature === signature) return;
  section?.remove();
  section = document.createElement("section");
  section.className = "ref-sidebar-group pw-ref-projects";
  section.dataset.pwReferenceProjects = "true";
  section.dataset.pwSignature = signature;
  section.innerHTML = `<div class="ref-sidebar-heading"><span>Projects</span><button type="button" data-pw-ref-create>＋ New</button></div><div class="pw-ref-project-list">${projectRows()}</div>${assignmentControl(auditId)}`;

  const workspace = shell.querySelector(".ref-sidebar-group");
  if (workspace?.nextSibling) shell.insertBefore(section, workspace.nextSibling);
  else shell.append(section);

  section.querySelector("[data-pw-ref-create]")?.addEventListener("click", () => {
    const globalCreate = document.querySelector("[data-pw-project-group] [data-pw-create]");
    if (globalCreate) globalCreate.click();
  });
  section.querySelectorAll("[data-pw-ref-open]").forEach((button) => button.addEventListener("click", () => openProject(button.dataset.pwRefOpen || "")));
  const select = section.querySelector("[data-pw-ref-assignment]");
  select?.addEventListener("change", () => assignCurrentAudit(select));
}

function bindProjectDialogRefresh() {
  const dialog = document.querySelector("#project-create-dialog");
  if (!dialog || dialog.dataset.pwReferenceBound === "true") return;
  dialog.dataset.pwReferenceBound = "true";
  dialog.addEventListener("close", refreshProjects);
}

function enhance() {
  refProjectState.queued = false;
  bindProjectDialogRefresh();
  ensureReferenceProjects();
}

function queueEnhance() {
  if (refProjectState.queued) return;
  refProjectState.queued = true;
  queueMicrotask(enhance);
}

const mainObserver = new MutationObserver(queueEnhance);
if (main) mainObserver.observe(main, { childList: true, subtree: true });
const sidebarObserver = new MutationObserver(queueEnhance);
if (sidebar) sidebarObserver.observe(sidebar, { childList: true, subtree: true });
window.addEventListener("hashchange", queueEnhance);

refreshProjects();
queueEnhance();
