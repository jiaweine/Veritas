const main = document.querySelector("#main-content");
const sidebarGroups = document.querySelector(".nav-groups");

const ACTIVE_PROJECT_KEY = "veritas:projects:active:v1";
const UNASSIGNED = "__unassigned__";

const projectState = {
  snapshot: null,
  loading: false,
  error: "",
  queued: false,
  requestToken: 0,
  dialogAuditId: "",
  activeProjectId: readActiveProject(),
};

const esc = (value = "") => String(value)
  .replaceAll("&", "&amp;")
  .replaceAll("<", "&lt;")
  .replaceAll(">", "&gt;")
  .replaceAll('"', "&quot;")
  .replaceAll("'", "&#039;");

function readActiveProject() {
  try { return localStorage.getItem(ACTIVE_PROJECT_KEY) || ""; } catch { return ""; }
}

function writeActiveProject(projectId) {
  projectState.activeProjectId = projectId || "";
  try {
    if (projectState.activeProjectId) localStorage.setItem(ACTIVE_PROJECT_KEY, projectState.activeProjectId);
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

function projects() {
  return Array.isArray(projectState.snapshot?.projects) ? projectState.snapshot.projects : [];
}

function assignments() {
  const value = projectState.snapshot?.assignments;
  return value && typeof value === "object" ? value : {};
}

function unassignedAuditIds() {
  return Array.isArray(projectState.snapshot?.unassigned_audit_ids)
    ? projectState.snapshot.unassigned_audit_ids
    : [];
}

function projectById(projectId) {
  return projects().find((project) => project.project_id === projectId) || null;
}

function allKnownAuditIds() {
  const ids = new Set(unassignedAuditIds());
  projects().forEach((project) => (project.audit_ids || []).forEach((auditId) => ids.add(auditId)));
  return ids;
}

function projectSignature() {
  return projects().map((project) => project.project_id).join(",");
}

function activeProjectLabel() {
  if (projectState.activeProjectId === UNASSIGNED) return "Unassigned";
  return projectById(projectState.activeProjectId)?.name || "";
}

function projectAuditIds(projectId = projectState.activeProjectId) {
  if (!projectId) return null;
  if (projectId === UNASSIGNED) return new Set(unassignedAuditIds());
  const project = projectById(projectId);
  return project ? new Set(project.audit_ids || []) : new Set();
}

function normalizeActiveProject() {
  const active = projectState.activeProjectId;
  if (!active) return;
  if (active === UNASSIGNED) return;
  if (!projectById(active)) writeActiveProject("");
}

async function refreshProjects() {
  if (projectState.loading) return;
  projectState.loading = true;
  projectState.error = "";
  const token = ++projectState.requestToken;
  try {
    const snapshot = await requestJson("/api/v1/projects");
    if (token !== projectState.requestToken) return;
    projectState.snapshot = snapshot;
    normalizeActiveProject();
  } catch (error) {
    if (token === projectState.requestToken) projectState.error = error.message;
  } finally {
    if (token === projectState.requestToken) projectState.loading = false;
    queueEnhance();
  }
}

function ensureProjectDialog() {
  let dialog = document.querySelector("#project-create-dialog");
  if (dialog) return dialog;
  dialog = document.createElement("dialog");
  dialog.id = "project-create-dialog";
  dialog.className = "pw-dialog";
  dialog.innerHTML = `<form method="dialog" data-pw-form>
    <div class="pw-dialog-head"><div><span>Workspace organizer</span><strong>Create project</strong></div><button type="button" data-pw-close aria-label="Close">×</button></div>
    <p>Projects group papers for navigation only. They do not modify evidence, detector results, notes, provenance, or replication artifacts.</p>
    <label><span>Project name</span><input data-pw-name maxlength="80" autocomplete="off" placeholder="e.g. Minimum wage literature" /></label>
    <div class="pw-dialog-error" data-pw-error hidden></div>
    <div class="pw-dialog-actions"><button type="button" data-pw-cancel>Cancel</button><button class="primary" type="submit" data-pw-submit>Create project</button></div>
  </form>`;
  document.body.append(dialog);
  dialog.querySelector("[data-pw-close]")?.addEventListener("click", () => dialog.close());
  dialog.querySelector("[data-pw-cancel]")?.addEventListener("click", () => dialog.close());
  dialog.querySelector("[data-pw-form]")?.addEventListener("submit", submitProjectDialog);
  dialog.addEventListener("close", () => {
    projectState.dialogAuditId = "";
    const error = dialog.querySelector("[data-pw-error]");
    if (error) { error.hidden = true; error.textContent = ""; }
  });
  return dialog;
}

function openProjectDialog(auditId = "") {
  const dialog = ensureProjectDialog();
  projectState.dialogAuditId = auditId;
  const input = dialog.querySelector("[data-pw-name]");
  if (input) input.value = "";
  if (!dialog.open) dialog.showModal();
  setTimeout(() => input?.focus(), 30);
}

async function submitProjectDialog(event) {
  event.preventDefault();
  const dialog = event.currentTarget.closest("dialog");
  const input = dialog?.querySelector("[data-pw-name]");
  const submit = dialog?.querySelector("[data-pw-submit]");
  const errorNode = dialog?.querySelector("[data-pw-error]");
  const name = input?.value.trim() || "";
  const targetAuditId = projectState.dialogAuditId;
  if (!name || !dialog || !submit || !errorNode) return;
  submit.disabled = true;
  errorNode.hidden = true;
  try {
    const project = await requestJson("/api/v1/projects", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ name }),
    });
    if (targetAuditId) {
      await assignAudit(targetAuditId, project.project_id, { refresh: false });
    } else {
      writeActiveProject(project.project_id);
    }
    dialog.close();
    await refreshProjects();
    if (!targetAuditId) openActiveProjectInAudits();
  } catch (error) {
    errorNode.textContent = error.message;
    errorNode.hidden = false;
  } finally {
    submit.disabled = false;
  }
}

