import React, { useEffect, useMemo, useState } from 'react';
import {
  Activity,
  AlertTriangle,
  Bot,
  BarChart3,
  Clock,
  FileSearch,
  Send,
  ShieldCheck,
  Sparkles,
  Trash2,
} from 'lucide-react';
import { api } from '../api.js';

const SUGGESTED_CHAT_PROMPTS = [
  'What is happening across the HPC cluster right now, and which nodes need attention?',
  'Which active Slurm jobs could be affected by current anomalies or resource pressure?',
  'Compare V7 Isolation Forest findings against LSTM V8 warning scores separately without combining them.',
  'What should an administrator investigate next based on live telemetry and recent incidents?',
];

export default function AiIntelligencePage({
  snapshot,
  user,
  selectedNodeId,
  initialEpisodeId = null,
  onNavigate,
  showToast,
}) {
  const [tab, setTab] = useState(initialEpisodeId ? 'investigate' : 'chat');
  const [sessionId, setSessionId] = useState(() => `ops-${new Date().toISOString().slice(0, 10)}`);
  const [messages, setMessages] = useState([]);
  const [geminiMeta, setGeminiMeta] = useState({ configured: null, model: '--' });

  // Chat state
  const [chatInput, setChatInput] = useState('');
  const [rangeMinutes, setRangeMinutes] = useState(60);
  const [sending, setSending] = useState(false);

  // Incident Investigation state
  const [targetEpId, setTargetEpId] = useState(initialEpisodeId || '');
  const [targetNode, setTargetNode] = useState(selectedNodeId || '');
  const [invQuestion, setInvQuestion] = useState(
    'Analyse observed telemetry, V7 score, LSTM V8 state, logs, and Slurm job impact. Separate confirmed measurements from hypotheses.'
  );
  const [invResult, setInvResult] = useState(null);

  // Natural-language analytics state
  const [analyticsRange, setAnalyticsRange] = useState('24h');
  const [analyticsQuestion, setAnalyticsQuestion] = useState(
    'Summarize cluster utilization bottlenecks, repeated node anomalies, and model detection differences over this window.'
  );
  const [analyticsResult, setAnalyticsResult] = useState(null);

  const nodes = snapshot?.nodes || [];
  const episodes = snapshot?.alert_episodes || [];

  useEffect(() => {
    if (initialEpisodeId) {
      setTab('investigate');
      setTargetEpId(String(initialEpisodeId));
    }
  }, [initialEpisodeId]);

  const loadContext = async () => {
    try {
      const [histRes, setRes] = await Promise.all([
        api.getAiHistory(sessionId, 80),
        api.getSettings(),
      ]);
      setMessages(histRes?.messages || []);
      const g = setRes?.service_health?.gemini || {};
      setGeminiMeta({ configured: Boolean(g.configured), model: g.model || '--' });
    } catch {
      // Ignore transient load error
    }
  };

  useEffect(() => {
    loadContext();
  }, [sessionId]);

  const selectedEpObj = useMemo(
    () => episodes.find((e) => String(e.id) === String(targetEpId)) || null,
    [episodes, targetEpId]
  );

  const handleSendChat = async (promptOverride = null) => {
    const q = (promptOverride ?? chatInput).trim();
    if (!q || sending) return;
    setSending(true);
    try {
      const res = await api.aiChat(q, sessionId, rangeMinutes);
      if (!promptOverride) setChatInput('');
      await loadContext();
      if (res?.answer) {
        showToast?.(`Gemini replied (${res.model})`);
      }
    } catch (err) {
      showToast?.(`Gemini assistant error: ${err.message}`);
    } finally {
      setSending(false);
    }
  };

  const handleInvestigate = async (e) => {
    e?.preventDefault();
    if (sending) return;
    setSending(true);
    try {
      const res = await api.aiInvestigateIncident({
        episode_id: targetEpId ? Number(targetEpId) : null,
        node_id: targetNode || null,
        question: invQuestion,
        session_id: sessionId,
      });
      setInvResult(res);
      await loadContext();
      showToast?.(`Incident investigation completed via ${res.model}`);
    } catch (err) {
      showToast?.(`Investigation failed: ${err.message}`);
    } finally {
      setSending(false);
    }
  };

  const handleRunAnalytics = async (e) => {
    e?.preventDefault();
    if (!analyticsQuestion.trim() || sending) return;
    setSending(true);
    try {
      const res = await api.aiQueryAnalytics(analyticsQuestion, analyticsRange, sessionId);
      setAnalyticsResult(res);
      await loadContext();
      showToast?.(`Cluster analytics completed via ${res.model}`);
    } catch (err) {
      showToast?.(`Analytics query failed: ${err.message}`);
    } finally {
      setSending(false);
    }
  };

  return (
    <div className="space-y-5">
      {/* Header */}
      <div className="flex flex-wrap items-center justify-between gap-3">
        <div className="flex items-center gap-3">
          <div className="flex h-10 w-10 items-center justify-center rounded-xl bg-cyan-500/15 text-[var(--accent-cyan)]">
            <Sparkles className="h-5 w-5" />
          </div>
          <div>
            <h2 className="text-xl font-bold tracking-tight">AI Intelligence Centre</h2>
            
          </div>
        </div>

        <div className="flex flex-wrap items-center gap-2">
          <span
            className={`rounded-full px-3 py-1 font-mono text-[11px] font-bold uppercase ${
              geminiMeta.configured
                ? 'bg-emerald-500/15 text-emerald-400'
                : 'bg-rose-500/15 text-rose-400'
            }`}
          >
            Gemini: {geminiMeta.configured ? `Ready (${geminiMeta.model})` : 'Not Configured'}
          </span>

          <button
            onClick={() => onNavigate?.('reports')}
            className="spu-btn-secondary inline-flex items-center gap-1.5 text-xs"
          >
            <BarChart3 className="h-3.5 w-3.5 text-[var(--accent-cyan)]" />
            AI Reports Archive
          </button>
        </div>
      </div>


      {/* Sub-mode Tabs */}
      <div className="spu-subcard inline-flex flex-wrap gap-1 p-1 text-xs">
        {[
          { id: 'chat', label: 'Conversational HPC Assistant', icon: Bot },
          { id: 'investigate', label: 'Incident & Anomaly Investigation', icon: FileSearch },
          { id: 'analytics', label: 'Natural-Language Cluster Analytics', icon: BarChart3 },
        ].map((item) => {
          const Icon = item.icon;
          return (
            <button
              key={item.id}
              onClick={() => setTab(item.id)}
              className={`inline-flex items-center gap-1.5 rounded-md px-3 py-1.5 font-semibold transition ${
                tab === item.id
                  ? 'bg-[var(--accent-cyan-strong)] text-white'
                  : 'spu-text-secondary hover:text-[var(--text-primary)]'
              }`}
            >
              <Icon className="h-3.5 w-3.5" />
              {item.label}
            </button>
          );
        })}
      </div>

      {/* TAB 1: CONVERSATIONAL ASSISTANT */}
      {tab === 'chat' && (
        <div className="grid grid-cols-1 gap-5 xl:grid-cols-12">
          <div className="spu-card p-5 xl:col-span-8 flex flex-col justify-between min-h-[520px]">
            <div className="space-y-3 overflow-y-auto max-h-[420px] pr-1">
              {messages.length === 0 ? (
                <div className="py-12 text-center text-xs spu-text-secondary">
                  <Bot className="mx-auto mb-2 h-8 w-8 text-[var(--accent-cyan)] opacity-70" />
                  <p className="font-semibold text-[var(--text-primary)]">
                    Ask Gemini.
                  </p>
                  <p className="mt-1 spu-text-muted">
                   
                  </p>
                </div>
              ) : (
                messages.map((m) => (
                  <div
                    key={m.id}
                    className={`rounded-xl p-3.5 text-xs ${
                      m.role === 'user'
                        ? 'ml-8 border border-cyan-500/30 bg-cyan-500/10'
                        : 'mr-4 spu-subcard'
                    }`}
                  >
                    <div className="mb-1 flex items-center justify-between font-mono text-[10px] spu-text-muted">
                      <span>
                        {m.role === 'user' ? user?.email || 'Administrator' : `Gemini (${m.evidence?.model || geminiMeta.model})`} • {m.mode}
                      </span>
                      <span>{m.created_utc}</span>
                    </div>
                    <div className="whitespace-pre-wrap leading-relaxed text-[var(--text-primary)]">
                      {m.content}
                    </div>
                  </div>
                ))
              )}
            </div>

            <div className="mt-4 border-t pt-3 spu-border">
              <div className="mb-2 flex items-center justify-between text-[11px] spu-text-secondary">
                <span>Telemetry Context Window:</span>
                <select
                  value={rangeMinutes}
                  onChange={(e) => setRangeMinutes(Number(e.target.value))}
                  className="spu-input py-1 text-xs"
                >
                  <option value={15}>Last 15 minutes</option>
                  <option value={60}>Last 1 hour</option>
                  <option value={360}>Last 6 hours</option>
                  <option value={1440}>Last 24 hours</option>
                </select>
              </div>
              <div className="flex gap-2">
                <input
                  type="text"
                  value={chatInput}
                  onChange={(e) => setChatInput(e.target.value)}
                  onKeyDown={(e) => {
                    if (e.key === 'Enter' && !e.shiftKey) {
                      e.preventDefault();
                      handleSendChat();
                    }
                  }}
                  placeholder="Ask Gemini about cluster state, node anomalies, V7/LSTM signals, or Slurm jobs..."
                  className="spu-input flex-1 text-xs"
                />
                <button
                  onClick={() => handleSendChat()}
                  disabled={sending || !chatInput.trim()}
                  className="spu-btn-primary inline-flex items-center gap-1.5"
                >
                  <Send className="h-3.5 w-3.5" />
                  {sending ? 'Analysing...' : 'Send'}
                </button>
              </div>
            </div>
          </div>

          {/* Right rail: Quick Prompts & Live Context Summary */}
          <div className="space-y-4 xl:col-span-4">
            <div className="spu-card p-4">
              <h3 className="text-xs font-bold uppercase tracking-wider spu-text-secondary mb-2.5">
                Quick Operational Questions
              </h3>
              <div className="space-y-2">
                {SUGGESTED_CHAT_PROMPTS.map((q) => (
                  <button
                    key={q}
                    disabled={sending}
                    onClick={() => handleSendChat(q)}
                    className="w-full rounded-lg p-2.5 text-left text-xs spu-subcard hover:border-[var(--accent-cyan)] transition"
                  >
                    {q}
                  </button>
                ))}
              </div>
            </div>

            <div className="spu-card p-4 text-xs space-y-2">
              <h3 className="font-bold uppercase tracking-wider spu-text-secondary">
                Supplied Live Context Snapshot
              </h3>
              <div className="flex justify-between">
                <span className="spu-text-secondary">Online Nodes</span>
                <span className="font-mono font-bold">
                  {snapshot?.kpis?.nodes_online ?? 0} / {snapshot?.kpis?.nodes_total ?? 4}
                </span>
              </div>
              <div className="flex justify-between">
                <span className="spu-text-secondary">Active Incidents</span>
                <span className="font-mono font-bold">
                  {snapshot?.kpis?.active_episodes_total ?? 0}
                </span>
              </div>
              <div className="flex justify-between">
                <span className="spu-text-secondary">V7 Active Anomalies</span>
                <span className="font-mono font-bold">
                  {snapshot?.kpis?.nodes_with_v7_anomaly ?? 0}
                </span>
              </div>
              <div className="flex justify-between">
                <span className="spu-text-secondary">LSTM V8 Warnings</span>
                <span className="font-mono font-bold">
                  {snapshot?.kpis?.nodes_with_lstm_warning ?? 0}
                </span>
              </div>
              <div className="flex justify-between">
                <span className="spu-text-secondary">Running Slurm Jobs</span>
                <span className="font-mono font-bold">
                  {snapshot?.kpis?.active_slurm_jobs ?? 0}
                </span>
              </div>
            </div>
          </div>
        </div>
      )}

      {/* TAB 2: INCIDENT & ANOMALY INVESTIGATION */}
      {tab === 'investigate' && (
        <div className="grid grid-cols-1 gap-5 lg:grid-cols-12">
          <form onSubmit={handleInvestigate} className="spu-card p-5 lg:col-span-5 space-y-4">
            <div className="flex items-center gap-2 text-sm font-bold">
              <AlertTriangle className="h-4 w-4 text-amber-400" />
              Target Incident / Node Selection
            </div>

            <div>
              <label className="block text-[11px] font-semibold spu-text-secondary mb-1">
                Incident Episode (optional)
              </label>
              <select
                value={targetEpId}
                onChange={(e) => setTargetEpId(e.target.value)}
                className="spu-input w-full text-xs"
              >
                <option value="">-- Investigate by Node / Current State --</option>
                {episodes.map((ep) => (
                  <option key={ep.id} value={ep.id}>
                    #{ep.id} [{ep.priority} | {ep.alert_source}] {ep.node_id} — {ep.event_type} ({ep.status})
                  </option>
                ))}
              </select>
            </div>

            <div>
              <label className="block text-[11px] font-semibold spu-text-secondary mb-1">
                Target Node
              </label>
              <select
                value={targetNode}
                onChange={(e) => setTargetNode(e.target.value)}
                className="spu-input w-full text-xs"
              >
                <option value="">Auto from Episode / Cluster Overview</option>
                {nodes.map((n) => (
                  <option key={n.node_id} value={n.node_id}>
                    {n.display_name || n.node_id} ({n.health_status})
                  </option>
                ))}
              </select>
            </div>

            {selectedEpObj && (
              <div className="spu-subcard p-3 rounded-lg text-[11px] space-y-1">
                <div className="font-bold text-[var(--text-primary)]">{selectedEpObj.title}</div>
                <div className="spu-text-secondary">{selectedEpObj.summary}</div>
              </div>
            )}

            <div>
              <label className="block text-[11px] font-semibold spu-text-secondary mb-1">
                Investigation Prompt
              </label>
              <textarea
                rows={4}
                value={invQuestion}
                onChange={(e) => setInvQuestion(e.target.value)}
                className="spu-input w-full text-xs"
              />
            </div>

            <button type="submit" disabled={sending} className="spu-btn-primary w-full inline-flex items-center justify-center gap-2">
              <FileSearch className="h-4 w-4" />
              {sending ? 'Investigating Evidence...' : 'Run Evidence-Grounded Investigation'}
            </button>
          </form>

          <div className="spu-card p-5 lg:col-span-7">
            <h3 className="text-sm font-bold mb-3 flex items-center gap-2">
              <Activity className="h-4 w-4 text-[var(--accent-cyan)]" />
              Gemini Investigation Findings
            </h3>
            {invResult?.answer ? (
              <div className="space-y-3">
                <div className="text-[11px] font-mono spu-text-muted">
                  Model: {invResult.model} • Target Node: {invResult.target_node || 'Cluster'}
                </div>
                <div className="spu-subcard p-4 rounded-xl whitespace-pre-wrap text-xs leading-relaxed">
                  {invResult.answer}
                </div>
              </div>
            ) : (
              <div className="py-16 text-center text-xs spu-text-secondary">
                Select an incident episode or node on the left to generate a structured, non-speculative root-cause &amp; diagnostic check briefing.
              </div>
            )}
          </div>
        </div>
      )}

      {/* TAB 3: NATURAL-LANGUAGE CLUSTER ANALYTICS */}
      {tab === 'analytics' && (
        <div className="grid grid-cols-1 gap-5 lg:grid-cols-12">
          <form onSubmit={handleRunAnalytics} className="spu-card p-5 lg:col-span-4 space-y-4">
            <div className="flex items-center gap-2 text-sm font-bold">
              <Clock className="h-4 w-4 text-[var(--accent-cyan)]" />
              Historical Cluster Query
            </div>

            <div>
              <label className="block text-[11px] font-semibold spu-text-secondary mb-1">
                Analysis Horizon
              </label>
              <select
                value={analyticsRange}
                onChange={(e) => setAnalyticsRange(e.target.value)}
                className="spu-input w-full text-xs"
              >
                <option value="1h">Last 1 Hour</option>
                <option value="6h">Last 6 Hours</option>
                <option value="12h">Last 12 Hours</option>
                <option value="24h">Last 24 Hours</option>
              </select>
            </div>

            <div>
              <label className="block text-[11px] font-semibold spu-text-secondary mb-1">
                Analytical Question
              </label>
              <textarea
                rows={4}
                value={analyticsQuestion}
                onChange={(e) => setAnalyticsQuestion(e.target.value)}
                className="spu-input w-full text-xs"
              />
            </div>

            <button type="submit" disabled={sending} className="spu-btn-primary w-full inline-flex items-center justify-center gap-2">
              <BarChart3 className="h-4 w-4" />
              {sending ? 'Running Cluster Analytics...' : 'Analyse Historical Evidence'}
            </button>
          </form>

          <div className="spu-card p-5 lg:col-span-8">
            <h3 className="text-sm font-bold mb-3">Natural-Language Analytics Brief</h3>
            {analyticsResult?.answer ? (
              <div className="spu-subcard p-4 rounded-xl whitespace-pre-wrap text-xs leading-relaxed">
                {analyticsResult.answer}
              </div>
            ) : (
              <div className="py-16 text-center text-xs spu-text-secondary">
                Submit a cluster analytics query to correlate persisted telemetry summaries, model comparison evaluations, and historical incidents.
              </div>
            )}
          </div>
        </div>
      )}
    </div>
  );
}
