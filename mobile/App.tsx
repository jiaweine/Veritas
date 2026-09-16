import * as DocumentPicker from "expo-document-picker";
import React, { useCallback, useEffect, useMemo, useState } from "react";
import {
  ActivityIndicator,
  Alert,
  FlatList,
  KeyboardAvoidingView,
  Platform,
  Pressable,
  RefreshControl,
  SafeAreaView,
  ScrollView,
  StatusBar,
  StyleSheet,
  Text,
  TextInput,
  View,
} from "react-native";

import ReplicationScreen from "./ReplicationScreen";

const API_BASE = (process.env.EXPO_PUBLIC_VERITAS_API_URL || "http://127.0.0.1:8765").replace(/\/$/, "");

type Audit = {
  audit_id: string;
  title: string;
  filename: string;
  status: string;
  updated_at: string;
  paper_summary?: { pages?: number; words?: number; tables_detected?: number };
  latest_result?: {
    status?: string;
    verification_coverage?: number;
    counts?: { verified?: number; needs_review?: number; contradictions?: number };
    findings?: Array<{ title?: string; explanation?: string }>;
    source?: { page?: number; table?: string; row?: string };
  } | null;
  events?: Array<{ event_id: string; kind: string; title: string; detail?: string; status?: string; created_at?: string }>;
};

type Overview = {
  audits_total: number;
  papers_pages: number;
  checks_verified: number;
  checks_review: number;
  checks_contradictions: number;
  mean_coverage: number;
};

type Finding = {
  finding_id: string;
  audit_id: string;
  audit_title: string;
  title: string;
  explanation: string;
  severity: string;
  source?: { page?: number; table?: string };
};

type Tab = "overview" | "audits" | "findings" | "reproduction";

async function request(path: string, init?: RequestInit) {
  const response = await fetch(`${API_BASE}${path}`, init);
  if (!response.ok) {
    let message = `${response.status} ${response.statusText}`;
    try { message = (await response.json()).detail || message; } catch {}
    throw new Error(message);
  }
  return response;
}

const percent = (value?: number) => `${Math.round((value || 0) * 100)}%`;
const number = (value?: number) => new Intl.NumberFormat().format(value || 0);

function StatusPill({ value }: { value?: string }) {
  const tone = value === "error" || value === "danger" || value === "contradiction" ? styles.badPill
    : value === "running" || value === "info" ? styles.infoPill : styles.goodPill;
  return <View style={[styles.pill, tone]}><Text style={styles.pillText}>{(value || "ready").replaceAll("_", " ")}</Text></View>;
}

function Metric({ label, value, foot }: { label: string; value: string; foot: string }) {
  return <View style={styles.metricCard}><Text style={styles.metricLabel}>{label}</Text><Text style={styles.metricValue}>{value}</Text><Text style={styles.metricFoot}>{foot}</Text></View>;
}

