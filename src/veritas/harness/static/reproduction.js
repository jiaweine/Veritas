const main = document.querySelector("#main-content");

const escapeHtml = (value = "") => String(value)
  .replaceAll("&", "&amp;")
  .replaceAll("<", "&lt;")
  .replaceAll(">", "&gt;")
  .replaceAll('"', "&quot;")
  .replaceAll("'", "&#039;");

async function getJson(path) {
  const response = await fetch(path, { headers: { Accept: "application/json" } });
  if (!response.ok) {
    let detail = `${response.status} ${response.statusText}`;
    try { detail = (await response.json()).detail || detail; } catch {}
    throw new Error(detail);
  }
  return response.json();
}

function badge(status, text = status) {
  const normalized = String(status || "info").replaceAll("_", "-");
  return `<span class="badge ${escapeHtml(normalized)}">${escapeHtml(text)}</span>`;
}

function traceSymbol(event) {
  const agentKind = event.payload?.agent_event?.kind || "";
  const title = String(event.title || "").toLowerCase();
  if (agentKind === "permission") return "◆";
  if (title.includes("terminal")) return ">_";
  if (title.includes("tool_call") || title.includes("tool call")) return "⌁";
  if (event.kind === "tool") return "⌁";
  if (event.kind === "replication") return "↻";
  return "·";
}

function traceRow(event) {
  const status = event.status || "info";
  const kind = event.kind || "event";
  const payload = event.payload || {};
  const phase = payload.phase ? ` · ${payload.phase}` : "";
  const duration = payload.duration_ms != null ? ` · ${Number(payload.duration_ms).toFixed(0)} ms` : "";
  return `<div class="status-row">
    <span class="status-icon ${escapeHtml(status)}">${escapeHtml(traceSymbol(event))}</span>
    <div class="status-copy">
      <strong>${escapeHtml(event.title || "Replication event")}</strong>
      <small>${escapeHtml(kind)}${escapeHtml(phase)}${escapeHtml(duration)}${event.detail ? ` · ${escapeHtml(event.detail)}` : ""}</small>
    </div>
    ${badge(status)}
  </div>`;
}

function formatBytes(value) {
  const bytes = Number(value) || 0;
  if (bytes < 1024) return `${bytes} B`;
  if (bytes < 1024 * 1024) return `${(bytes / 1024).toFixed(bytes < 10 * 1024 ? 1 : 0)} KiB`;
  return `${(bytes / 1024 / 1024).toFixed(bytes < 10 * 1024 * 1024 ? 1 : 0)} MiB`;
}

function lockControls(controls) {
  const snapshot = controls.filter(Boolean).map((control) => [control, control.disabled]);
  snapshot.forEach(([control]) => { control.disabled = true; });
  return () => snapshot.forEach(([control, disabled]) => { control.disabled = disabled; });
}

function renderArtifacts(items, auditId) {
  if (!items.length) {
    return `<div class="artifact-empty"><strong>No attached artifacts</strong><small>Add code, data, environment files, or an archive. Veritas stores the original bytes immutably and does not unpack or execute them in the web process.</small></div>`;
  }
  return items.map((item) => `<div class="artifact-row">
    <span class="artifact-icon">◇</span>
    <div class="artifact-copy">
      <strong>${escapeHtml(item.filename || item.attachment_id)}</strong>
      <small>${formatBytes(item.size_bytes)} · <span class="mono">sha256:${escapeHtml(String(item.sha256 || "").slice(0, 16))}…</span></small>
    </div>
    <a class="artifact-download" href="/api/v1/audits/${encodeURIComponent(auditId)}/attachments/${encodeURIComponent(item.attachment_id)}" download>Download</a>
  </div>`).join("");
}

