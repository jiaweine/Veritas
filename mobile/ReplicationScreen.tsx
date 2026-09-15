import React, { useEffect, useMemo, useState } from "react";
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
};

type HarnessEvent = {
  event_id: string;
  kind: string;
  title: string;
  detail?: string;
  status?: string;
  payload?: {
    run_id?: string;
    phase?: string;
    duration_ms?: number;
  };
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

function CapabilityRow({ label, value }: { label: string; value: string }) {
  return <View style={styles.capabilityRow}><Text style={styles.capabilityLabel}>{label}</Text><Text style={styles.capabilityValue}>{value}</Text></View>;
}

function EventRow({ event }: { event: HarnessEvent }) {
  const phase = event.payload?.phase ? ` · ${event.payload.phase}` : "";
  const duration = event.payload?.duration_ms != null ? ` · ${Math.round(event.payload.duration_ms)} ms` : "";
  const icon = event.kind === "tool" ? "⌁" : event.kind === "replication" ? "↻" : "·";
  const danger = event.status === "danger" || event.status === "error";
  return <View style={styles.eventRow}>
    <View style={[styles.eventIcon, danger && styles.eventIconDanger]}><Text style={styles.eventIconText}>{icon}</Text></View>
    <View style={styles.eventCard}>
      <View style={styles.eventTop}><Text style={styles.eventTitle}>{event.title}</Text><Text style={[styles.eventStatus, danger && styles.eventStatusDanger]}>{event.status || "info"}</Text></View>
      {event.detail ? <Text style={styles.eventDetail}>{event.detail}</Text> : null}
      <Text style={styles.eventMeta}>{event.kind}{phase}{duration}</Text>
    </View>
  </View>;
}

export default function ReplicationScreen({ audits }: { audits: AuditOption[] }) {
  const [capability, setCapability] = useState<ReplicationCapability | null>(null);
  const [selectedAudit, setSelectedAudit] = useState<string>(audits[0]?.audit_id || "");
  const [prompt, setPrompt] = useState("Reproduce the paper's main reported result and record the environment, steps, outputs, and discrepancies.");
  const [events, setEvents] = useState<HarnessEvent[]>([]);
  const [running, setRunning] = useState(false);

  useEffect(() => {
    if (!selectedAudit && audits[0]) setSelectedAudit(audits[0].audit_id);
    if (selectedAudit && !audits.some((audit) => audit.audit_id === selectedAudit)) {
      setSelectedAudit(audits[0]?.audit_id || "");
    }
  }, [audits, selectedAudit]);

  useEffect(() => {
    request("/api/v1/capabilities")
      .then((response) => response.json())
      .then((value) => setCapability(value.replication || { configured: false }))
      .catch((error) => Alert.alert("Replication capability unavailable", String(error)));
  }, []);

  const selectedTitle = useMemo(
    () => audits.find((audit) => audit.audit_id === selectedAudit)?.title || "No paper selected",
    [audits, selectedAudit],
  );

  const run = async () => {
    const goal = prompt.trim();
    if (!selectedAudit || !goal || running) return;
    setRunning(true);
    setEvents([]);
    try {
      const response = await request(`/api/v1/audits/${encodeURIComponent(selectedAudit)}/replication`, {
        method: "POST",
        headers: { "Content-Type": "application/json", Accept: "application/x-ndjson" },
        body: JSON.stringify({ prompt: goal }),
      });
      const text = await response.text();
      const parsed = text.split("\n").filter(Boolean).map((line) => JSON.parse(line) as HarnessEvent);
      setEvents(parsed);
    } catch (error) {
      Alert.alert("Replication run failed", error instanceof Error ? error.message : String(error));
    } finally {
      setRunning(false);
    }
  };

  const configured = Boolean(capability?.configured);
  return <ScrollView contentContainerStyle={styles.page} keyboardShouldPersistTaps="handled">
    <Text style={styles.eyebrow}>REPRODUCIBILITY</Text>
    <Text style={styles.title}>Reproduction</Text>
    <Text style={styles.subtitle}>Run the server-selected ACP agent against a paper-specific workspace. The app sends a goal, never an executable command.</Text>

    <View style={styles.card}>
      <View style={styles.cardHead}><Text style={styles.cardTitle}>Execution boundary</Text><View style={[styles.badge, configured ? styles.badgeReady : styles.badgeReview]}><Text style={styles.badgeText}>{configured ? "configured" : "fail-closed"}</Text></View></View>
      <CapabilityRow label="Agent" value={capability?.agent || "Not configured"} />
      <CapabilityRow label="Permission" value={capability?.permission_policy || "deny"} />
      <CapabilityRow label="Client commands" value={capability?.client_supplied_commands ? "allowed" : "disabled"} />
      <CapabilityRow label="Workspace sandbox" value={capability?.workspace_is_security_boundary ? "yes" : "agent-owned"} />
      {capability && capability.permission_policy_valid === false ? <Text style={styles.warning}>Invalid server policy detected; Veritas has fallen back to deny.</Text> : null}
    </View>

    <View style={styles.card}>
      <Text style={styles.cardTitle}>Paper</Text>
      <Text style={styles.selectedTitle}>{selectedTitle}</Text>
      <ScrollView horizontal showsHorizontalScrollIndicator={false} contentContainerStyle={styles.auditChips}>
        {audits.map((audit) => <Pressable key={audit.audit_id} onPress={() => setSelectedAudit(audit.audit_id)} style={[styles.auditChip, selectedAudit === audit.audit_id && styles.auditChipActive]}><Text numberOfLines={1} style={[styles.auditChipText, selectedAudit === audit.audit_id && styles.auditChipTextActive]}>{audit.title}</Text></Pressable>)}
      </ScrollView>
      {!audits.length ? <Text style={styles.empty}>Upload a paper before starting a reproduction run.</Text> : null}

      <Text style={styles.fieldLabel}>Goal</Text>
      <TextInput value={prompt} onChangeText={setPrompt} multiline editable={!running && configured} style={styles.input} placeholder="Describe the reproduction goal…" placeholderTextColor="#9aa2b1" />
      <Pressable onPress={run} disabled={!configured || !selectedAudit || !prompt.trim() || running} style={[styles.runButton, (!configured || !selectedAudit || !prompt.trim() || running) && styles.runButtonDisabled]}>
        {running ? <ActivityIndicator color="#fff" /> : <Text style={styles.runButtonText}>Run reproduction</Text>}
      </Pressable>
      {!configured ? <Text style={styles.helper}>Configure VERITAS_REPLICATION_AGENT on the server to enable this control.</Text> : <Text style={styles.helper}>ACP permission policy defaults to deny. The local workspace is not presented as a security sandbox.</Text>}
    </View>

    <View style={styles.traceHead}><Text style={styles.cardTitle}>Run trace</Text><Text style={styles.traceCount}>{events.length} events</Text></View>
    {events.map((event) => <EventRow key={event.event_id} event={event} />)}
    {!events.length ? <View style={styles.emptyTrace}><Text style={styles.empty}>No replication trace in this session.</Text></View> : null}
  </ScrollView>;
}

const styles = StyleSheet.create({
  page: { padding: 16, paddingBottom: 30 },
  eyebrow: { color: "#5368f5", fontSize: 9, fontWeight: "800", letterSpacing: 1.1, marginBottom: 7 },
  title: { color: "#151927", fontSize: 27, fontWeight: "800", letterSpacing: -0.7 },
  subtitle: { color: "#626b7d", fontSize: 11, lineHeight: 17, marginTop: 6, marginBottom: 17 },
  card: { backgroundColor: "#fff", borderWidth: StyleSheet.hairlineWidth, borderColor: "#e4e7ec", borderRadius: 12, padding: 14, marginBottom: 10 },
  cardHead: { flexDirection: "row", alignItems: "center", justifyContent: "space-between", gap: 10, marginBottom: 8 },
  cardTitle: { color: "#202532", fontSize: 12, fontWeight: "800" },
  badge: { borderRadius: 999, paddingHorizontal: 8, paddingVertical: 4 },
  badgeReady: { backgroundColor: "#eaf8f3" },
  badgeReview: { backgroundColor: "#fff6df" },
  badgeText: { color: "#596273", fontSize: 7.5, fontWeight: "800" },
  capabilityRow: { minHeight: 31, flexDirection: "row", alignItems: "center", justifyContent: "space-between", borderBottomWidth: StyleSheet.hairlineWidth, borderBottomColor: "#eef0f3" },
  capabilityLabel: { color: "#7c8595", fontSize: 9 },
  capabilityValue: { color: "#202532", fontSize: 9, fontWeight: "700", maxWidth: "56%", textAlign: "right" },
  warning: { marginTop: 10, padding: 9, borderRadius: 8, backgroundColor: "#fff6df", color: "#8a651c", fontSize: 8.5, lineHeight: 13 },
  selectedTitle: { color: "#657082", fontSize: 9, marginTop: 6 },
  auditChips: { gap: 7, paddingVertical: 10 },
  auditChip: { maxWidth: 180, borderWidth: StyleSheet.hairlineWidth, borderColor: "#d8dce4", borderRadius: 999, paddingHorizontal: 10, paddingVertical: 7, backgroundColor: "#fafbfc" },
  auditChipActive: { borderColor: "#aeb9ff", backgroundColor: "#eef0ff" },
  auditChipText: { color: "#687284", fontSize: 8.5 },
  auditChipTextActive: { color: "#4054d5", fontWeight: "700" },
  fieldLabel: { color: "#596273", fontSize: 9, fontWeight: "700", marginTop: 4, marginBottom: 6 },
  input: { minHeight: 112, borderWidth: StyleSheet.hairlineWidth, borderColor: "#d8dce4", borderRadius: 10, padding: 10, color: "#151927", fontSize: 10, lineHeight: 15, textAlignVertical: "top", backgroundColor: "#fdfdfe" },
  runButton: { minHeight: 42, borderRadius: 10, backgroundColor: "#5368f5", alignItems: "center", justifyContent: "center", marginTop: 10 },
  runButtonDisabled: { opacity: 0.35 },
  runButtonText: { color: "#fff", fontSize: 10.5, fontWeight: "800" },
  helper: { color: "#8a93a4", fontSize: 8, lineHeight: 12, marginTop: 8 },
  empty: { color: "#8a93a4", fontSize: 9, textAlign: "center", lineHeight: 13 },
  traceHead: { flexDirection: "row", alignItems: "center", justifyContent: "space-between", marginTop: 8, marginBottom: 8 },
  traceCount: { color: "#8a93a4", fontSize: 8 },
  eventRow: { flexDirection: "row", gap: 8, marginBottom: 8, alignItems: "flex-start" },
  eventIcon: { width: 26, height: 26, borderRadius: 13, borderWidth: StyleSheet.hairlineWidth, borderColor: "#d8dce4", backgroundColor: "#fff", alignItems: "center", justifyContent: "center" },
  eventIconDanger: { borderColor: "#efc8cc", backgroundColor: "#fff0f1" },
  eventIconText: { color: "#697385", fontSize: 9, fontWeight: "800" },
  eventCard: { flex: 1, backgroundColor: "#fff", borderWidth: StyleSheet.hairlineWidth, borderColor: "#e4e7ec", borderRadius: 10, padding: 10 },
  eventTop: { flexDirection: "row", alignItems: "flex-start", justifyContent: "space-between", gap: 8 },
  eventTitle: { flex: 1, color: "#242936", fontSize: 10, fontWeight: "700" },
  eventStatus: { color: "#657082", fontSize: 7.5, fontWeight: "700" },
  eventStatusDanger: { color: "#b63e49" },
  eventDetail: { color: "#687284", fontSize: 8.5, lineHeight: 13, marginTop: 5 },
  eventMeta: { color: "#9aa2b1", fontSize: 7.5, marginTop: 6 },
  emptyTrace: { minHeight: 100, borderWidth: StyleSheet.hairlineWidth, borderStyle: "dashed", borderColor: "#d8dce4", borderRadius: 11, alignItems: "center", justifyContent: "center", padding: 16 },
});