export default function App() {
  const [tab, setTab] = useState<Tab>("overview");
  const [overview, setOverview] = useState<Overview | null>(null);
  const [audits, setAudits] = useState<Audit[]>([]);
  const [findings, setFindings] = useState<Finding[]>([]);
  const [activeAudit, setActiveAudit] = useState<Audit | null>(null);
  const [refreshing, setRefreshing] = useState(false);
  const [sending, setSending] = useState(false);
  const [message, setMessage] = useState("");

  const load = useCallback(async () => {
    try {
      const [o, a, f] = await Promise.all([
        request("/api/v1/overview").then((r) => r.json()),
        request("/api/v1/audits").then((r) => r.json()),
        request("/api/v1/findings").then((r) => r.json()),
      ]);
      setOverview(o);
      setAudits(a);
      setFindings(f);
      if (activeAudit) {
        const next = await request(`/api/v1/audits/${encodeURIComponent(activeAudit.audit_id)}`).then((r) => r.json());
        setActiveAudit(next);
      }
    } catch (error) {
      Alert.alert("Cannot reach Veritas", error instanceof Error ? error.message : String(error));
    }
  }, [activeAudit?.audit_id]);

  useEffect(() => { load(); }, []);

  const refresh = async () => {
    setRefreshing(true);
    await load();
    setRefreshing(false);
  };

  const openAudit = async (id: string) => {
    try {
      const audit = await request(`/api/v1/audits/${encodeURIComponent(id)}`).then((r) => r.json());
      setActiveAudit(audit);
    } catch (error) {
      Alert.alert("Unable to open audit", String(error));
    }
  };

  const uploadPdf = async () => {
    const result = await DocumentPicker.getDocumentAsync({ type: "application/pdf", copyToCacheDirectory: true });
    if (result.canceled || !result.assets[0]) return;
    const asset = result.assets[0];
    const body = new FormData();
    body.append("title", asset.name.replace(/\.pdf$/i, ""));
    body.append("file", { uri: asset.uri, name: asset.name, type: asset.mimeType || "application/pdf" } as never);
    try {
      setRefreshing(true);
      const audit = await request("/api/v1/audits", { method: "POST", body }).then((r) => r.json());
      await load();
      setActiveAudit(audit);
    } catch (error) {
      Alert.alert("Upload failed", String(error));
    } finally {
      setRefreshing(false);
    }
  };

  const send = async () => {
    const text = message.trim();
    if (!activeAudit || !text || sending) return;
    setSending(true);
    setMessage("");
    try {
      const response = await request(`/api/v1/audits/${encodeURIComponent(activeAudit.audit_id)}/messages`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ message: text }),
      });
      await response.text();
      const next = await request(`/api/v1/audits/${encodeURIComponent(activeAudit.audit_id)}`).then((r) => r.json());
      setActiveAudit(next);
      await load();
    } catch (error) {
      Alert.alert("Audit command failed", String(error));
    } finally {
      setSending(false);
    }
  };

  if (activeAudit) {
    return <SafeAreaView style={styles.app}>
      <StatusBar barStyle="dark-content" />
      <AuditDetail audit={activeAudit} onBack={() => setActiveAudit(null)} message={message} setMessage={setMessage} send={send} sending={sending} />
    </SafeAreaView>;
  }

  const tabs: Array<{ key: Tab; label: string; icon: string }> = [
    { key: "overview", label: "Overview", icon: "⌂" },
    { key: "audits", label: "Audits", icon: "▤" },
    { key: "findings", label: "Findings", icon: "◇" },
    { key: "reproduction", label: "Reproduce", icon: "↻" },
  ];

  return <SafeAreaView style={styles.app}>
    <StatusBar barStyle="dark-content" />
    <View style={styles.header}>
      <View><Text style={styles.brand}>Veritas</Text><Text style={styles.brandSub}>Research audit</Text></View>
      <Pressable style={styles.uploadButton} onPress={uploadPdf}><Text style={styles.uploadButtonText}>＋ Paper</Text></Pressable>
    </View>
    <View style={styles.body}>
      {tab === "overview" && <ScrollView refreshControl={<RefreshControl refreshing={refreshing} onRefresh={refresh} />} contentContainerStyle={styles.scroll}>
        <Text style={styles.eyebrow}>RESEARCH AUDIT COCKPIT</Text>
        <Text style={styles.title}>Evidence in view.</Text>
        <Text style={styles.subtitle}>Inspect real verification coverage, contradiction findings, and paper provenance from the same local-first harness.</Text>
        <View style={styles.metricGrid}>
          <Metric label="Papers" value={number(overview?.audits_total)} foot={`${number(overview?.papers_pages)} pages`} />
          <Metric label="Coverage" value={percent(overview?.mean_coverage)} foot="mean verified scope" />
          <Metric label="Verified" value={number(overview?.checks_verified)} foot={`${number(overview?.checks_review)} review`} />
          <Metric label="Contradictions" value={number(overview?.checks_contradictions)} foot="evidence-linked" />
        </View>
        <SectionTitle title="Recent audits" action="All" onPress={() => setTab("audits")} />
        {audits.slice(0, 5).map((audit) => <AuditRow key={audit.audit_id} audit={audit} onPress={() => openAudit(audit.audit_id)} />)}
        {!audits.length && <Empty text="Upload a PDF to create the first audit workspace." />}
        <SectionTitle title="Needs attention" action="Findings" onPress={() => setTab("findings")} />
        {findings.slice(0, 4).map((finding) => <FindingRow key={finding.finding_id} finding={finding} onPress={() => openAudit(finding.audit_id)} />)}
        {!findings.length && <Empty text="No contradiction findings in the latest detector results." />}
        <SectionTitle title="Reproduction" action="Open" onPress={() => setTab("reproduction")} />
        <View style={styles.reproductionPromo}><Text style={styles.rowTitle}>ACP replication workspace</Text><Text style={styles.rowSub}>Use the server-selected agent with fail-closed permissions and inspect the structured execution trace.</Text></View>
      </ScrollView>}
      {tab === "audits" && <FlatList data={audits} keyExtractor={(x) => x.audit_id} contentContainerStyle={styles.list} refreshControl={<RefreshControl refreshing={refreshing} onRefresh={refresh} />} ListHeaderComponent={<><Text style={styles.eyebrow}>WORKSPACE</Text><Text style={styles.title}>Audits</Text><Text style={styles.subtitle}>Immutable papers, deterministic checks, inspectable provenance.</Text></>} ListEmptyComponent={<Empty text="No audits yet." />} renderItem={({ item }) => <AuditRow audit={item} onPress={() => openAudit(item.audit_id)} />} />}
      {tab === "findings" && <FlatList data={findings} keyExtractor={(x) => x.finding_id} contentContainerStyle={styles.list} refreshControl={<RefreshControl refreshing={refreshing} onRefresh={refresh} />} ListHeaderComponent={<><Text style={styles.eyebrow}>EVIDENCE REVIEW</Text><Text style={styles.title}>Findings</Text><Text style={styles.subtitle}>Contradictions remain attached to source context.</Text></>} ListEmptyComponent={<Empty text="No contradiction findings." />} renderItem={({ item }) => <FindingRow finding={item} onPress={() => openAudit(item.audit_id)} />} />}
      {tab === "reproduction" && <ReplicationScreen audits={audits} />}
    </View>
    <View style={styles.tabbar}>{tabs.map((item) => <Pressable key={item.key} onPress={() => setTab(item.key)} style={styles.tab}><Text style={[styles.tabIcon, tab === item.key && styles.tabActive]}>{item.icon}</Text><Text style={[styles.tabLabel, tab === item.key && styles.tabActive]}>{item.label}</Text></Pressable>)}</View>
  </SafeAreaView>;
}