async function loadArtifacts(auditId, listNode, countNode) {
  if (!auditId || !listNode) return [];
  listNode.innerHTML = `<div class="artifact-empty"><small>Loading immutable artifact manifest…</small></div>`;
  try {
    const items = await getJson(`/api/v1/audits/${encodeURIComponent(auditId)}/attachments`);
    listNode.innerHTML = renderArtifacts(items, auditId);
    if (countNode) countNode.textContent = `${items.length} attached`;
    return items;
  } catch (error) {
    listNode.innerHTML = `<div class="artifact-empty danger"><strong>Artifact manifest unavailable</strong><small>${escapeHtml(error.message)}</small></div>`;
    if (countNode) countNode.textContent = "unavailable";
    return [];
  }
}

async function uploadArtifacts(auditId, files, listNode, countNode, button, maxBytes, locks = []) {
  const selected = [...files];
  if (!auditId || !selected.length) return;
  const oversized = selected.find((file) => file.size > maxBytes);
  if (oversized) {
    throw new Error(`${oversized.name} exceeds the ${formatBytes(maxBytes)} per-file limit.`);
  }

  const unlock = lockControls([button, ...locks]);
  const original = button.textContent;
  try {
    for (let index = 0; index < selected.length; index += 1) {
      button.textContent = `Uploading ${index + 1}/${selected.length}…`;
      const body = new FormData();
      body.append("file", selected[index], selected[index].name);
      const response = await fetch(`/api/v1/audits/${encodeURIComponent(auditId)}/attachments`, {
        method: "POST",
        body,
      });
      if (!response.ok) {
        let detail = `${response.status} ${response.statusText}`;
        try { detail = (await response.json()).detail || detail; } catch {}
        throw new Error(detail);
      }
    }
    await loadArtifacts(auditId, listNode, countNode);
  } finally {
    unlock();
    button.textContent = original;
  }
}

function workspaceBadge(status) {
  const labels = {
    staged_unchanged: ["success", "staged · unchanged"],
    staged_modified: ["danger", "staged · modified"],
    staged_deleted: ["danger", "staged · deleted"],
    created: ["info", "created"],
    created_symlink: ["review", "symlink"],
    created_other: ["review", "other"],
  };
  const [tone, label] = labels[status] || ["info", status || "file"];
  return badge(tone, label);
}

function renderWorkspace(snapshot) {
  const summary = snapshot.summary || {};
  const files = snapshot.files || [];
  const integrityTone = snapshot.integrity_ok ? "success" : "danger";
  const integrityTitle = snapshot.integrity_ok ? "Staged inputs unchanged" : "Staged input integrity breach";
  const fileRows = files.length ? files.map((item) => {
    const previewablePath = item.exists && item.kind === "file";
    const sha = item.sha256 ? ` · sha256:${escapeHtml(String(item.sha256).slice(0, 12))}…` : "";
    const size = item.size_bytes == null ? "missing" : formatBytes(item.size_bytes);
    return `<button class="workspace-file-row${previewablePath ? " previewable" : ""}" type="button" data-workspace-path="${escapeHtml(item.path)}" ${previewablePath ? "" : "disabled"}>
      <span class="workspace-file-icon">${item.kind === "symlink" ? "↗" : item.exists ? "◇" : "×"}</span>
      <span class="workspace-file-copy"><strong>${escapeHtml(item.path)}</strong><small>${escapeHtml(size)}${sha}${item.hash_computed === false && item.exists && item.kind === "file" ? " · hash omitted by inspection bound" : ""}</small></span>
      ${workspaceBadge(item.status)}
    </button>`;
  }).join("") : `<div class="artifact-empty"><strong>No workspace files</strong><small>The run workspace contains no inspectable entries.</small></div>`;

  return `<div class="workspace-integrity ${integrityTone}">
      <div><strong>${integrityTitle}</strong><small>Integrity scope: Veritas-staged paper, attachments, and artifacts.json only. This is not a sandbox or a correctness verdict.</small></div>
      ${badge(integrityTone, snapshot.integrity_ok ? "integrity ok" : "review required")}
    </div>
    <div class="workspace-summary">
      <div><span>Created files</span><strong>${Number(summary.created_files || 0)}</strong></div>
      <div><span>Staged unchanged</span><strong>${Number(summary.staged_unchanged || 0)}</strong></div>
      <div><span>Staged modified</span><strong>${Number(summary.staged_modified || 0)}</strong></div>
      <div><span>Staged deleted</span><strong>${Number(summary.staged_deleted || 0)}</strong></div>
      <div><span>Symlinks</span><strong>${Number(summary.symlinks || 0)}</strong></div>
    </div>
    <div class="workspace-grid">
      <div class="workspace-files">
        <div class="workspace-subhead"><strong>Run files</strong><small>${escapeHtml(snapshot.run_id)}</small></div>
        <div class="workspace-file-list">${fileRows}</div>
      </div>
      <div class="workspace-preview">
        <div class="workspace-subhead"><strong>Read-only preview</strong><small>UTF-8 · first 256 KiB</small></div>
        <div id="workspace-preview-body" class="workspace-preview-body"><div class="artifact-empty"><strong>Select a file</strong><small>Generated outputs are untrusted until reviewed. Symlinks are never followed.</small></div></div>
      </div>
    </div>
    <p class="reproduction-helper">${escapeHtml(snapshot.note || "")}</p>`;
}