function projectNavMarkup() {
  if (projectState.error) {
    return `<div class="pw-nav-message"><span>Projects unavailable</span><button type="button" data-pw-retry>Retry</button></div>`;
  }
  if (!projectState.snapshot) {
    return `<div class="pw-nav-message">${projectState.loading ? "Loading projects…" : "No project metadata yet."}</div>`;
  }
  const rows = projects().map((project) => `<button type="button" class="nav-item pw-project-nav ${projectState.activeProjectId === project.project_id ? "active" : ""}" data-pw-open="${esc(project.project_id)}"><span class="nav-icon">▱</span><span class="pw-project-nav-name">${esc(project.name)}</span><span class="nav-count">${Number(project.audit_count) || 0}</span></button>`).join("");
  const unassignedCount = unassignedAuditIds().length;
  return `${rows || `<div class="pw-nav-message">Create a project to group related audits.</div>`}
    ${unassignedCount ? `<button type="button" class="nav-item pw-project-nav ${projectState.activeProjectId === UNASSIGNED ? "active" : ""}" data-pw-open="${UNASSIGNED}"><span class="nav-icon">○</span><span class="pw-project-nav-name">Unassigned</span><span class="nav-count">${unassignedCount}</span></button>` : ""}`;
}

function ensureSidebarProjects() {
  if (!sidebarGroups) return;
  let group = sidebarGroups.querySelector("[data-pw-project-group]");
  if (!group) {
    group = document.createElement("div");
    group.className = "nav-group pw-project-group";
    group.dataset.pwProjectGroup = "true";
    const first = sidebarGroups.querySelector(".nav-group");
    if (first?.nextSibling) sidebarGroups.insertBefore(group, first.nextSibling);
    else sidebarGroups.append(group);
  }
  group.innerHTML = `<div class="nav-label pw-project-label"><span>Projects</span><button type="button" data-pw-create title="Create project" aria-label="Create project">＋</button></div><div class="pw-project-list">${projectNavMarkup()}</div>`;
  group.querySelector("[data-pw-create]")?.addEventListener("click", () => openProjectDialog());
  group.querySelector("[data-pw-retry]")?.addEventListener("click", refreshProjects);
  group.querySelectorAll("[data-pw-open]").forEach((button) => button.addEventListener("click", () => {
    writeActiveProject(button.dataset.pwOpen || "");
    openActiveProjectInAudits();
    queueEnhance();
  }));
}

function openActiveProjectInAudits() {
  const auditsNav = document.querySelector(".sidebar [data-view='audits']");
  if (auditsNav) auditsNav.click();
}

async function assignAudit(auditId, projectId, { refresh = true } = {}) {
  const result = await requestJson(`/api/v1/audits/${encodeURIComponent(auditId)}/project`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ project_id: projectId || null }),
  });
  if (refresh) await refreshProjects();
  return result;
}

function projectSelectorMarkup(auditId) {
  const assigned = assignments()[auditId] || "";
  const options = projects().map((project) => `<option value="${esc(project.project_id)}" ${assigned === project.project_id ? "selected" : ""}>${esc(project.name)}</option>`).join("");
  return `<section class="ah-rail-section pw-audit-project" data-pw-audit-project data-pw-project-signature="${esc(projectSignature())}">
    <div class="ah-section-head"><span>Project</span><button type="button" data-pw-new-for-audit="${esc(auditId)}">＋ New</button></div>
    <select data-pw-assignment="${esc(auditId)}" aria-label="Project for this audit"><option value="">Unassigned</option>${options}</select>
    <small>Organization only · excluded from audit evidence and provenance.</small>
    <div class="pw-assignment-status" data-pw-assignment-status></div>
  </section>`;
}

