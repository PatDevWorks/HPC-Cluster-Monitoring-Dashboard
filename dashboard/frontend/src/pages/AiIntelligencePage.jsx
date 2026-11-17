import React, { useEffect, useMemo, useState } from 'react';
import {
  Activity,
  AlertTriangle,
  Bot,
  BarChart3,
  Clock,
  FileSearch,
  Check,
  MessageSquarePlus,
  Pencil,
  Search,
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

const PROVIDER_LABELS = { gemini: 'Gemini', openai: 'OpenAI', groq: 'Groq' };

export default function AiIntelligencePage({
  snapshot,
  user,
  selectedNodeId,
  initialEpisodeId = null,
  onNavigate,
  showToast,
}) {
  const [tab, setTab] = useState(initialEpisodeId ? 'investigate' : 'chat');
  const [sessionId, setSessionId] = useState('');
  const [messages, setMessages] = useState([]);
  const [provider, setProvider] = useState('gemini');
  const [providerStatus, setProviderStatus] = useState({});
  const [conversations, setConversations] = useState([]);
  const [conversationSearch, setConversationSearch] = useState('');
  const [editingSessionId, setEditingSessionId] = useState(null);
  const [editingTitle, setEditingTitle] = useState('');
  const [testingProvider, setTestingProvider] = useState(false);

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

  const loadConversations = async () => {
    try {
      const [conversationRes, providerRes] = await Promise.all([
        api.getAiConversations(), api.getAiProviders(),
      ]);
      const items = conversationRes?.conversations || [];
      setConversations(items);
      setProviderStatus(providerRes?.providers || {});
      if (!sessionId) {
        if (items.length) {
          setSessionId(items[0].session_id);
          setProvider(items[0].provider || 'gemini');
        } else {
          const created = await api.createAiConversation(provider);
          setSessionId(created.session_id);
          setConversations([created]);
        }
      }
    } catch (err) {
      showToast?.(`Could not load AI conversations: ${err.message}`);
    }
  };

  const loadContext = async () => {
    if (!sessionId) return;
    try {
      const [histRes, providerRes] = await Promise.all([
        api.getAiHistory(sessionId, 80), api.getAiProviders(),
      ]);
      setMessages(histRes?.messages || []);
      setProviderStatus(providerRes?.providers || {});
    } catch (err) {
      showToast?.(`Could not load conversation: ${err.message}`);
    }
  };

  useEffect(() => { loadConversations(); }, []);

  useEffect(() => {
    loadContext();
  }, [sessionId]);

  const handleNewConversation = async () => {
    try {
      const created = await api.createAiConversation(provider);
      setConversations((items) => [created, ...items]);
      setSessionId(created.session_id);
      setMessages([]);
      setTab('chat');
    } catch (err) {
      showToast?.(`Could not create conversation: ${err.message}`);
    }
  };

  const handleProviderChange = async (nextProvider) => {
    setProvider(nextProvider);
    if (!sessionId) return;
    try {
      await api.updateAiConversation(sessionId, { provider: nextProvider });
      setConversations((items) => items.map((item) => item.session_id === sessionId ? { ...item, provider: nextProvider } : item));
    } catch (err) {
      showToast?.(`Could not update provider: ${err.message}`);
    }
  };

  const handleRenameConversation = async () => {
    const title = editingTitle.trim();
    if (!title || !editingSessionId) return;
    try {
      await api.updateAiConversation(editingSessionId, { title });
      setConversations((items) => items.map((item) => item.session_id === editingSessionId ? { ...item, title } : item));
      setEditingSessionId(null);
    } catch (err) {
      showToast?.(`Could not rename conversation: ${err.message}`);
    }
  };

  const handleDeleteConversation = async (targetId) => {
    if (!window.confirm('Delete this conversation and its messages?')) return;
    try {
      await api.deleteAiConversation(targetId);
      const next = conversations.filter((item) => item.session_id !== targetId);
      setConversations(next);
      if (targetId === sessionId) {
        if (next.length) {
          setSessionId(next[0].session_id);
          setProvider(next[0].provider || 'gemini');
        } else {
          const created = await api.createAiConversation(provider);
          setConversations([created]);
          setSessionId(created.session_id);
          setMessages([]);
        }
      }
    } catch (err) {
      showToast?.(`Could not delete conversation: ${err.message}`);
    }
  };

  const handleClearConversation = async () => {
    if (!sessionId || !window.confirm('Clear the messages and context in this conversation?')) return;
    try {
      await api.clearAiConversation(sessionId);
      setMessages([]);
      await loadConversations();
    } catch (err) {
      showToast?.(`Could not clear conversation: ${err.message}`);
    }
  };

  const handleTestProvider = async () => {
    setTestingProvider(true);
    try {
      const result = await api.testAiProvider(provider);
      setProviderStatus((old) => ({ ...old, [provider]: result }));
      showToast?.(result.reachable ? `${result.provider} responded using ${result.model}.` : `${result.provider} check failed: ${result.detail}`);
    } catch (err) {
      showToast?.(`Provider check failed: ${err.message}`);
    } finally {
      setTestingProvider(false);
    }
  };

  const activeProviderStatus = providerStatus[provider] || {};
  const visibleConversations = conversations.filter((item) =>
    `${item.title || ''} ${item.last_message_preview || ''}`.toLowerCase().includes(conversationSearch.toLowerCase())
  );

  const selectedEpObj = useMemo(
    () => episodes.find((e) => String(e.id) === String(targetEpId)) || null,
    [episodes, targetEpId]
  );

  const handleSendChat = async (promptOverride = null) => {
    const q = (promptOverride ?? chatInput).trim();
    if (!q || sending) return;
    setSending(true);
    try {
      const res = await api.aiChat(q, sessionId, rangeMinutes, provider);
      if (!promptOverride) setChatInput('');
      await loadContext();
      await loadConversations();
      if (res?.answer) {
        showToast?.(`${res.provider} replied (${res.model})`);
      }
    } catch (err) {
      showToast?.(`${provider} assistant error: ${err.message}`);
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
        provider,
      });
      setInvResult(res);
      await loadContext();
      await loadConversations();
      showToast?.(`Incident investigation completed via ${res.provider} (${res.model})`);
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
      const res = await api.aiQueryAnalytics(analyticsQuestion, analyticsRange, sessionId, provider);
      setAnalyticsResult(res);
      await loadContext();
      await loadConversations();
      showToast?.(`Cluster analytics completed via ${res.provider} (${res.model})`);
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
          <span className={`rounded-full px-3 py-1 font-mono text-[11px] font-bold uppercase ${activeProviderStatus.configured ? 'bg-emerald-500/15 text-emerald-400' : 'bg-amber-500/15 text-amber-400'}`}>
            {PROVIDER_LABELS[provider] || provider}: {activeProviderStatus.configured ? `${activeProviderStatus.model || 'Configured'} · ${activeProviderStatus.reachable === true ? 'Connected' : activeProviderStatus.reachable === false ? 'Unavailable' : 'Not checked'}` : 'Not configured'}
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
        <div className="grid grid-cols-1 gap-4 xl:grid-cols-12">
          <aside className="spu-card min-h-[420px] p-4 xl:col-span-3">
            <div className="flex items-center justify-between gap-2"><h3 className="text-xs font-bold uppercase tracking-wider spu-text-secondary">Conversations</h3><button onClick={handleNewConversation} title="New conversation" className="rounded-lg border spu-border p-2 text-[var(--accent-cyan)]"><MessageSquarePlus className="h-4 w-4" /></button></div>
            <label className="mt-3 flex items-center gap-2 rounded-lg border spu-border px-2.5"><Search className="h-3.5 w-3.5 spu-text-muted" /><input value={conversationSearch} onChange={(event) => setConversationSearch(event.target.value)} placeholder="Search conversations" className="min-w-0 flex-1 bg-transparent py-2 text-xs outline-none" /></label>
            <div className="mt-3 max-h-[520px] space-y-1 overflow-y-auto">
              {visibleConversations.map((conversation) => <div key={conversation.session_id} className={`rounded-lg p-2 ${conversation.session_id === sessionId ? 'bg-cyan-500/10 ring-1 ring-cyan-500/30' : 'hover:bg-[var(--bg-hover)]'}`}>
                {editingSessionId === conversation.session_id ? <div className="flex gap-1"><input value={editingTitle} onChange={(event) => setEditingTitle(event.target.value)} onKeyDown={(event) => event.key === 'Enter' && handleRenameConversation()} autoFocus className="min-w-0 flex-1 rounded border spu-border bg-transparent px-2 py-1 text-xs" /><button onClick={handleRenameConversation} title="Save title" className="text-emerald-400"><Check className="h-4 w-4" /></button></div> : <div className="flex items-start gap-1"><button onClick={() => { setSessionId(conversation.session_id); setProvider(conversation.provider || 'gemini'); setTab('chat'); }} className="min-w-0 flex-1 text-left"><span className="block truncate text-xs font-semibold">{conversation.title || 'New conversation'}</span><span className="mt-1 block truncate text-[10px] spu-text-muted">{conversation.last_message_preview || `${conversation.provider || 'Gemini'} · ${conversation.message_count || 0} messages`}</span><span className="mt-1 block text-[9px] spu-text-muted">{conversation.last_message_utc ? new Date(conversation.last_message_utc).toLocaleString() : new Date(conversation.updated_utc).toLocaleString()}</span></button><button onClick={() => { setEditingSessionId(conversation.session_id); setEditingTitle(conversation.title || ''); }} title="Rename conversation" className="rounded p-1 spu-text-secondary hover:text-[var(--accent-cyan)]"><Pencil className="h-3.5 w-3.5" /></button><button onClick={() => handleDeleteConversation(conversation.session_id)} title="Delete conversation" className="rounded p-1 spu-text-secondary hover:text-rose-400"><Trash2 className="h-3.5 w-3.5" /></button></div>}
              </div>)}
              {!visibleConversations.length && <p className="p-3 text-xs spu-text-secondary">No matching conversations.</p>}
            </div>
          </aside>

          <div className="spu-card flex min-h-[520px] flex-col p-4 xl:col-span-6">
            <div className="mb-3 flex flex-wrap items-center justify-between gap-2 border-b spu-border pb-3"><div><div className="text-sm font-semibold">{conversations.find((item) => item.session_id === sessionId)?.title || 'New conversation'}</div><div className="mt-1 text-[10px] spu-text-muted">Cluster evidence is retrieved for each request. Assistant text is interpretation.</div></div><button onClick={handleClearConversation} className="inline-flex items-center gap-1 rounded-lg border spu-border px-2 py-1.5 text-[10px] spu-text-secondary hover:text-rose-400"><Trash2 className="h-3 w-3" /> Clear context</button></div>
            <div className="min-h-0 flex-1 space-y-3 overflow-y-auto pr-1">
              {messages.length === 0 ? (
                <div className="py-12 text-center text-xs spu-text-secondary">
                  <Bot className="mx-auto mb-2 h-8 w-8 text-[var(--accent-cyan)] opacity-70" />
                  <p className="font-semibold text-[var(--text-primary)]">
                    Ask the HPC AI Assistant.
                  </p>
                  <p className="mt-1 spu-text-muted">Choose a configured provider, then ask about current cluster evidence.</p>
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
                        {m.role === 'user' ? user?.email || 'Operator' : `${m.evidence?.provider || 'gemini'} · ${m.evidence?.model || ''} · LLM interpretation`} · {m.mode}
                      </span>
                      <span>{m.created_utc}</span>
                    </div>
                    <div className="whitespace-pre-wrap leading-relaxed text-[var(--text-primary)]">
                      {m.content}
                    </div>
                    {m.role === 'assistant' && m.evidence?.evidence_summary && <details className="mt-3 border-t spu-border pt-2"><summary className="cursor-pointer text-[10px] font-semibold text-[var(--accent-cyan)]">Evidence references</summary><pre className="mt-2 overflow-x-auto whitespace-pre-wrap text-[10px] spu-text-secondary">{JSON.stringify(m.evidence.evidence_summary, null, 2)}</pre></details>}
                  </div>
                ))
              )}
            </div>

            <div className="mt-4 border-t pt-3 spu-border">
              <div className="mb-2 flex items-center justify-between text-[11px] spu-text-secondary">
                <label>Provider <select value={provider} onChange={(event) => handleProviderChange(event.target.value)} className="spu-input ml-1 py-1 text-xs"><option value="gemini" disabled={!providerStatus.gemini?.configured && provider !== 'gemini'}>Gemini {providerStatus.gemini?.model ? `· ${providerStatus.gemini.model}` : ''}{providerStatus.gemini?.configured ? '' : ' · Not configured'}</option><option value="openai" disabled={!providerStatus.openai?.configured && provider !== 'openai'}>OpenAI {providerStatus.openai?.model ? `· ${providerStatus.openai.model}` : ''}{providerStatus.openai?.configured ? '' : ' · Not configured'}</option><option value="groq" disabled={!providerStatus.groq?.configured && provider !== 'groq'}>Groq {providerStatus.groq?.model ? `· ${providerStatus.groq.model}` : ''}{providerStatus.groq?.configured ? '' : ' · Not configured'}</option></select></label>
                <label>Context <select value={rangeMinutes} onChange={(e) => setRangeMinutes(Number(e.target.value))} className="spu-input ml-1 py-1 text-xs"><option value={15}>15 min</option><option value={60}>1 hour</option><option value={360}>6 hours</option><option value={1440}>24 hours</option></select></label>
              </div>
              <div className="flex items-end gap-2">
                <textarea
                  rows={3}
                  value={chatInput}
                  onChange={(e) => setChatInput(e.target.value)}
                  onKeyDown={(e) => {
                    if (e.key === 'Enter' && !e.shiftKey) {
                      e.preventDefault();
                      handleSendChat();
                    }
                  }}
                  placeholder={`Ask ${PROVIDER_LABELS[provider] || provider} about cluster state, node anomalies, model outputs, or Slurm jobs…`}
                  className="spu-input min-h-20 flex-1 resize-y text-xs"
                />
                <button
                  onClick={() => handleSendChat()}
                  disabled={sending || !chatInput.trim() || !activeProviderStatus.configured}
                  className="spu-btn-primary inline-flex items-center gap-1.5"
                >
                  <Send className="h-3.5 w-3.5" />
                  {sending ? 'Thinking…' : 'Send'}
                </button>
              </div>
              {user?.role === 'admin' || user?.role === 'super_admin' ? <button disabled={testingProvider || !activeProviderStatus.configured} onClick={handleTestProvider} className="mt-2 text-[10px] font-semibold text-[var(--accent-cyan)] disabled:opacity-50">{testingProvider ? 'Checking provider…' : `Test ${PROVIDER_LABELS[provider] || provider} connection`}</button> : null}
            </div>
          </div>

          {/* Right rail: Quick Prompts & Live Context Summary */}
          <div className="space-y-4 xl:col-span-3">
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