function SectionTitle({ title, action, onPress }: { title: string; action: string; onPress: () => void }) {
  return <View style={styles.sectionHead}><Text style={styles.sectionTitle}>{title}</Text><Pressable onPress={onPress}><Text style={styles.link}>{action} →</Text></Pressable></View>;
}

function AuditRow({ audit, onPress }: { audit: Audit; onPress: () => void }) {
  return <Pressable style={styles.rowCard} onPress={onPress}><View style={styles.rowMain}><Text style={styles.rowTitle} numberOfLines={1}>{audit.title}</Text><Text style={styles.rowSub}>{audit.paper_summary?.pages || 0} pages · {audit.paper_summary?.tables_detected || 0} tables · {percent(audit.latest_result?.verification_coverage)}</Text></View><StatusPill value={audit.status} /></Pressable>;
}

function FindingRow({ finding, onPress }: { finding: Finding; onPress: () => void }) {
  return <Pressable style={styles.findingCard} onPress={onPress}><View style={styles.findingMark}><Text style={styles.findingMarkText}>!</Text></View><View style={styles.rowMain}><Text style={styles.rowTitle}>{finding.title}</Text><Text style={styles.rowSub} numberOfLines={2}>{finding.audit_title} · {finding.source?.table || "source"}{finding.source?.page ? ` · p.${finding.source.page}` : ""}</Text></View></Pressable>;
}

