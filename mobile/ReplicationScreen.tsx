import * as DocumentPicker from "expo-document-picker";
import React, { useEffect, useMemo, useRef, useState } from "react";
import {
  ActivityIndicator,
  Alert,
  Pressable,
  ScrollView,
  StyleSheet,
  Text,
  TextInput,
  View,
} from "react-native";

const API_BASE = (process.env.EXPO_PUBLIC_VERITAS_API_URL || "http://127.0.0.1:8765").replace(/\/$/, "");

type AuditOption = {
  audit_id: string;
  title: string;
};

type ReplicationCapability = {
  configured: boolean;
  agent?: string | null;
  permission_policy?: string;
  permission_policy_valid?: boolean;
  workspace_is_security_boundary?: boolean;
  client_supplied_commands?: boolean;
  immutable_artifact_intake?: boolean;
  workspace_per_run?: boolean;
  interactive_approval_supported?: boolean;
  interactive_approval_enabled?: boolean;
  cancellation_supported?: boolean;
  workspace_inspector?: boolean;
  workspace_diff?: boolean;
};

type Attachment = {
  attachment_id: string;
  filename: string;
  sha256: string;
  size_bytes: number;
  media_type?: string;
  created_at?: string;
};

type AgentEvent = {
  kind?: string;
  title?: string;
  detail?: string;
  status?: string;
  payload?: Record<string, unknown>;
};

type HarnessEvent = {
  event_id: string;
  kind: string;
  title: string;
  detail?: string;
  status?: string;
  created_at?: string;
  payload?: {
    run_id?: string;
    run_kind?: string;
    phase?: string;
    duration_ms?: number;
    error_type?: string;
    agent_event?: AgentEvent;
  };
};

type ParserRef = string | {
  parser_id?: string;
  parser?: string;
  name?: string;
  version?: string;
};

type RunSummary = {
  run_id: string;
  audit_id: string;
  audit_title?: string;
  tool?: string;
  run_kind?: string;
  task?: string;
  phase?: string;
  status?: string;
  evidence?: boolean;
  coverage?: number;
  counts?: { verified?: number; needs_review?: number; contradictions?: number };
  duration_ms?: number | null;
  artifact_id?: string | null;
  parsers?: ParserRef[];
  error_type?: string | null;
  created_at?: string;
};

type RunDetail = RunSummary & {
  started_at?: string | null;
  finished_at?: string | null;
  source?: { page?: number; table?: string; row?: string };
  events?: HarnessEvent[];
};

type WorkspaceFile = {
  path: string;
  size_bytes: number;
  sha256?: string | null;
  baseline_sha256?: string | null;
  binary?: boolean;
  kind?: string;
  change: "original" | "created" | "modified" | "deleted" | "unsafe_link";
  immutable_input?: boolean;
};

type WorkspaceSnapshot = {
  schema_version: number;
  run_id: string;
  audit_id: string;
  workspace_is_security_boundary: boolean;
  files: WorkspaceFile[];
  counts: Record<string, number>;
  changed_files: string[];
  staged_input_drift: string[];
  staged_inputs_unchanged: boolean;
};

type WorkspaceFileDetail = {
  run_id: string;
  audit_id: string;
  path: string;
  change: string;
  size_bytes: number;
  sha256?: string | null;
  baseline_sha256?: string | null;
  immutable_input?: boolean;
  binary?: boolean;
  baseline_binary?: boolean;
  truncated?: boolean;
  baseline_truncated?: boolean;
  content?: string | null;
  baseline_content?: string | null;
  diff?: string;
};

type InspectorTab = "changes" | "files" | "run";

type Reader = {
  read: () => Promise<{ value?: Uint8Array; done: boolean }>;
  cancel?: () => Promise<void>;
};

type ReadableResponseBody = {
  getReader?: () => Reader;
  cancel?: () => Promise<void>;
};

async function request(path: string, init?: RequestInit) {
  const response = await fetch(`${API_BASE}${path}`, init);
  if (!response.ok) {
    let message = `${response.status} ${response.statusText}`;
    try { message = (await response.json()).detail || message; } catch {}
    throw new Error(message);
  }
  return response;
}

function formatDuration(value?: number | null) {
  if (value == null || !Number.isFinite(Number(value))) return "—";
  const ms = Number(value);
  if (ms < 1000) return `${Math.round(ms)} ms`;
  return `${(ms / 1000).toFixed(ms < 10000 ? 2 : 1)} s`;
}

function formatDate(value?: string | null) {
  if (!value) return "—";
  const date = new Date(value);
  return Number.isNaN(date.getTime()) ? "—" : date.toLocaleString();
}

function formatBytes(value?: number | null) {
  const bytes = Number(value) || 0;
  if (bytes < 1024) return `${bytes} B`;
  if (bytes < 1024 * 1024) return `${(bytes / 1024).toFixed(bytes < 10 * 1024 ? 1 : 0)} KiB`;
  return `${(bytes / 1024 / 1024).toFixed(bytes < 10 * 1024 * 1024 ? 1 : 0)} MiB`;
}

function parserLabel(parser: ParserRef) {
  if (typeof parser === "string") return parser;
  const name = parser.parser_id || parser.parser || parser.name || "parser";
  return parser.version ? `${name} ${parser.version}` : name;
}

function agentEvent(event: HarnessEvent) {
  return event.payload?.agent_event;
}

function permissionPayload(event: HarnessEvent) {
  const inner = agentEvent(event);
  if (inner?.kind !== "permission") return null;
  return inner.payload || null;
}

function payloadString(payload: Record<string, unknown> | null, key: string) {
  const value = payload?.[key];
  return typeof value === "string" ? value : "";
}

function permissionOptions(payload: Record<string, unknown> | null) {
  const value = payload?.options;
  return Array.isArray(value) ? value.filter((item): item is Record<string, unknown> => Boolean(item) && typeof item === "object") : [];
}