async function previewWorkspaceFile(auditId, runId, path, previewNode) {
  previewNode.innerHTML = `<div class="artifact-empty"><small>Loading bounded file preview…</small></div>`;
  try {
    const params = new URLSearchParams({ path });
    const value = await getJson(`/api/v1/audits/${encodeURIComponent(auditId)}/replication-runs/${encodeURIComponent(runId)}/workspace/file?${params}`);
    if (!value.previewable) {
      previewNode.innerHTML = `<div class="artifact-empty"><strong>Preview unavailable</strong><small>${escapeHtml(value.reason || "This file is not UTF-8 text.")} · ${formatBytes(value.size_bytes)}</small></div>`;
      return;
    }
    previewNode.innerHTML = `<div class="workspace-preview-meta"><strong>${escapeHtml(value.path)}</strong><small>${formatBytes(value.size_bytes)}${value.truncated ? " · preview truncated" : " · complete"}</small></div><pre>${escapeHtml(value.content || "")}</pre>`;
  } catch (error) {
    previewNode.innerHTML = `<div class="artifact-empty danger"><strong>Preview failed</strong><small>${escapeHtml(error.message)}</small></div>`;
  }
}

async function loadWorkspace(auditId, runId, workspaceNode, runNode) {
  if (!workspaceNode || !runId) return;
  workspaceNode.innerHTML = `<div class="artifact-empty"><small>Inspecting run-scoped workspace without following symlinks…</small></div>`;
  if (runNode) runNode.textContent = runId;
  try {
    const snapshot = await getJson(`/api/v1/audits/${encodeURIComponent(auditId)}/replication-runs/${encodeURIComponent(runId)}/workspace`);
    workspaceNode.innerHTML = renderWorkspace(snapshot);
    const previewNode = workspaceNode.querySelector("#workspace-preview-body");
    workspaceNode.querySelectorAll(".workspace-file-row.previewable").forEach((row) => {
      row.addEventListener("click", async () => {
        workspaceNode.querySelectorAll(".workspace-file-row").forEach((item) => item.classList.remove("active"));
        row.classList.add("active");
        await previewWorkspaceFile(auditId, runId, row.dataset.workspacePath || "", previewNode);
      });
    });
    const firstCreated = workspaceNode.querySelector('.workspace-file-row.previewable .badge.info')?.closest(".workspace-file-row");
    const firstPreviewable = firstCreated || workspaceNode.querySelector(".workspace-file-row.previewable");
    if (firstPreviewable) firstPreviewable.click();
  } catch (error) {
    workspaceNode.innerHTML = `<div class="artifact-empty danger"><strong>Workspace inspection unavailable</strong><small>${escapeHtml(error.message)}</small></div>`;
  }
}