function enhanceAuditProject() {
  const root = main?.querySelector("[data-audit-harness='true']");
  if (!root || !projectState.snapshot) return;
  const auditId = root.dataset.auditId || "";
  if (!auditId) return;
  if (!allKnownAuditIds().has(auditId) && !projectState.loading) {
    refreshProjects();
    return;
  }
  const rail = root.querySelector(".ah-left");
  if (!rail) return;
  let section = rail.querySelector("[data-pw-audit-project]");
  const expected = assignments()[auditId] || "";
  const signature = projectSignature();
  const needsRefresh = !section
    || section.querySelector("select")?.dataset.value !== expected
    || section.dataset.pwProjectSignature !== signature;
  if (needsRefresh) {
    section?.remove();
    rail.insertAdjacentHTML("afterbegin", projectSelectorMarkup(auditId));
    section = rail.querySelector("[data-pw-audit-project]");
    const select = section?.querySelector("[data-pw-assignment]");
    if (select) {
      select.dataset.value = expected;
      select.addEventListener("change", async () => {
        const status = section.querySelector("[data-pw-assignment-status]");
        select.disabled = true;
        if (status) status.textContent = "Saving…";
        try {
          await assignAudit(auditId, select.value || null);
          if (status) status.textContent = "Saved";
        } catch (error) {
          if (status) status.textContent = error.message;
          select.value = assignments()[auditId] || "";
        } finally {
          select.disabled = false;
        }
      });
    }
    section?.querySelector("[data-pw-new-for-audit]")?.addEventListener("click", () => openProjectDialog(auditId));
  }
}

function clearProjectFilter() {
  writeActiveProject("");
  queueEnhance();
}

function enhanceAuditTableLabels(rows) {
  rows.forEach((row) => {
    const auditId = row.dataset.auditId || "";
    const project = projectById(assignments()[auditId]);
    const cell = row.querySelector("td:first-child");
    const existing = cell?.querySelector("[data-pw-row-project]");
    if (!project) {
      existing?.remove();
      return;
    }
    if (existing) {
      existing.textContent = project.name;
      return;
    }
    const badge = document.createElement("span");
    badge.dataset.pwRowProject = "true";
    badge.className = "pw-row-project";
    badge.textContent = project.name;
    cell?.append(badge);
  });
}

function enhanceAuditListFilter() {
  if (!main || !projectState.snapshot) return;
  const title = main.querySelector(".page-title")?.textContent?.trim();
  if (title !== "Audits") return;
  const rows = [...main.querySelectorAll("table.data-table tbody tr[data-audit-id]")];
  const known = allKnownAuditIds();
  if (rows.some((row) => !known.has(row.dataset.auditId || "")) && !projectState.loading) {
    refreshProjects();
  }
  enhanceAuditTableLabels(rows);

  let banner = main.querySelector("[data-pw-filter-banner]");
  let empty = main.querySelector("[data-pw-filter-empty]");
  if (!projectState.activeProjectId) {
    rows.forEach((row) => { row.hidden = false; });
    banner?.remove();
    empty?.remove();
    return;
  }
  const allowed = projectAuditIds();
  const label = activeProjectLabel();
  if (!label) {
    clearProjectFilter();
    return;
  }
  let visible = 0;
  rows.forEach((row) => {
    const show = allowed?.has(row.dataset.auditId || "") || false;
    row.hidden = !show;
    if (show) visible += 1;
  });

  const pageHead = main.querySelector(".page-head");
  if (!banner && pageHead) {
    pageHead.insertAdjacentHTML("afterend", `<div class="pw-filter-banner" data-pw-filter-banner><div><span>Project</span><strong>${esc(label)}</strong><small data-pw-filter-count></small></div><button type="button" data-pw-clear-filter>Show all audits</button></div>`);
    banner = main.querySelector("[data-pw-filter-banner]");
    banner?.querySelector("[data-pw-clear-filter]")?.addEventListener("click", clearProjectFilter);
  }
  if (banner) {
    const strong = banner.querySelector("strong");
    const count = banner.querySelector("[data-pw-filter-count]");
    if (strong) strong.textContent = label;
    if (count) count.textContent = `${visible} paper${visible === 1 ? "" : "s"}`;
  }

  const panel = main.querySelector("section.panel");
  if (!visible && panel && !empty) {
    panel.insertAdjacentHTML("beforeend", `<div class="pw-filter-empty" data-pw-filter-empty><span>▱</span><strong>No papers in ${esc(label)}</strong><p>Open an audit and assign it from the Project control in the left rail.</p></div>`);
  } else if (visible) {
    empty?.remove();
  }
}

function enhance() {
  projectState.queued = false;
  ensureSidebarProjects();
  enhanceAuditProject();
  enhanceAuditListFilter();
}

function queueEnhance() {
  if (projectState.queued) return;
  projectState.queued = true;
  queueMicrotask(enhance);
}

const observer = new MutationObserver(queueEnhance);
if (main) observer.observe(main, { childList: true, subtree: true });
window.addEventListener("hashchange", queueEnhance);

ensureProjectDialog();
refreshProjects();
queueEnhance();