function optionId(option: Record<string, unknown>) {
  const value = option.optionId ?? option.option_id;
  return typeof value === "string" ? value : "";
}

function CapabilityRow({ label, value }: { label: string; value: string }) {
  return <View style={styles.capabilityRow}><Text style={styles.capabilityLabel}>{label}</Text><Text style={styles.capabilityValue}>{value}</Text></View>;
}

function EventRow({ event }: { event: HarnessEvent }) {
  const inner = agentEvent(event);
  const phase = event.payload?.phase ? ` · ${event.payload.phase}` : "";
  const duration = event.payload?.duration_ms != null ? ` · ${formatDuration(event.payload.duration_ms)}` : "";
  const icon = inner?.kind === "permission" ? "?" : inner?.kind === "agent_update" ? "›" : event.kind === "tool" ? "⌁" : event.kind === "replication" ? "↻" : "·";
  const danger = event.status === "danger" || event.status === "error" || event.status === "blocked";
  const title = inner?.title || event.title;
  const detail = inner?.detail || event.detail;
  return <View style={styles.eventRow}>
    <View style={[styles.eventIcon, danger && styles.eventIconDanger]}><Text style={styles.eventIconText}>{icon}</Text></View>
    <View style={styles.eventCard}>
      <View style={styles.eventTop}><Text style={styles.eventTitle}>{title}</Text><Text style={[styles.eventStatus, danger && styles.eventStatusDanger]}>{inner?.status || event.status || "info"}</Text></View>
      {detail ? <Text style={styles.eventDetail}>{detail}</Text> : null}
      <Text style={styles.eventMeta}>{inner?.kind || event.kind}{phase}{duration}{event.created_at ? ` · ${formatDate(event.created_at)}` : ""}</Text>
    </View>
  </View>;
}

function RunRow({ run, selected, onPress }: { run: RunSummary; selected: boolean; onPress: () => void }) {
  const danger = run.status === "danger" || run.status === "error";
  return <Pressable onPress={onPress} style={[styles.runRow, selected && styles.runRowSelected]}>
    <View style={[styles.runIcon, danger && styles.eventIconDanger]}><Text style={styles.eventIconText}>↻</Text></View>
    <View style={styles.runCopy}>
      <Text style={styles.runTitle} numberOfLines={1}>{run.task || run.tool || "Replication run"}</Text>
      <Text style={styles.runMeta} numberOfLines={1}>{run.audit_title || run.audit_id} · {formatDuration(run.duration_ms)}</Text>
    </View>
    <Text style={[styles.runStatus, danger && styles.eventStatusDanger]}>{run.phase || run.status || "ready"}</Text>
  </Pressable>;
}

function WorkspaceFileRow({ file, selected, onPress }: { file: WorkspaceFile; selected: boolean; onPress: () => void }) {
  const changed = file.change !== "original";
  const unsafe = file.change === "unsafe_link";
  return <Pressable onPress={onPress} disabled={unsafe} style={[styles.fileRow, selected && styles.fileRowSelected, unsafe && styles.fileRowUnsafe]}>
    <View style={[styles.fileMark, changed && styles.fileMarkChanged]}><Text style={styles.fileMarkText}>{file.kind === "symlink" ? "↗" : file.binary ? "◇" : "≡"}</Text></View>
    <View style={styles.fileCopy}>
      <Text style={styles.fileTitle} numberOfLines={1}>{file.path}</Text>
      <Text style={styles.fileMeta}>{file.change} · {formatBytes(file.size_bytes)}{file.immutable_input ? " · staged input" : ""}</Text>
    </View>
    {changed ? <View style={[styles.changePill, unsafe && styles.changePillDanger]}><Text style={styles.changePillText}>{file.change}</Text></View> : null}
  </Pressable>;
}

function RunDetailCard({ detail, loading }: { detail: RunDetail | null; loading: boolean }) {
  if (loading) return <View style={styles.centered}><ActivityIndicator color="#5368f5" /><Text style={styles.helper}>Loading run…</Text></View>;
  if (!detail) return <Text style={styles.empty}>Select a replication run to inspect its persisted lifecycle.</Text>;
  return <View>
    <CapabilityRow label="Run" value={detail.run_id} />
    <CapabilityRow label="Status" value={detail.phase || detail.status || "ready"} />
    <CapabilityRow label="Started" value={formatDate(detail.started_at)} />
    <CapabilityRow label="Finished" value={formatDate(detail.finished_at)} />
    <CapabilityRow label="Duration" value={formatDuration(detail.duration_ms)} />
    <CapabilityRow label="Agent tool" value={detail.tool || "replication.acp"} />
    {detail.error_type ? <CapabilityRow label="Error" value={detail.error_type} /> : null}
    <View style={styles.traceHead}><Text style={styles.cardTitle}>Persisted events</Text><Text style={styles.traceCount}>{detail.events?.length || 0}</Text></View>
    {(detail.events || []).map((event) => <EventRow key={event.event_id} event={event} />)}
  </View>;
}

async function consumeNdjson(
  response: Response,
  onEvent: (event: HarnessEvent) => void,
  *,
  requireStreaming: boolean,
) {
  const body = response.body as unknown as ReadableResponseBody | null;
  if (!body?.getReader || typeof TextDecoder === "undefined") {
    if (requireStreaming) {
      try { await body?.cancel?.(); } catch {}
      throw new Error("Interactive approval requires streaming fetch support in this mobile runtime.");
    }
    const text = await response.text();
    text.split("\n").filter(Boolean).forEach((line) => onEvent(JSON.parse(line) as HarnessEvent));
    return;
  }

  const reader = body.getReader();
  const decoder = new TextDecoder();
  let buffer = "";
  while (true) {
    const { value, done } = await reader.read();
    if (done) break;
    if (!value) continue;
    buffer += decoder.decode(value, { stream: true });
    const lines = buffer.split("\n");
    buffer = lines.pop() || "";
    for (const line of lines) {
      if (line.trim()) onEvent(JSON.parse(line) as HarnessEvent);
    }
  }
  buffer += decoder.decode();
  if (buffer.trim()) onEvent(JSON.parse(buffer) as HarnessEvent);
}