async function streamReplication(auditId, prompt, timeline, button, locks = []) {
  const unlock = lockControls([button, ...locks]);
  button.textContent = "Running…";
  timeline.innerHTML = `<div class="status-row"><span class="status-icon running">↻</span><div class="status-copy"><strong>Opening replication stream</strong><small>Waiting for structured ACP events…</small></div></div>`;
  let runId = null;
  try {
    const response = await fetch(`/api/v1/audits/${encodeURIComponent(auditId)}/replication`, {
      method: "POST",
      headers: { "Content-Type": "application/json", Accept: "application/x-ndjson" },
      body: JSON.stringify({ prompt }),
    });
    if (!response.ok) {
      let detail = `${response.status} ${response.statusText}`;
      try { detail = (await response.json()).detail || detail; } catch {}
      throw new Error(detail);
    }
    if (!response.body) throw new Error("Streaming response body is unavailable in this browser.");

    const reader = response.body.getReader();
    const decoder = new TextDecoder();
    let buffer = "";
    let rows = "";
    const appendEvent = (event) => {
      if (event?.payload?.run_id) runId = event.payload.run_id;
      rows += traceRow(event);
      timeline.innerHTML = rows;
      timeline.scrollTop = timeline.scrollHeight;
    };

    while (true) {
      const { value, done } = await reader.read();
      if (done) break;
      buffer += decoder.decode(value, { stream: true });
      const lines = buffer.split("\n");
      buffer = lines.pop() || "";
      for (const line of lines) {
        if (!line.trim()) continue;
        appendEvent(JSON.parse(line));
      }
    }
    if (buffer.trim()) appendEvent(JSON.parse(buffer));
  } catch (error) {
    timeline.innerHTML += `<div class="status-row"><span class="status-icon danger">!</span><div class="status-copy"><strong>Replication request failed</strong><small>${escapeHtml(error.message)}</small></div>${badge("danger", "error")}</div>`;
  } finally {
    unlock();
    button.textContent = "Run reproduction";
  }
  return runId;
}

