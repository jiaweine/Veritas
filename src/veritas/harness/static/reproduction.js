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

function traceRow(event) {
  const status = event.status || "info";
  const kind = event.kind || "event";
  const payload = event.payload || {};
  const phase = payload.phase ? ` · ${payload.phase}` : "";
  const duration = payload.duration_ms != null ? ` · ${Number(payload.duration_ms).toFixed(0)} ms` : "";
  return `<div class="status-row">
    <span class="status-icon ${escapeHtml(status)}">${kind === "tool" ? "⌁" : kind === "replication" ? "↻" : "·"}</span>
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

async function uploadArtifacts(auditId, files, listNode, countNode, button, maxBytes) {
  const selected = [...files];
  if (!auditId || !selected.length) return;
  const oversized = selected.find((file) => file.size > maxBytes);
  if (oversized) {
    throw new Error(`${oversized.name} exceeds the ${formatBytes(maxBytes)} per-file limit.`);
  }

  button.disabled = true;
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
    button.disabled = false;
    button.textContent = original;
  }
}

async function streamReplication(auditId, prompt, timeline, button) {
  button.disabled = true;
  button.textContent = "Running…";
  timeline.innerHTML = `<div class="status-row"><span class="status-icon running">↻</span><div class="status-copy"><strong>Opening replication stream</strong><small>Waiting for structured ACP events…</small></div></div>`;
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
    while (true) {
      const { value, done } = await reader.read();
      if (done) break;
      buffer += decoder.decode(value, { stream: true });
      const lines = buffer.split("\n");
      buffer = lines.pop() || "";
      for (const line of lines) {
        if (!line.trim()) continue;
        rows += traceRow(JSON.parse(line));
        timeline.innerHTML = rows;
        timeline.scrollTop = timeline.scrollHeight;
      }
    }
    if (buffer.trim()) {
      rows += traceRow(JSON.parse(buffer));
      timeline.innerHTML = rows;
    }
  } catch (error) {
    timeline.innerHTML += `<div class="status-row"><span class="status-icon danger">!</span><div class="status-copy"><strong>Replication request failed</strong><small>${escapeHtml(error.message)}</small></div>${badge("danger", "error")}</div>`;
  } finally {
    button.disabled = false;
    button.textContent = "Run reproduction";
  }
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
          <p class="page-subtitle">Attach immutable research artifacts, run a server-configured ACP agent in a run-specific workspace, and inspect every structured update. The browser never supplies an executable command.</p>
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
          <div class="status-row"><span class="status-icon">·</span><div class="status-copy"><strong>No replication run in this session</strong><small>Start a run to stream agent updates, tool permissions, and completion state.</small></div></div>
        </div>
      </section>
    </div>`;

    const auditSelect = document.querySelector("#replication-audit");
    const artifactList = document.querySelector("#replication-artifact-list");
    const artifactCount = document.querySelector("#replication-artifact-count");
    const artifactInput = document.querySelector("#replication-artifact-input");
    const artifactAdd = document.querySelector("#replication-artifact-add");
    const artifactError = document.querySelector("#replication-artifact-error");

    if (auditSelect && artifactList) {
      await loadArtifacts(auditSelect.value, artifactList, artifactCount);
      auditSelect.addEventListener("change", async () => {
        if (artifactError) { artifactError.hidden = true; artifactError.textContent = ""; }
        await loadArtifacts(auditSelect.value, artifactList, artifactCount);
      });
    }

    if (artifactAdd && artifactInput) {
      artifactAdd.addEventListener("click", () => artifactInput.click());
      artifactInput.addEventListener("change", async () => {
        if (!auditSelect?.value || !artifactList || !artifactInput.files?.length) return;
        if (artifactError) { artifactError.hidden = true; artifactError.textContent = ""; }
        try {
          await uploadArtifacts(
            auditSelect.value,
            artifactInput.files,
            artifactList,
            artifactCount,
            artifactAdd,
            maxAttachmentBytes,
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

    const button = document.querySelector("#replication-run");
    if (button) {
      button.addEventListener("click", async () => {
        const auditId = auditSelect?.value;
        const prompt = document.querySelector("#replication-prompt")?.value.trim();
        const timeline = document.querySelector("#replication-timeline");
        if (!auditId || !timeline) return;
        if (!prompt) {
          timeline.innerHTML = `<div class="status-row"><span class="status-icon review">!</span><div class="status-copy"><strong>Describe the reproduction goal</strong><small>The server accepts a goal/prompt, never a client-supplied executable command.</small></div>${badge("review")}</div>`;
          return;
        }
        await streamReplication(auditId, prompt, timeline, button);
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