export default function ReplicationScreen({ audits }: { audits: AuditOption[] }) {
  const [capability, setCapability] = useState<ReplicationCapability | null>(null);
  const [maxAttachmentBytes, setMaxAttachmentBytes] = useState(80 * 1024 * 1024);
  const [selectedAudit, setSelectedAudit] = useState<string>(audits[0]?.audit_id || "");
  const [attachments, setAttachments] = useState<Attachment[]>([]);
  const [loadingAttachments, setLoadingAttachments] = useState(false);
  const [uploadingArtifact, setUploadingArtifact] = useState(false);
  const [prompt, setPrompt] = useState("Reproduce the paper's main reported result and record the environment, steps, outputs, and discrepancies.");
  const [events, setEvents] = useState<HarnessEvent[]>([]);
  const [running, setRunning] = useState(false);
  const [activeRunId, setActiveRunId] = useState("");
  const [decisionBusy, setDecisionBusy] = useState<string>("");
  const [runs, setRuns] = useState<RunSummary[]>([]);
  const [selectedRunId, setSelectedRunId] = useState("");
  const [runDetail, setRunDetail] = useState<RunDetail | null>(null);
  const [loadingRuns, setLoadingRuns] = useState(false);
  const [loadingDetail, setLoadingDetail] = useState(false);
  const [workspace, setWorkspace] = useState<WorkspaceSnapshot | null>(null);
  const [loadingWorkspace, setLoadingWorkspace] = useState(false);
  const [inspectorTab, setInspectorTab] = useState<InspectorTab>("changes");
  const [selectedPath, setSelectedPath] = useState("");
  const [fileDetail, setFileDetail] = useState<WorkspaceFileDetail | null>(null);
  const [loadingFile, setLoadingFile] = useState(false);
  const abortRef = useRef<AbortController | null>(null);
  const interactionLocked = running || uploadingArtifact || loadingAttachments;

  useEffect(() => {
    if (!selectedAudit && audits[0]) setSelectedAudit(audits[0].audit_id);
    if (selectedAudit && !audits.some((audit) => audit.audit_id === selectedAudit)) setSelectedAudit(audits[0]?.audit_id || "");
  }, [audits, selectedAudit]);

  useEffect(() => {
    request("/api/v1/capabilities")
      .then((response) => response.json())
      .then((value) => {
        setCapability(value.replication || { configured: false });
        setMaxAttachmentBytes(Number(value.max_attachment_bytes) || 80 * 1024 * 1024);
      })
      .catch((error) => Alert.alert("Replication capability unavailable", String(error)));
    void refreshRuns();
    return () => abortRef.current?.abort();
  }, []);

  useEffect(() => {
    if (selectedAudit) void refreshAttachments(selectedAudit);
    else setAttachments([]);
  }, [selectedAudit]);

  const selectedTitle = useMemo(
    () => audits.find((audit) => audit.audit_id === selectedAudit)?.title || "No paper selected",
    [audits, selectedAudit],
  );

  const resolvedPermissionIds = useMemo(() => {
    const ids = new Set<string>();
    for (const event of events) {
      const payload = permissionPayload(event);
      const requestId = payloadString(payload, "request_id");
      const decision = payloadString(payload, "decision");
      if (requestId && decision && decision !== "pending") ids.add(requestId);
    }
    return ids;
  }, [events]);

  const pendingPermissions = useMemo(() => events.filter((event) => {
    const payload = permissionPayload(event);
    const requestId = payloadString(payload, "request_id");
    return Boolean(requestId && payloadString(payload, "decision") === "pending" && !resolvedPermissionIds.has(requestId));
  }), [events, resolvedPermissionIds]);

  const refreshAttachments = async (auditId: string) => {
    setLoadingAttachments(true);
    try {
      const next = await request(`/api/v1/audits/${encodeURIComponent(auditId)}/attachments`).then((response) => response.json()) as Attachment[];
      setAttachments(next);
    } catch (error) {
      setAttachments([]);
      Alert.alert("Artifact manifest unavailable", error instanceof Error ? error.message : String(error));
    } finally {
      setLoadingAttachments(false);
    }
  };

  const attachArtifact = async () => {
    if (!selectedAudit || interactionLocked) return;
    const result = await DocumentPicker.getDocumentAsync({ type: "*/*", copyToCacheDirectory: true });
    if (result.canceled || !result.assets[0]) return;
    const asset = result.assets[0];
    if (asset.size != null && asset.size > maxAttachmentBytes) {
      Alert.alert("Artifact too large", `${asset.name} exceeds the ${formatBytes(maxAttachmentBytes)} per-file limit.`);
      return;
    }
    const body = new FormData();
    body.append("file", { uri: asset.uri, name: asset.name, type: asset.mimeType || "application/octet-stream" } as never);
    setUploadingArtifact(true);
    try {
      await request(`/api/v1/audits/${encodeURIComponent(selectedAudit)}/attachments`, { method: "POST", body });
      await refreshAttachments(selectedAudit);
    } catch (error) {
      Alert.alert("Artifact upload failed", error instanceof Error ? error.message : String(error));
    } finally {
      setUploadingArtifact(false);
    }
  };

  const loadWorkspace = async (runId: string) => {
    if (!runId) return;
    setLoadingWorkspace(true);
    try {
      const next = await request(`/api/v1/runs/${encodeURIComponent(runId)}/workspace`).then((response) => response.json()) as WorkspaceSnapshot;
      setWorkspace(next);
      if (selectedPath && !next.files.some((item) => item.path === selectedPath)) {
        setSelectedPath("");
        setFileDetail(null);
      }
    } catch (error) {
      setWorkspace(null);
      Alert.alert("Workspace inspector unavailable", error instanceof Error ? error.message : String(error));
    } finally {
      setLoadingWorkspace(false);
    }
  };

  const openWorkspaceFile = async (runId: string, path: string) => {
    setSelectedPath(path);
    setLoadingFile(true);
    try {
      const detail = await request(`/api/v1/runs/${encodeURIComponent(runId)}/workspace/file?path=${encodeURIComponent(path)}`).then((response) => response.json()) as WorkspaceFileDetail;
      setFileDetail(detail);
    } catch (error) {
      setFileDetail(null);
      Alert.alert("Workspace file unavailable", error instanceof Error ? error.message : String(error));
    } finally {
      setLoadingFile(false);
    }
  };

  const openRun = async (runId: string) => {
    setSelectedRunId(runId);
    setSelectedPath("");
    setFileDetail(null);
    setLoadingDetail(true);
    try {
      const detail = await request(`/api/v1/runs/${encodeURIComponent(runId)}`).then((response) => response.json()) as RunDetail;
      setRunDetail(detail);
      if (detail.run_kind === "replication") await loadWorkspace(runId);
      else setWorkspace(null);
    } catch (error) {
      setRunDetail(null);
      setWorkspace(null);
      Alert.alert("Unable to load run", error instanceof Error ? error.message : String(error));
    } finally {
      setLoadingDetail(false);
    }
  };

  const refreshRuns = async (preferredRunId?: string) => {
    setLoadingRuns(true);
    try {
      const all = await request("/api/v1/runs").then((response) => response.json()) as RunSummary[];
      const nextRuns = all.filter((item) => item.run_kind === "replication");
      setRuns(nextRuns);
      const nextId = preferredRunId || selectedRunId || nextRuns[0]?.run_id || "";
      if (nextId) await openRun(nextId);
      else {
        setSelectedRunId("");
        setRunDetail(null);
        setWorkspace(null);
      }
    } catch (error) {
      Alert.alert("Run history unavailable", error instanceof Error ? error.message : String(error));
    } finally {
      setLoadingRuns(false);
    }
  };

  const decidePermission = async (event: HarnessEvent, decision: "allow_once" | "reject", selectedOptionId?: string) => {
    const payload = permissionPayload(event);
    const requestId = payloadString(payload, "request_id");
    const runId = event.payload?.run_id || activeRunId;
    if (!runId || !requestId || decisionBusy) return;
    setDecisionBusy(requestId);
    try {
      await request(`/api/v1/replication/runs/${encodeURIComponent(runId)}/permissions/${encodeURIComponent(requestId)}`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ decision, option_id: selectedOptionId || null }),
      });
    } catch (error) {
      Alert.alert("Permission decision failed", error instanceof Error ? error.message : String(error));
    } finally {
      setDecisionBusy("");
    }
  };

  const cancelRun = async () => {
    if (!activeRunId) return;
    try {
      await request(`/api/v1/replication/runs/${encodeURIComponent(activeRunId)}/cancel`, { method: "POST" });
    } catch (error) {
      Alert.alert("Cancel failed", error instanceof Error ? error.message : String(error));
    }
  };

  const run = async () => {
    const goal = prompt.trim();
    if (!selectedAudit || !goal || interactionLocked) return;
    const targetAuditId = selectedAudit;
    const controller = new AbortController();
    abortRef.current = controller;
    setRunning(true);
    setEvents([]);
    setActiveRunId("");
    setWorkspace(null);
    setSelectedPath("");
    setFileDetail(null);
    let discoveredRunId = "";
    try {
      const response = await request(`/api/v1/audits/${encodeURIComponent(targetAuditId)}/replication`, {
        method: "POST",
        headers: { "Content-Type": "application/json", Accept: "application/x-ndjson" },
        body: JSON.stringify({ prompt: goal }),
        signal: controller.signal,
      });
      await consumeNdjson(response, (event) => {
        const runId = event.payload?.run_id;
        if (runId) {
          discoveredRunId = runId;
          setActiveRunId(runId);
        }
        setEvents((current) => [...current, event]);
      }, { requireStreaming: capability?.permission_policy === "interactive" });
      if (discoveredRunId) {
        setSelectedRunId(discoveredRunId);
        await loadWorkspace(discoveredRunId);
      }
      await refreshRuns(discoveredRunId || undefined);
    } catch (error) {
      if ((error as { name?: string }).name !== "AbortError") {
        Alert.alert("Replication run failed", error instanceof Error ? error.message : String(error));
      }
    } finally {
      abortRef.current = null;
      setRunning(false);
      setActiveRunId("");
    }
  };

  const configured = Boolean(capability?.configured);
  const runDisabled = !configured || !selectedAudit || !prompt.trim() || interactionLocked;
  const inspectedRunId = activeRunId || selectedRunId;
  const changedFiles = workspace?.files.filter((item) => item.change !== "original") || [];
  const visibleFiles = inspectorTab === "changes" ? changedFiles : workspace?.files || [];

  return <ScrollView contentContainerStyle={styles.page} keyboardShouldPersistTaps="handled">
    <View style={styles.heroRow}>
      <View style={styles.heroCopy}>
        <Text style={styles.eyebrow}>CODE-CAPABLE REPRODUCTION</Text>
        <Text style={styles.title}>Replication Workspace</Text>
        <Text style={styles.subtitle}>Run the server-selected ACP coding agent, review tool permissions, and inspect workspace changes from server-side hashes.</Text>
      </View>
      <View style={[styles.badge, configured ? styles.badgeReady : styles.badgeReview]}><Text style={styles.badgeText}>{configured ? capability?.agent || "agent" : "fail-closed"}</Text></View>
    </View>

    <View style={styles.card}>
      <View style={styles.cardHead}><Text style={styles.cardTitle}>Execution boundary</Text><Text style={styles.cardMeta}>server controlled</Text></View>
      <CapabilityRow label="Permission policy" value={capability?.permission_policy || "deny"} />
      <CapabilityRow label="Interactive approval" value={capability?.interactive_approval_enabled ? "enabled" : "off"} />
      <CapabilityRow label="Client shell commands" value={capability?.client_supplied_commands ? "allowed" : "disabled"} />
      <CapabilityRow label="Workspace inspector" value={capability?.workspace_inspector ? "server-side" : "unavailable"} />
      <CapabilityRow label="Workspace sandbox" value={capability?.workspace_is_security_boundary ? "yes" : "agent-owned"} />
      {capability && capability.permission_policy_valid === false ? <Text style={styles.warning}>Invalid server policy detected; Veritas has fallen back to deny.</Text> : null}
      <Text style={styles.boundaryCopy}>The run directory is inspectable but is not a security boundary. Process, filesystem and network isolation remain the configured agent runtime's responsibility.</Text>
    </View>

    <View style={styles.card}>
      <View style={styles.cardHead}><Text style={styles.cardTitle}>Project</Text><Text style={styles.cardMeta}>{attachments.length} artifacts</Text></View>
      <Text style={styles.selectedTitle}>{selectedTitle}</Text>
      <ScrollView horizontal showsHorizontalScrollIndicator={false} contentContainerStyle={styles.auditChips}>
        {audits.map((audit) => <Pressable key={audit.audit_id} disabled={interactionLocked} onPress={() => setSelectedAudit(audit.audit_id)} style={[styles.auditChip, selectedAudit === audit.audit_id && styles.auditChipActive, interactionLocked && styles.disabled]}><Text numberOfLines={1} style={[styles.auditChipText, selectedAudit === audit.audit_id && styles.auditChipTextActive]}>{audit.title}</Text></Pressable>)}
      </ScrollView>
      {!audits.length ? <Text style={styles.empty}>Upload a paper before starting a replication workspace.</Text> : null}

      {selectedAudit ? <View style={styles.artifactSection}>
        <View style={styles.artifactHead}>
          <View style={styles.flex}><Text style={styles.sectionTitle}>Immutable inputs</Text><Text style={styles.sectionCopy}>Staged byte-for-byte into each run · max {formatBytes(maxAttachmentBytes)} each</Text></View>
          <Pressable onPress={attachArtifact} disabled={interactionLocked} style={[styles.smallButton, interactionLocked && styles.disabled]}>{uploadingArtifact ? <ActivityIndicator size="small" color="#5368f5" /> : <Text style={styles.smallButtonText}>＋ Attach</Text>}</Pressable>
        </View>
        {loadingAttachments ? <View style={styles.centered}><ActivityIndicator size="small" color="#5368f5" /></View> : null}
        {!loadingAttachments && attachments.map((attachment) => <View style={styles.artifactRow} key={attachment.attachment_id}>
          <View style={styles.artifactMark}><Text style={styles.artifactMarkText}>◇</Text></View>
          <View style={styles.flex}><Text style={styles.artifactTitle} numberOfLines={1}>{attachment.filename}</Text><Text style={styles.artifactMeta} numberOfLines={1}>{formatBytes(attachment.size_bytes)} · sha256:{attachment.sha256.slice(0, 14)}…</Text></View>
        </View>)}
      </View> : null}
    </View>

    <View style={styles.card}>
      <View style={styles.cardHead}><Text style={styles.cardTitle}>Agent conversation</Text><Text style={styles.cardMeta}>{running ? "live" : events.length ? `${events.length} events` : "idle"}</Text></View>
      <Text style={styles.fieldLabel}>Reproduction goal</Text>
      <TextInput value={prompt} onChangeText={setPrompt} multiline editable={!interactionLocked && configured} style={styles.input} placeholder="Describe the reproduction goal…" placeholderTextColor="#9aa2b1" />
      <View style={styles.actionRow}>
        <Pressable onPress={run} disabled={runDisabled} style={[styles.runButton, runDisabled && styles.disabled]}>
          {running ? <ActivityIndicator color="#fff" /> : <Text style={styles.runButtonText}>Run agent</Text>}
        </Pressable>
        {running && activeRunId && capability?.cancellation_supported ? <Pressable onPress={cancelRun} style={styles.cancelButton}><Text style={styles.cancelButtonText}>Cancel run</Text></Pressable> : null}
      </View>
      {!configured ? <Text style={styles.helper}>Configure VERITAS_REPLICATION_AGENT on the server. The mobile client never supplies an executable command.</Text> : null}

      {pendingPermissions.map((event) => {
        const payload = permissionPayload(event);
        const requestId = payloadString(payload, "request_id");
        const options = permissionOptions(payload);
        const allowOptions = options.filter((option) => option.kind === "allow_once" && optionId(option));
        return <View style={styles.permissionCard} key={`${event.event_id}-${requestId}`}>
          <Text style={styles.permissionEyebrow}>HUMAN APPROVAL REQUIRED</Text>
          <Text style={styles.permissionTitle}>{agentEvent(event)?.title || "Tool permission"}</Text>
          <Text style={styles.permissionCopy}>{agentEvent(event)?.detail || "The coding agent requested permission for a tool action."}</Text>
          <View style={styles.permissionActions}>
            <Pressable disabled={decisionBusy === requestId} onPress={() => void decidePermission(event, "reject")} style={styles.rejectButton}><Text style={styles.rejectText}>Reject</Text></Pressable>
            {allowOptions.map((option) => <Pressable key={optionId(option)} disabled={decisionBusy === requestId} onPress={() => void decidePermission(event, "allow_once", optionId(option))} style={styles.allowButton}><Text style={styles.allowText}>{typeof option.name === "string" ? option.name : "Allow once"}</Text></Pressable>)}
          </View>
          <Text style={styles.permissionFoot}>Only an allow_once option explicitly offered by the ACP agent can be approved.</Text>
        </View>;
      })}

      <View style={styles.traceHead}><Text style={styles.sectionTitle}>Live trace</Text><Text style={styles.traceCount}>{events.length} events</Text></View>
      {events.map((event) => <EventRow key={event.event_id} event={event} />)}
      {!events.length ? <View style={styles.emptyTrace}><Text style={styles.empty}>No agent activity in this session yet.</Text></View> : null}
    </View>

    <View style={styles.card}>
      <View style={styles.cardHead}><Text style={styles.cardTitle}>Workspace inspector</Text><Pressable disabled={!inspectedRunId || loadingWorkspace} onPress={() => inspectedRunId && void loadWorkspace(inspectedRunId)} style={[styles.refreshButton, (!inspectedRunId || loadingWorkspace) && styles.disabled]}>{loadingWorkspace ? <ActivityIndicator size="small" color="#5368f5" /> : <Text style={styles.refreshText}>Refresh</Text>}</Pressable></View>
      <View style={styles.tabs}>
        {(["changes", "files", "run"] as InspectorTab[]).map((tab) => <Pressable key={tab} onPress={() => setInspectorTab(tab)} style={[styles.tab, inspectorTab === tab && styles.tabActive]}><Text style={[styles.tabText, inspectorTab === tab && styles.tabTextActive]}>{tab === "changes" ? `Changes ${changedFiles.length}` : tab === "files" ? `Files ${workspace?.files.length || 0}` : "Run"}</Text></Pressable>)}
      </View>

      {inspectorTab === "run" ? <RunDetailCard detail={runDetail} loading={loadingDetail} /> : <>
        {workspace?.staged_input_drift.length ? <View style={styles.driftBanner}><Text style={styles.driftTitle}>Staged input drift detected</Text><Text style={styles.driftCopy}>{workspace.staged_input_drift.join(" · ")}</Text></View> : null}
        {!workspace && !loadingWorkspace ? <Text style={styles.empty}>Run or select a replication session to inspect its server-side workspace snapshot.</Text> : null}
        {visibleFiles.map((file) => <WorkspaceFileRow key={file.path} file={file} selected={selectedPath === file.path} onPress={() => inspectedRunId && void openWorkspaceFile(inspectedRunId, file.path)} />)}
        {workspace && !visibleFiles.length ? <Text style={styles.empty}>{inspectorTab === "changes" ? "No workspace changes detected." : "No regular workspace files found."}</Text> : null}

        {loadingFile ? <View style={styles.centered}><ActivityIndicator color="#5368f5" /><Text style={styles.helper}>Reading safe workspace preview…</Text></View> : null}
        {fileDetail && !loadingFile ? <View style={styles.fileDetail}>
          <View style={styles.fileDetailHead}><View style={styles.flex}><Text style={styles.fileDetailTitle}>{fileDetail.path}</Text><Text style={styles.fileDetailMeta}>{fileDetail.change} · {formatBytes(fileDetail.size_bytes)}{fileDetail.truncated ? " · preview truncated" : ""}</Text></View></View>
          {fileDetail.binary ? <Text style={styles.empty}>Binary content is not rendered. Hash and change status remain available.</Text> : fileDetail.diff ? <ScrollView horizontal style={styles.codeScroll}><Text selectable style={styles.code}>{fileDetail.diff}</Text></ScrollView> : <ScrollView horizontal style={styles.codeScroll}><Text selectable style={styles.code}>{fileDetail.content || ""}</Text></ScrollView>}
        </View> : null}
      </>}
    </View>

    <View style={styles.historyHead}>
      <View style={styles.flex}><Text style={styles.cardTitle}>Previous replication runs</Text><Text style={styles.historyCopy}>Reopen the persisted trace and retained run workspace.</Text></View>
      <Pressable onPress={() => void refreshRuns()} disabled={loadingRuns} style={[styles.refreshButton, loadingRuns && styles.disabled]}>{loadingRuns ? <ActivityIndicator size="small" color="#5368f5" /> : <Text style={styles.refreshText}>Refresh</Text>}</Pressable>
    </View>
    <View style={styles.card}>
      {runs.slice(0, 12).map((item) => <RunRow key={item.run_id} run={item} selected={selectedRunId === item.run_id} onPress={() => void openRun(item.run_id)} />)}
      {!runs.length && !loadingRuns ? <Text style={styles.empty}>No persisted replication runs yet.</Text> : null}
    </View>
  </ScrollView>;
}