async function enhanceReproduction() {
  if (!main || main.dataset.reproductionEnhanced === "true") return;
  if (!main.textContent.includes("Reproduction workflow")) return;
  main.dataset.reproductionEnhanced = "true";

  try {
    const [capabilities, audits] = await Promise.all([
      getJson("/api/v1/capabilities"),
      getJson("/api/v1/audits"),
    ]);
    const replication = capabilities.replication || {};
    const configured = Boolean(replication.configured);
    const maxAttachmentBytes = Number(capabilities.max_attachment_bytes || 80 * 1024 * 1024);
    const options = audits.map((audit) => `<option value="${escapeHtml(audit.audit_id)}">${escapeHtml(audit.title || audit.filename || audit.audit_id)}</option>`).join("");

    main.innerHTML = `<div class="page" data-reproduction-surface="true">
      <div class="page-head">
        <div class="page-head-copy">
          <span class="eyebrow">Reproducibility</span>
          <h1 class="page-title">Reproduction</h1>
          <p class="page-subtitle">Attach immutable research artifacts, run a server-configured ACP agent in a run-specific workspace, inspect structured execution, and review the exact post-run files without exposing arbitrary host paths.</p>
        </div>
        <div class="page-actions">${configured ? badge("success", "agent configured") : badge("review", "fail-closed")}</div>
      </div>

      <section class="content-row">
        <article class="panel">
          <div class="panel-head"><h2>Execution boundary</h2>${configured ? `<span class="panel-link">${escapeHtml(replication.agent || "ACP agent")}</span>` : ""}</div>
          <div class="panel-body">
            <div class="stat-list">
              <div class="stat-item"><span>Agent</span><strong>${escapeHtml(replication.agent || "Not configured")}</strong></div>
              <div class="stat-item"><span>Permission policy</span><strong>${escapeHtml(replication.permission_policy || "deny")}</strong></div>
              <div class="stat-item"><span>Client-supplied commands</span><strong>${replication.client_supplied_commands ? "Allowed" : "Disabled"}</strong></div>
              <div class="stat-item"><span>Workspace per run</span><strong>${replication.workspace_per_run ? "Yes" : "No"}</strong></div>
              <div class="stat-item"><span>Workspace security boundary</span><strong>${replication.workspace_is_security_boundary ? "Yes" : "Agent-owned"}</strong></div>
            </div>
            <p class="page-subtitle" style="margin:16px 0 0">Veritas stages read-only copies of the immutable paper and hash-verified attachments into a new workspace for each run. <span class="mono">audit.json</span> is not staged. The selected ACP agent remains responsible for its own execution sandbox.</p>
          </div>
        </article>

        <article class="panel">
          <div class="panel-head"><h2>Reproduction target</h2></div>
          <div class="panel-body">
            ${audits.length ? `
              <label class="field"><span>Paper</span><select id="replication-audit" class="secondary-button" style="width:100%;text-align:left">${options}</select></label>
              <label class="field" style="margin-top:14px"><span>Goal</span><textarea id="replication-prompt" rows="5" ${configured ? "" : "disabled"} placeholder="Reproduce the paper's main reported result and record the steps, environment, outputs, and discrepancies."></textarea></label>
              <button id="replication-run" class="primary-button" style="margin-top:14px" ${configured ? "" : "disabled"}>Run reproduction</button>
              ${configured ? "" : `<p class="reproduction-helper">Configure <span class="mono">VERITAS_REPLICATION_AGENT</span> on the server to enable execution. Artifact intake remains available.</p>`}
            ` : `<div class="empty-state" style="min-height:220px"><div class="empty-state-inner"><div class="empty-mark">↻</div><h2>No paper available</h2><p>Upload a paper before attaching reproduction artifacts or starting a run.</p></div></div>`}
          </div>
        </article>
      </section>

      ${audits.length ? `<section class="panel reproduction-artifacts">
        <div class="panel-head"><h2>Immutable reproduction artifacts</h2><span id="replication-artifact-count" class="panel-link">loading…</span></div>
        <div class="panel-body">
          <div class="artifact-toolbar">
            <div><strong>Code · data · environment</strong><small>Stored byte-for-byte with SHA256 provenance. Archives are not unpacked by the web process. Max ${formatBytes(maxAttachmentBytes)} per file.</small></div>
            <button id="replication-artifact-add" class="secondary-button">＋ Attach files</button>
            <input id="replication-artifact-input" type="file" multiple hidden />
          </div>
          <div id="replication-artifact-list" class="artifact-list"></div>
          <div id="replication-artifact-error" class="artifact-error" hidden></div>
        </div>
      </section>` : ""}

      <section class="panel">
        <div class="panel-head"><h2>Live replication trace</h2><span class="panel-link">NDJSON · persisted to audit history</span></div>
        <div id="replication-timeline" class="panel-body status-stack" style="max-height:480px;overflow:auto">
          <div class="status-row"><span class="status-icon">·</span><div class="status-copy"><strong>No replication run in this session</strong><small>Start a run to stream agent updates, tool permissions, terminal/tool activity, and completion state.</small></div></div>
        </div>
      </section>

      <section class="panel reproduction-workspace">
        <div class="panel-head"><h2>Run workspace</h2><span id="replication-workspace-run" class="panel-link">read-only · run scoped</span></div>
        <div id="replication-workspace" class="panel-body">
          <div class="artifact-empty"><strong>No run workspace selected</strong><small>After a run finishes or fails, Veritas will inspect that exact run directory, verify its staged inputs, and expose bounded read-only previews of regular files.</small></div>
        </div>
      </section>
    </div>`;

    const auditSelect = document.querySelector("#replication-audit");
    const promptInput = document.querySelector("#replication-prompt");
    const button = document.querySelector("#replication-run");
    const artifactList = document.querySelector("#replication-artifact-list");
    const artifactCount = document.querySelector("#replication-artifact-count");
    const artifactInput = document.querySelector("#replication-artifact-input");
    const artifactAdd = document.querySelector("#replication-artifact-add");
    const artifactError = document.querySelector("#replication-artifact-error");
    const workspaceNode = document.querySelector("#replication-workspace");
    const workspaceRun = document.querySelector("#replication-workspace-run");

    if (auditSelect && artifactList) {
      await loadArtifacts(auditSelect.value, artifactList, artifactCount);
      auditSelect.addEventListener("change", async () => {
        if (artifactError) { artifactError.hidden = true; artifactError.textContent = ""; }
        if (workspaceNode) workspaceNode.innerHTML = `<div class="artifact-empty"><strong>No run workspace selected</strong><small>Run the newly selected paper to inspect its run-scoped workspace.</small></div>`;
        if (workspaceRun) workspaceRun.textContent = "read-only · run scoped";
        await loadArtifacts(auditSelect.value, artifactList, artifactCount);
      });
    }

    if (artifactAdd && artifactInput) {
      artifactAdd.addEventListener("click", () => artifactInput.click());
      artifactInput.addEventListener("change", async () => {
        if (!auditSelect?.value || !artifactList || !artifactInput.files?.length) return;
        if (artifactError) { artifactError.hidden = true; artifactError.textContent = ""; }
        const targetAuditId = auditSelect.value;
        try {
          await uploadArtifacts(
            targetAuditId,
            artifactInput.files,
            artifactList,
            artifactCount,
            artifactAdd,
            maxAttachmentBytes,
            [auditSelect, button],
          );
        } catch (error) {
          if (artifactError) {
            artifactError.hidden = false;
            artifactError.textContent = error.message;
          }
        } finally {
          artifactInput.value = "";
        }
      });
    }

    if (button) {
      button.addEventListener("click", async () => {
        const auditId = auditSelect?.value;
        const prompt = promptInput?.value.trim();
        const timeline = document.querySelector("#replication-timeline");
        if (!auditId || !timeline) return;
        if (!prompt) {
          timeline.innerHTML = `<div class="status-row"><span class="status-icon review">!</span><div class="status-copy"><strong>Describe the reproduction goal</strong><small>The server accepts a goal/prompt, never a client-supplied executable command.</small></div>${badge("review")}</div>`;
          return;
        }
        if (workspaceNode) workspaceNode.innerHTML = `<div class="artifact-empty"><small>Waiting for the run workspace to close before inspection…</small></div>`;
        const runId = await streamReplication(
          auditId,
          prompt,
          timeline,
          button,
          [auditSelect, promptInput, artifactAdd, artifactInput],
        );
        if (runId && workspaceNode) {
          await loadWorkspace(auditId, runId, workspaceNode, workspaceRun);
        } else if (workspaceNode) {
          workspaceNode.innerHTML = `<div class="artifact-empty danger"><strong>No run id was persisted</strong><small>The replication request did not reach a run-scoped workspace.</small></div>`;
        }
      });
    }
  } catch (error) {
    main.innerHTML = `<div class="page"><div class="empty-state"><div class="empty-state-inner"><div class="empty-mark">!</div><h2>Reproduction surface unavailable</h2><p>${escapeHtml(error.message)}</p></div></div></div>`;
  }
}

const observer = new MutationObserver(() => {
  if (!main) return;
  if (!main.textContent.includes("Reproduction workflow")) {
    if (!main.querySelector("[data-reproduction-surface]")) delete main.dataset.reproductionEnhanced;
    return;
  }
  queueMicrotask(enhanceReproduction);
});

if (main) {
  observer.observe(main, { childList: true, subtree: true });
  queueMicrotask(enhanceReproduction);
}