function Empty({ text }: { text: string }) {
  return <View style={styles.empty}><Text style={styles.emptyText}>{text}</Text></View>;
}

function AuditDetail({ audit, onBack, message, setMessage, send, sending }: { audit: Audit; onBack: () => void; message: string; setMessage: (value: string) => void; send: () => void; sending: boolean }) {
  const events = useMemo(() => [...(audit.events || [])].reverse().slice(0, 12), [audit.events]);
  const result = audit.latest_result;
  return <KeyboardAvoidingView style={styles.app} behavior={Platform.OS === "ios" ? "padding" : undefined}>
    <View style={styles.detailHeader}><Pressable onPress={onBack} style={styles.back}><Text style={styles.backText}>‹</Text></Pressable><View style={styles.detailHeaderCopy}><Text style={styles.detailTitle} numberOfLines={1}>{audit.title}</Text><Text style={styles.rowSub}>{audit.paper_summary?.pages || 0} pages · {audit.paper_summary?.tables_detected || 0} tables</Text></View><StatusPill value={audit.status} /></View>
    <ScrollView style={styles.detailScroll} contentContainerStyle={styles.detailContent}>
      <Text style={styles.eyebrow}>LATEST RESULT</Text>
      <View style={styles.resultCard}><View style={styles.resultTop}><Text style={styles.resultTitle}>{result ? (result.status === "verified" ? "Values internally consistent" : result.status === "contradiction" ? "Reporting contradiction" : "Review required") : "No detector result yet"}</Text>{result && <StatusPill value={result.status} />}</View><Text style={styles.resultMeta}>{result?.source?.table || "Use the Audit Agent below"}{result?.source?.page ? ` · page ${result.source.page}` : ""}</Text>{result && <View style={styles.resultMetrics}><MiniMetric label="Verified" value={result.counts?.verified || 0} /><MiniMetric label="Review" value={result.counts?.needs_review || 0} /><MiniMetric label="Contradiction" value={result.counts?.contradictions || 0} /></View>}</View>
      <Text style={[styles.eyebrow, { marginTop: 20 }]}>TRACE</Text>
      {events.map((event) => <View style={styles.traceRow} key={event.event_id}><View style={styles.traceDot}><Text style={styles.traceDotText}>{event.kind === "tool" ? "⌁" : event.kind === "finding" ? "!" : event.kind === "replication" ? "↻" : "·"}</Text></View><View style={styles.traceCard}><Text style={styles.rowTitle}>{event.title}</Text>{event.detail ? <Text style={styles.rowSub}>{event.detail}</Text> : null}</View></View>)}
      {!events.length && <Empty text="Run /inspect or /audit to start the trace." />}
    </ScrollView>
    <View style={styles.composer}><View style={styles.commandRow}><Pressable onPress={() => setMessage("/inspect")}><Text style={styles.command}>Inspect</Text></Pressable><Pressable onPress={() => setMessage('/audit row="Treatment" table=2 page=1')}><Text style={styles.command}>Audit row</Text></Pressable></View><View style={styles.composerLine}><TextInput value={message} onChangeText={setMessage} multiline placeholder="Ask the audit harness…" style={styles.input} editable={!sending} /><Pressable onPress={send} disabled={sending || !message.trim()} style={[styles.send, (sending || !message.trim()) && styles.sendDisabled]}>{sending ? <ActivityIndicator size="small" color="#fff" /> : <Text style={styles.sendText}>↑</Text>}</Pressable></View></View>
  </KeyboardAvoidingView>;
}

function MiniMetric({ label, value }: { label: string; value: number }) {
  return <View style={styles.miniMetric}><Text style={styles.metricLabel}>{label}</Text><Text style={styles.miniMetricValue}>{value}</Text></View>;
}