const styles = StyleSheet.create({
  page: { padding: 16, paddingBottom: 34, backgroundColor: "#f7f8fa" },
  heroRow: { flexDirection: "row", alignItems: "flex-start", gap: 12, marginBottom: 16 },
  heroCopy: { flex: 1 },
  eyebrow: { color: "#5368f5", fontSize: 8.5, fontWeight: "800", letterSpacing: 1.1, marginBottom: 6 },
  title: { color: "#151927", fontSize: 26, fontWeight: "800", letterSpacing: -0.7 },
  subtitle: { color: "#626b7d", fontSize: 10.5, lineHeight: 16, marginTop: 6 },
  card: { backgroundColor: "#fff", borderWidth: StyleSheet.hairlineWidth, borderColor: "#e1e4ea", borderRadius: 13, padding: 13, marginBottom: 11 },
  cardHead: { flexDirection: "row", alignItems: "center", justifyContent: "space-between", gap: 10, marginBottom: 8 },
  cardTitle: { color: "#202532", fontSize: 12, fontWeight: "800" },
  cardMeta: { color: "#8a93a4", fontSize: 7.5, fontWeight: "700" },
  badge: { borderRadius: 999, paddingHorizontal: 9, paddingVertical: 5, maxWidth: 120 },
  badgeReady: { backgroundColor: "#eaf8f3" },
  badgeReview: { backgroundColor: "#fff3d8" },
  badgeText: { color: "#596273", fontSize: 7.5, fontWeight: "800" },
  capabilityRow: { minHeight: 31, flexDirection: "row", alignItems: "center", justifyContent: "space-between", gap: 12, borderBottomWidth: StyleSheet.hairlineWidth, borderBottomColor: "#eef0f3" },
  capabilityLabel: { color: "#7c8595", fontSize: 8.5 },
  capabilityValue: { color: "#202532", fontSize: 8.5, fontWeight: "700", maxWidth: "63%", textAlign: "right" },
  warning: { marginTop: 10, padding: 9, borderRadius: 8, backgroundColor: "#fff6df", color: "#8a651c", fontSize: 8.5, lineHeight: 13 },
  boundaryCopy: { color: "#8a93a4", fontSize: 7.8, lineHeight: 12, marginTop: 9 },
  selectedTitle: { color: "#5f6879", fontSize: 9, fontWeight: "700", marginTop: 1 },
  auditChips: { gap: 7, paddingVertical: 10 },
  auditChip: { maxWidth: 190, borderWidth: StyleSheet.hairlineWidth, borderColor: "#d8dce4", borderRadius: 999, paddingHorizontal: 10, paddingVertical: 7, backgroundColor: "#fafbfc" },
  auditChipActive: { borderColor: "#aeb9ff", backgroundColor: "#eef0ff" },
  auditChipText: { color: "#687284", fontSize: 8.5 },
  auditChipTextActive: { color: "#4054d5", fontWeight: "700" },
  artifactSection: { paddingTop: 10, borderTopWidth: StyleSheet.hairlineWidth, borderTopColor: "#e7e9ee" },
  artifactHead: { flexDirection: "row", alignItems: "flex-start", gap: 10, marginBottom: 8 },
  sectionTitle: { color: "#242936", fontSize: 9.5, fontWeight: "800" },
  sectionCopy: { color: "#8a93a4", fontSize: 7.5, lineHeight: 11, marginTop: 2 },
  flex: { flex: 1, minWidth: 0 },
  smallButton: { minWidth: 70, minHeight: 30, paddingHorizontal: 8, borderWidth: StyleSheet.hairlineWidth, borderColor: "#d0d5de", borderRadius: 8, backgroundColor: "#fff", alignItems: "center", justifyContent: "center" },
  smallButtonText: { color: "#5368f5", fontSize: 8.5, fontWeight: "800" },
  artifactRow: { minHeight: 48, flexDirection: "row", alignItems: "center", gap: 8, marginTop: 6, padding: 7, borderWidth: StyleSheet.hairlineWidth, borderColor: "#e4e7ec", borderRadius: 9, backgroundColor: "#fbfcfd" },
  artifactMark: { width: 27, height: 27, borderRadius: 8, backgroundColor: "#eef0ff", alignItems: "center", justifyContent: "center" },
  artifactMarkText: { color: "#5368f5", fontSize: 10, fontWeight: "800" },
  artifactTitle: { color: "#242936", fontSize: 9, fontWeight: "700" },
  artifactMeta: { color: "#8a93a4", fontSize: 7.3, marginTop: 3 },
  fieldLabel: { color: "#596273", fontSize: 8.7, fontWeight: "700", marginTop: 2, marginBottom: 6 },
  input: { minHeight: 104, borderWidth: StyleSheet.hairlineWidth, borderColor: "#d8dce4", borderRadius: 10, padding: 10, color: "#151927", fontSize: 9.5, lineHeight: 15, textAlignVertical: "top", backgroundColor: "#fdfdfe" },
  actionRow: { flexDirection: "row", alignItems: "center", gap: 8, marginTop: 9 },
  runButton: { flex: 1, minHeight: 40, borderRadius: 10, backgroundColor: "#5368f5", alignItems: "center", justifyContent: "center" },
  runButtonText: { color: "#fff", fontSize: 10, fontWeight: "800" },
  cancelButton: { minHeight: 40, paddingHorizontal: 13, borderRadius: 10, borderWidth: StyleSheet.hairlineWidth, borderColor: "#e0aeb4", backgroundColor: "#fff7f7", alignItems: "center", justifyContent: "center" },
  cancelButtonText: { color: "#b63e49", fontSize: 9, fontWeight: "800" },
  disabled: { opacity: 0.4 },
  helper: { color: "#8a93a4", fontSize: 7.8, lineHeight: 12, marginTop: 7 },
  empty: { color: "#8a93a4", fontSize: 8.7, textAlign: "center", lineHeight: 13, paddingVertical: 14 },
  centered: { minHeight: 64, alignItems: "center", justifyContent: "center", gap: 5 },
  permissionCard: { marginTop: 11, padding: 11, borderWidth: StyleSheet.hairlineWidth, borderColor: "#e8c97a", borderRadius: 10, backgroundColor: "#fffaf0" },
  permissionEyebrow: { color: "#9a6b12", fontSize: 7, fontWeight: "900", letterSpacing: 0.8 },
  permissionTitle: { color: "#342a18", fontSize: 10.5, fontWeight: "800", marginTop: 4 },
  permissionCopy: { color: "#746243", fontSize: 8.3, lineHeight: 13, marginTop: 4 },
  permissionActions: { flexDirection: "row", flexWrap: "wrap", gap: 7, marginTop: 9 },
  rejectButton: { minHeight: 32, paddingHorizontal: 11, borderRadius: 8, borderWidth: StyleSheet.hairlineWidth, borderColor: "#d8b4b8", backgroundColor: "#fff", alignItems: "center", justifyContent: "center" },
  rejectText: { color: "#a63e49", fontSize: 8.5, fontWeight: "800" },
  allowButton: { minHeight: 32, paddingHorizontal: 11, borderRadius: 8, backgroundColor: "#5368f5", alignItems: "center", justifyContent: "center" },
  allowText: { color: "#fff", fontSize: 8.5, fontWeight: "800" },
  permissionFoot: { color: "#9b8a69", fontSize: 7.2, lineHeight: 11, marginTop: 7 },
  traceHead: { flexDirection: "row", alignItems: "center", justifyContent: "space-between", marginTop: 13, marginBottom: 8 },
  traceCount: { color: "#8a93a4", fontSize: 7.5 },
  eventRow: { flexDirection: "row", gap: 7, marginBottom: 7, alignItems: "flex-start" },
  eventIcon: { width: 25, height: 25, borderRadius: 13, borderWidth: StyleSheet.hairlineWidth, borderColor: "#d8dce4", backgroundColor: "#fff", alignItems: "center", justifyContent: "center" },
  eventIconDanger: { borderColor: "#efc8cc", backgroundColor: "#fff0f1" },
  eventIconText: { color: "#697385", fontSize: 8.5, fontWeight: "800" },
  eventCard: { flex: 1, backgroundColor: "#fbfcfd", borderWidth: StyleSheet.hairlineWidth, borderColor: "#e4e7ec", borderRadius: 9, padding: 9 },
  eventTop: { flexDirection: "row", alignItems: "flex-start", justifyContent: "space-between", gap: 8 },
  eventTitle: { flex: 1, color: "#242936", fontSize: 9.3, fontWeight: "700" },
  eventStatus: { color: "#657082", fontSize: 7, fontWeight: "700" },
  eventStatusDanger: { color: "#b63e49" },
  eventDetail: { color: "#687284", fontSize: 8.2, lineHeight: 12.5, marginTop: 4 },
  eventMeta: { color: "#9aa2b1", fontSize: 7, marginTop: 5 },
  emptyTrace: { minHeight: 82, borderWidth: StyleSheet.hairlineWidth, borderStyle: "dashed", borderColor: "#d8dce4", borderRadius: 10, alignItems: "center", justifyContent: "center", padding: 13 },
  tabs: { flexDirection: "row", gap: 5, padding: 4, borderRadius: 9, backgroundColor: "#f1f3f6", marginBottom: 9 },
  tab: { flex: 1, minHeight: 31, borderRadius: 7, alignItems: "center", justifyContent: "center" },
  tabActive: { backgroundColor: "#fff", borderWidth: StyleSheet.hairlineWidth, borderColor: "#dfe2e8" },
  tabText: { color: "#7a8393", fontSize: 8, fontWeight: "700" },
  tabTextActive: { color: "#3e4fc4" },
  refreshButton: { minWidth: 58, minHeight: 29, paddingHorizontal: 9, borderWidth: StyleSheet.hairlineWidth, borderColor: "#d8dce4", borderRadius: 8, alignItems: "center", justifyContent: "center", backgroundColor: "#fff" },
  refreshText: { color: "#5368f5", fontSize: 8, fontWeight: "800" },
  driftBanner: { padding: 9, borderRadius: 8, backgroundColor: "#fff0f1", borderWidth: StyleSheet.hairlineWidth, borderColor: "#efc8cc", marginBottom: 8 },
  driftTitle: { color: "#a63e49", fontSize: 8.7, fontWeight: "800" },
  driftCopy: { color: "#a75a62", fontSize: 7.3, lineHeight: 11, marginTop: 3 },
  fileRow: { minHeight: 50, flexDirection: "row", alignItems: "center", gap: 8, padding: 7, marginBottom: 6, borderWidth: StyleSheet.hairlineWidth, borderColor: "#e4e7ec", borderRadius: 9, backgroundColor: "#fbfcfd" },
  fileRowSelected: { borderColor: "#aeb9ff", backgroundColor: "#f4f5ff" },
  fileRowUnsafe: { borderColor: "#efc8cc", backgroundColor: "#fff7f7" },
  fileMark: { width: 27, height: 27, borderRadius: 8, backgroundColor: "#f0f2f5", alignItems: "center", justifyContent: "center" },
  fileMarkChanged: { backgroundColor: "#eef0ff" },
  fileMarkText: { color: "#657082", fontSize: 9, fontWeight: "800" },
  fileCopy: { flex: 1, minWidth: 0 },
  fileTitle: { color: "#242936", fontSize: 8.8, fontWeight: "700" },
  fileMeta: { color: "#8a93a4", fontSize: 7.1, marginTop: 3 },
  changePill: { paddingHorizontal: 6, paddingVertical: 4, borderRadius: 999, backgroundColor: "#eef0ff" },
  changePillDanger: { backgroundColor: "#fff0f1" },
  changePillText: { color: "#5869d5", fontSize: 6.8, fontWeight: "800" },
  fileDetail: { marginTop: 9, paddingTop: 10, borderTopWidth: StyleSheet.hairlineWidth, borderTopColor: "#e4e7ec" },
  fileDetailHead: { flexDirection: "row", gap: 8, marginBottom: 7 },
  fileDetailTitle: { color: "#202532", fontSize: 9.5, fontWeight: "800" },
  fileDetailMeta: { color: "#8a93a4", fontSize: 7.2, marginTop: 3 },
  codeScroll: { maxHeight: 300, borderRadius: 8, backgroundColor: "#151927" },
  code: { color: "#e8eaf0", fontSize: 8, lineHeight: 12, padding: 10, fontFamily: "monospace" },
  historyHead: { flexDirection: "row", alignItems: "center", gap: 10, marginTop: 4, marginBottom: 8 },
  historyCopy: { color: "#8a93a4", fontSize: 7.5, marginTop: 2 },
  runRow: { minHeight: 54, flexDirection: "row", alignItems: "center", gap: 8, padding: 7, marginBottom: 6, borderWidth: StyleSheet.hairlineWidth, borderColor: "#e4e7ec", borderRadius: 9, backgroundColor: "#fbfcfd" },
  runRowSelected: { borderColor: "#aeb9ff", backgroundColor: "#f3f4ff" },
  runIcon: { width: 27, height: 27, borderRadius: 8, borderWidth: StyleSheet.hairlineWidth, borderColor: "#d8dce4", backgroundColor: "#fff", alignItems: "center", justifyContent: "center" },
  runCopy: { flex: 1, minWidth: 0 },
  runTitle: { color: "#242936", fontSize: 9, fontWeight: "700" },
  runMeta: { color: "#8a93a4", fontSize: 7.2, marginTop: 3 },
  runStatus: { color: "#657082", fontSize: 7.2, fontWeight: "800" },
});