const styles = StyleSheet.create({
  app: { flex: 1, backgroundColor: "#f6f7f9" },
  header: { height: 60, paddingHorizontal: 18, backgroundColor: "#fff", borderBottomWidth: StyleSheet.hairlineWidth, borderBottomColor: "#e4e7ec", flexDirection: "row", alignItems: "center", justifyContent: "space-between" },
  brand: { fontSize: 17, fontWeight: "800", color: "#151927", letterSpacing: -0.3 }, brandSub: { fontSize: 9, color: "#8a93a4", marginTop: 1 },
  uploadButton: { backgroundColor: "#5368f5", paddingHorizontal: 13, height: 34, borderRadius: 9, justifyContent: "center" }, uploadButtonText: { color: "#fff", fontSize: 11, fontWeight: "700" },
  body: { flex: 1 }, scroll: { padding: 16, paddingBottom: 26 }, list: { padding: 16, paddingBottom: 26 },
  eyebrow: { color: "#5368f5", fontSize: 9, fontWeight: "800", letterSpacing: 1.1, marginBottom: 7 },
  title: { color: "#151927", fontSize: 27, fontWeight: "800", letterSpacing: -0.7 }, subtitle: { color: "#626b7d", fontSize: 11, lineHeight: 17, marginTop: 6, marginBottom: 17 },
  metricGrid: { flexDirection: "row", flexWrap: "wrap", gap: 8, marginBottom: 20 }, metricCard: { width: "48.6%", minHeight: 105, backgroundColor: "#fff", borderWidth: StyleSheet.hairlineWidth, borderColor: "#e4e7ec", borderRadius: 12, padding: 13 }, metricLabel: { fontSize: 9, color: "#626b7d", fontWeight: "600" }, metricValue: { fontSize: 22, color: "#151927", fontWeight: "800", marginTop: 9, letterSpacing: -0.5 }, metricFoot: { fontSize: 8.5, color: "#8a93a4", marginTop: 7 },
  sectionHead: { flexDirection: "row", alignItems: "center", justifyContent: "space-between", marginTop: 4, marginBottom: 8 }, sectionTitle: { fontSize: 13, color: "#151927", fontWeight: "700" }, link: { color: "#687284", fontSize: 9 },
  reproductionPromo: { minHeight: 72, backgroundColor: "#eef0ff", borderWidth: StyleSheet.hairlineWidth, borderColor: "#cfd5ff", borderRadius: 11, padding: 12, marginBottom: 6 },
  rowCard: { minHeight: 67, backgroundColor: "#fff", borderWidth: StyleSheet.hairlineWidth, borderColor: "#e4e7ec", borderRadius: 11, paddingHorizontal: 12, paddingVertical: 11, marginBottom: 7, flexDirection: "row", alignItems: "center", gap: 10 }, rowMain: { flex: 1 }, rowTitle: { color: "#242936", fontSize: 11, fontWeight: "700" }, rowSub: { color: "#8a93a4", fontSize: 8.5, marginTop: 4, lineHeight: 12 },
  pill: { borderRadius: 999, paddingHorizontal: 7, paddingVertical: 4 }, goodPill: { backgroundColor: "#eaf8f3" }, infoPill: { backgroundColor: "#eef0ff" }, badPill: { backgroundColor: "#fff0f1" }, pillText: { color: "#536273", fontSize: 7.5, fontWeight: "700" },
  findingCard: { minHeight: 70, backgroundColor: "#fff", borderWidth: StyleSheet.hairlineWidth, borderColor: "#e4e7ec", borderRadius: 11, padding: 11, marginBottom: 7, flexDirection: "row", gap: 10, alignItems: "flex-start" }, findingMark: { width: 30, height: 30, borderRadius: 9, backgroundColor: "#fff0f1", alignItems: "center", justifyContent: "center" }, findingMarkText: { color: "#c74550", fontWeight: "900" },
  empty: { minHeight: 90, borderWidth: StyleSheet.hairlineWidth, borderStyle: "dashed", borderColor: "#d8dce4", borderRadius: 11, alignItems: "center", justifyContent: "center", padding: 18, marginBottom: 12 }, emptyText: { color: "#8a93a4", fontSize: 9.5, textAlign: "center" },
  tabbar: { height: 58, backgroundColor: "#fff", borderTopWidth: StyleSheet.hairlineWidth, borderTopColor: "#e4e7ec", flexDirection: "row", justifyContent: "space-around", alignItems: "center" }, tab: { flex: 1, alignItems: "center", gap: 2 }, tabIcon: { color: "#9099a8", fontSize: 17 }, tabLabel: { color: "#9099a8", fontSize: 7.5 }, tabActive: { color: "#4054d5", fontWeight: "700" },
  detailHeader: { height: 62, backgroundColor: "#fff", borderBottomWidth: StyleSheet.hairlineWidth, borderBottomColor: "#e4e7ec", flexDirection: "row", alignItems: "center", paddingHorizontal: 11, gap: 8 }, back: { width: 32, height: 32, alignItems: "center", justifyContent: "center" }, backText: { fontSize: 30, color: "#505a6b", lineHeight: 30 }, detailHeaderCopy: { flex: 1 }, detailTitle: { fontSize: 12, color: "#151927", fontWeight: "700" }, detailScroll: { flex: 1 }, detailContent: { padding: 15, paddingBottom: 22 },
  resultCard: { backgroundColor: "#fff", borderWidth: StyleSheet.hairlineWidth, borderColor: "#e4e7ec", borderRadius: 12, padding: 14 }, resultTop: { flexDirection: "row", alignItems: "flex-start", justifyContent: "space-between", gap: 10 }, resultTitle: { flex: 1, color: "#151927", fontSize: 13, fontWeight: "700" }, resultMeta: { color: "#8a93a4", fontSize: 9, marginTop: 5 }, resultMetrics: { flexDirection: "row", gap: 7, marginTop: 13 }, miniMetric: { flex: 1, borderRadius: 9, backgroundColor: "#f7f8fa", padding: 9 }, miniMetricValue: { color: "#151927", fontSize: 18, fontWeight: "800", marginTop: 4 },
  traceRow: { flexDirection: "row", gap: 8, marginBottom: 8 }, traceDot: { width: 24, height: 24, borderRadius: 12, borderWidth: StyleSheet.hairlineWidth, borderColor: "#d8dce4", backgroundColor: "#fff", alignItems: "center", justifyContent: "center" }, traceDotText: { color: "#697385", fontSize: 9, fontWeight: "800" }, traceCard: { flex: 1, backgroundColor: "#fff", borderWidth: StyleSheet.hairlineWidth, borderColor: "#e4e7ec", borderRadius: 9, padding: 10 },
  composer: { backgroundColor: "#fff", borderTopWidth: StyleSheet.hairlineWidth, borderTopColor: "#e4e7ec", padding: 10 }, commandRow: { flexDirection: "row", gap: 7, marginBottom: 7 }, command: { borderWidth: StyleSheet.hairlineWidth, borderColor: "#d8dce4", borderRadius: 7, paddingHorizontal: 8, paddingVertical: 5, color: "#657082", fontSize: 8.5 }, composerLine: { flexDirection: "row", alignItems: "flex-end", borderWidth: StyleSheet.hairlineWidth, borderColor: "#d8dce4", borderRadius: 10, padding: 6, gap: 7 }, input: { flex: 1, minHeight: 34, maxHeight: 95, paddingHorizontal: 4, paddingVertical: 6, color: "#151927", fontSize: 10 }, send: { width: 32, height: 32, borderRadius: 8, backgroundColor: "#5368f5", alignItems: "center", justifyContent: "center" }, sendDisabled: { opacity: 0.35 }, sendText: { color: "#fff", fontSize: 17, fontWeight: "800" },
});
