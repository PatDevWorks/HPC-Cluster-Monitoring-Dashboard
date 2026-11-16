import React, { useCallback, useEffect, useMemo, useState } from 'react';
import { Activity, ArrowLeft, BrainCircuit, Clock3, Cpu, Database, HeartPulse, Plus, RefreshCw, Search, Settings2 } from 'lucide-react';
import { api } from '../api.js';
import AiPredictionsPage from './AiPredictionsPage.jsx';

const NAV = [
  { id: 'registry', label: 'Registry' },
  { id: 'history', label: 'Observation history' },
  { id: 'health', label: 'Model health' },
  { id: 'live', label: 'Live predictions' },
];

const dashNode = (id) => ({
  headnode: 'head-node', compute001: 'compute-01', compute002: 'compute-02', compute003: 'compute-03',
}[id] || id || '');

const display = (value) => value === null || value === undefined || value === '' ? 'Not reported' : String(value);
const timeLabel = (value) => value ? new Date(value).toLocaleString() : 'No successful update recorded';

function StatusPill({ value, unknownLabel = 'Unknown' }) {
  const text = value === true ? 'Yes' : value === false ? 'No' : unknownLabel;
  const style = value === true
    ? 'bg-emerald-500/15 text-emerald-400'
    : value === false
      ? 'bg-amber-500/15 text-amber-400'
      : 'bg-slate-500/15 spu-text-secondary';
  return <span className={`rounded-full px-2 py-1 text-[10px] font-semibold ${style}`}>{text}</span>;
}

function Metric({ label, value, icon: Icon }) {
  return (
    <div className="spu-card flex min-w-0 items-center gap-3 p-4">
      <div className="rounded-xl bg-cyan-500/10 p-2.5 text-[var(--accent-cyan)]"><Icon className="h-5 w-5" /></div>
      <div className="min-w-0"><div className="text-[11px] spu-text-secondary">{label}</div><div className="mt-1 truncate text-xl font-bold">{value ?? '—'}</div></div>
    </div>
  );
}

function RegistrationForm({ onRegistered, showToast }) {
  const [form, setForm] = useState({ model_key: '', model_name: '', model_type: '', purpose: '', provider: '' });
  const [saving, setSaving] = useState(false);
  const set = (key) => (event) => setForm((old) => ({ ...old, [key]: event.target.value }));
  const submit = async (event) => {
    event.preventDefault();
    setSaving(true);
    try {
      await api.registerModel({ ...form, nodes_monitored: [], features: [] });
      setForm({ model_key: '', model_name: '', model_type: '', purpose: '', provider: '' });
      showToast?.('Model registered');
      await onRegistered();
    } catch (error) {
      showToast?.(`Could not register model: ${error.message}`);
    } finally {
      setSaving(false);
    }
  };
  return (
    <details className="spu-card p-4">
      <summary className="flex cursor-pointer list-none items-center gap-2 text-sm font-semibold"><Plus className="h-4 w-4 text-[var(--accent-cyan)]" /> Register model metadata</summary>
      <form onSubmit={submit} className="mt-4 grid gap-3 sm:grid-cols-2">
        {[
          ['model_key', 'Unique key'], ['model_name', 'Display name'], ['model_type', 'Model type'], ['provider', 'Provider'],
        ].map(([key, label]) => <label key={key} className="text-xs spu-text-secondary">{label}<input required value={form[key]} onChange={set(key)} className="mt-1 w-full rounded-lg border spu-border bg-transparent px-3 py-2 text-sm spu-text-primary" /></label>)}
        <label className="text-xs spu-text-secondary sm:col-span-2">Purpose<textarea value={form.purpose} onChange={set('purpose')} rows={2} className="mt-1 w-full rounded-lg border spu-border bg-transparent px-3 py-2 text-sm spu-text-primary" /></label>
        <div className="sm:col-span-2"><button disabled={saving} className="rounded-lg bg-cyan-600 px-3 py-2 text-xs font-semibold text-white disabled:opacity-50">{saving ? 'Registering…' : 'Register model'}</button></div>
      </form>
    </details>
  );
}

export default function ModelsCentrePage({ snapshot, user, selectedNodeId, onSelectNode, onNavigate, showToast, busyAction }) {
  const [view, setView] = useState('registry');
  const [registry, setRegistry] = useState([]);
  const [summary, setSummary] = useState(null);
  const [health, setHealth] = useState([]);
  const [retention, setRetention] = useState(null);
  const [selectedModel, setSelectedModel] = useState(null);
  const [observations, setObservations] = useState([]);
  const [selectedObservation, setSelectedObservation] = useState(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState('');
  const [filters, setFilters] = useState({ model_name: '', node_id: '', classification: '', flagged: '', since_utc: '', until_utc: '' });
  const [retentionBusy, setRetentionBusy] = useState(false);
  const isAdmin = ['admin', 'super_admin'].includes(user?.role);

  const loadOverview = useCallback(async () => {
    setLoading(true);
    setError('');
    try {
      const [models, stats, healthResponse, retentionResponse] = await Promise.all([
        api.getModelRegistry(), api.getModelSummary(), api.getModelHealth(), api.getModelRetention(),
      ]);
      setRegistry(models || []);
      setSummary(stats || null);
      setHealth(healthResponse?.models || []);
      setRetention(retentionResponse || null);
    } catch (err) {
      setError(err.message || 'Unable to load model centre data.');
    } finally {
      setLoading(false);
    }
  }, []);

  const loadObservations = useCallback(async (criteria = filters) => {
    setLoading(true);
    setError('');
    try {
      const toIso = (value) => value ? new Date(value).toISOString() : '';
      const rows = await api.getModelObservations({
        model_name: criteria.model_name,
        node_id: criteria.node_id,
        classification: criteria.classification,
        flagged: criteria.flagged,
        since_utc: toIso(criteria.since_utc),
        until_utc: toIso(criteria.until_utc),
        limit: 1000,
      });
      setObservations(rows || []);
    } catch (err) {
      setError(err.message || 'Unable to load observations.');
    } finally {
      setLoading(false);
    }
  }, [filters]);

  useEffect(() => { loadOverview(); }, [loadOverview]);
  useEffect(() => { if (view === 'history') loadObservations(); }, [view, loadObservations]);

  const openModel = (model) => { setSelectedModel(model); setSelectedObservation(null); setView('detail'); };
  const backToRegistry = () => { setSelectedObservation(null); setSelectedModel(null); setView('registry'); };
  const openObservationHistory = (modelKey = '') => {
    setFilters((old) => ({ ...old, model_name: modelKey }));
    setView('history');
  };

  const changeRetention = async (days) => {
    setRetentionBusy(true);
    try {
      const result = await api.updateModelRetention(Number(days));
      setRetention({ retention_days: result.retention_days, last_cleanup_utc: result.last_cleanup_utc, supported_days: [15, 30] });
      showToast?.(`Retention set to ${days} days; removed ${result.deleted_count} expired observation(s).`);
      await loadOverview();
    } catch (err) {
      showToast?.(`Retention update failed: ${err.message}`);
    } finally {
      setRetentionBusy(false);
    }
  };

  const filtersChanged = (key) => (event) => setFilters((old) => ({ ...old, [key]: event.target.value }));
  const selectedHealth = useMemo(() => health.find((item) => item.model_key === selectedModel?.model_key), [health, selectedModel]);

  if (view === 'live') {
    return <section className="space-y-4">
      <div className="flex items-center gap-3"><button onClick={backToRegistry} className="rounded-lg border spu-border p-2" aria-label="Back to models registry"><ArrowLeft className="h-4 w-4" /></button><div><div className="text-xs spu-text-secondary">Models Centre / Live predictions</div><h2 className="text-xl font-bold">Live model predictions and controls</h2></div></div>
      <AiPredictionsPage snapshot={snapshot} user={user} selectedNodeId={selectedNodeId} onSelectNode={onSelectNode} onNavigate={onNavigate} showToast={showToast} busyAction={busyAction} />
    </section>;
  }

  return (
    <section className="space-y-5">
      <header className="flex flex-wrap items-start justify-between gap-4">
        <div className="flex items-start gap-3">
          {view !== 'registry' && <button onClick={selectedObservation ? () => setSelectedObservation(null) : backToRegistry} className="mt-1 rounded-lg border spu-border p-2" aria-label="Go back"><ArrowLeft className="h-4 w-4" /></button>}
          <div><div className="flex items-center gap-2"><BrainCircuit className="h-5 w-5 text-[var(--accent-cyan)]" /><h2 className="text-xl font-bold">Models Centre</h2></div><p className="mt-1 max-w-3xl text-sm spu-text-secondary">Centralised visibility into deployed models, operational status, inference activity and historical observations across the HPC cluster.</p></div>
        </div>
        <button onClick={view === 'history' ? () => loadObservations() : loadOverview} className="inline-flex items-center gap-2 rounded-lg border spu-border px-3 py-2 text-xs font-semibold hover:border-[var(--accent-cyan)]"><RefreshCw className="h-3.5 w-3.5" /> Refresh</button>
      </header>

      {view !== 'detail' && !selectedObservation && <nav className="flex flex-wrap gap-2" aria-label="Models Centre navigation">
        {NAV.map((item) => <button key={item.id} onClick={() => setView(item.id)} className={`rounded-lg px-3 py-2 text-xs font-semibold ${view === item.id ? 'bg-cyan-500/15 text-[var(--accent-cyan)]' : 'border spu-border spu-text-secondary hover:border-[var(--accent-cyan)]'}`}>{item.label}</button>)}
      </nav>}

      {error && <div role="alert" className="rounded-lg border border-rose-500/30 bg-rose-500/10 p-3 text-sm text-rose-300">{error}</div>}
      {loading && <div className="spu-card p-5 text-sm spu-text-secondary">Loading model data…</div>}

      {!loading && view === 'registry' && <>
        <div className="grid gap-3 sm:grid-cols-2 xl:grid-cols-4">
          <Metric label="Registered models" value={summary?.total_registered_models} icon={BrainCircuit} />
          <Metric label="Healthy / fresh" value={summary?.healthy_models} icon={HeartPulse} />
          <Metric label="Degraded / unavailable" value={summary?.degraded_or_unavailable_models} icon={Activity} />
          <Metric label="Stored observations" value={summary?.total_stored_observations} icon={Database} />
        </div>
        <div className="spu-card flex flex-wrap items-center justify-between gap-3 p-4 text-xs"><span className="spu-text-secondary">Latest observation: <strong className="spu-text-primary">{summary?.latest_observation ? `${summary.latest_observation.model_name} · ${dashNode(summary.latest_observation.node_id)} · ${timeLabel(summary.latest_observation.observation_utc)}` : 'No observation recorded'}</strong></span><button onClick={() => openObservationHistory()} className="font-semibold text-[var(--accent-cyan)]">View observation history</button></div>
        <div className="grid gap-3 lg:grid-cols-2 xl:grid-cols-3">
          {registry.map((model) => <button key={model.model_key} onClick={() => openModel(model)} className="spu-card p-5 text-left transition hover:border-[var(--accent-cyan)] focus:outline-none focus:ring-2 focus:ring-[var(--accent-cyan)]">
            <div className="flex items-start justify-between gap-3"><div><h3 className="font-bold">{model.model_name}</h3><div className="mt-1 text-xs spu-text-secondary">{model.model_type} · {display(model.version)}</div></div><StatusPill value={model.runtime?.observation_fresh} unknownLabel={model.runtime?.status || 'Unknown'} /></div>
            <p className="mt-3 line-clamp-2 text-xs spu-text-secondary">{model.purpose}</p>
            <div className="mt-4 grid grid-cols-2 gap-3 text-[11px]"><div><div className="spu-text-muted">API reachable</div><div className="mt-1"><StatusPill value={model.runtime?.api_reachable} unknownLabel={model.runtime?.configured ? 'Not checked' : 'Unknown'} /></div></div><div><div className="spu-text-muted">Last successful update</div><div className="mt-1 spu-text-secondary">{timeLabel(model.last_success_utc)}</div></div></div>
            <div className="mt-4 flex items-center justify-between border-t spu-border pt-3 text-[11px]"><span className="spu-text-secondary">{model.nodes_monitored?.length || 0} monitored scope entries</span><span className="font-semibold text-[var(--accent-cyan)]">Open details →</span></div>
          </button>)}
        </div>
        {isAdmin && <div className="grid gap-3 lg:grid-cols-2"><RegistrationForm onRegistered={loadOverview} showToast={showToast} /><div className="spu-card p-4"><div className="flex items-center gap-2 text-sm font-semibold"><Settings2 className="h-4 w-4 text-[var(--accent-cyan)]" /> Model configuration</div><p className="mt-2 text-xs spu-text-secondary">Manage the existing V7 and LSTM V8 integrations and inspect live forecasts.</p><button onClick={() => setView('live')} className="mt-3 rounded-lg border spu-border px-3 py-2 text-xs font-semibold hover:border-[var(--accent-cyan)]">Open model controls</button></div></div>}
        {isAdmin && retention && <div className="spu-card flex flex-wrap items-center justify-between gap-4 p-4"><div><div className="text-sm font-semibold">Observation retention</div><div className="mt-1 text-xs spu-text-secondary">Old model observations are removed by the backend. Incident and audit records are unaffected.</div><div className="mt-1 text-[11px] spu-text-muted">Last cleanup: {timeLabel(retention.last_cleanup_utc)}</div></div><label className="text-xs spu-text-secondary">Keep observations<select value={retention.retention_days} disabled={retentionBusy} onChange={(event) => changeRetention(event.target.value)} className="ml-2 rounded-lg border spu-border bg-[var(--bg-card)] px-2 py-2 spu-text-primary"><option value={15}>15 days</option><option value={30}>30 days</option></select></label></div>}
      </>}

      {!loading && view === 'health' && <div className="space-y-3">{health.map((model) => <article key={model.model_key} className="spu-card p-4"><div className="flex flex-wrap items-center justify-between gap-3"><div><h3 className="font-semibold">{model.model_name}</h3><p className="mt-1 text-xs spu-text-secondary">Reported status: {model.status || 'unknown'}</p></div><StatusPill value={model.observation_fresh} unknownLabel="Freshness unknown" /></div><div className="mt-4 grid gap-3 sm:grid-cols-2 xl:grid-cols-5">{[['API reachable', model.api_reachable], ['Model loaded', model.model_loaded], ['Pipeline running', model.pipeline_running], ['Recent inference success', model.recent_inference_success], ['Observation fresh', model.observation_fresh]].map(([label, value]) => <div key={label} className="rounded-lg border spu-border p-3"><div className="text-[10px] spu-text-secondary">{label}</div><div className="mt-2"><StatusPill value={value} /></div></div>)}</div><div className="mt-3 text-[11px] spu-text-secondary">Last successful update: {timeLabel(model.last_success_utc)}{model.age_seconds != null ? ` · ${model.age_seconds}s ago` : ''}</div></article>)}</div>}

      {!loading && view === 'history' && !selectedObservation && <>
        <form onSubmit={(event) => { event.preventDefault(); loadObservations(filters); }} className="spu-card grid gap-3 p-4 sm:grid-cols-2 xl:grid-cols-6">
          <label className="text-[10px] spu-text-secondary">Model<select value={filters.model_name} onChange={filtersChanged('model_name')} className="mt-1 w-full rounded-lg border spu-border bg-[var(--bg-card)] px-2 py-2 text-xs spu-text-primary"><option value="">All models</option>{registry.map((item) => <option key={item.model_key} value={item.model_key}>{item.model_name}</option>)}</select></label>
          <label className="text-[10px] spu-text-secondary">Node<input value={filters.node_id} onChange={filtersChanged('node_id')} placeholder="Any node" className="mt-1 w-full rounded-lg border spu-border bg-transparent px-2 py-2 text-xs spu-text-primary" /></label>
          <label className="text-[10px] spu-text-secondary">Classification<input value={filters.classification} onChange={filtersChanged('classification')} placeholder="Any" className="mt-1 w-full rounded-lg border spu-border bg-transparent px-2 py-2 text-xs spu-text-primary" /></label>
          <label className="text-[10px] spu-text-secondary">Flagged<select value={filters.flagged} onChange={filtersChanged('flagged')} className="mt-1 w-full rounded-lg border spu-border bg-[var(--bg-card)] px-2 py-2 text-xs spu-text-primary"><option value="">All</option><option value="true">Flagged</option><option value="false">Unflagged</option></select></label>
          <label className="text-[10px] spu-text-secondary">From<input type="datetime-local" value={filters.since_utc} onChange={filtersChanged('since_utc')} className="mt-1 w-full rounded-lg border spu-border bg-transparent px-2 py-2 text-xs spu-text-primary" /></label>
          <label className="text-[10px] spu-text-secondary">To<input type="datetime-local" value={filters.until_utc} onChange={filtersChanged('until_utc')} className="mt-1 w-full rounded-lg border spu-border bg-transparent px-2 py-2 text-xs spu-text-primary" /></label>
          <button className="inline-flex items-center justify-center gap-2 rounded-lg bg-cyan-600 px-3 py-2 text-xs font-semibold text-white sm:col-span-2 xl:col-span-6"><Search className="h-3.5 w-3.5" /> Apply filters</button>
        </form>
        <div className="spu-card overflow-x-auto">{observations.length ? <table className="w-full min-w-[850px] text-left text-xs"><thead className="border-b spu-border spu-text-secondary"><tr>{['Timestamp', 'Model', 'Node', 'Score', 'Threshold', 'Classification', 'Flagged', 'Details'].map((title) => <th key={title} className="px-3 py-3 font-semibold">{title}</th>)}</tr></thead><tbody>{observations.map((row) => <tr key={row.id} className="border-b spu-border last:border-0 hover:bg-[var(--bg-hover)]"><td className="px-3 py-3 font-mono">{timeLabel(row.observation_utc)}</td><td className="px-3 py-3">{row.model_name}</td><td className="px-3 py-3">{dashNode(row.node_id)}</td><td className="px-3 py-3 font-mono">{display(row.score)}</td><td className="px-3 py-3 font-mono">{display(row.threshold)}</td><td className="px-3 py-3">{display(row.classification)}</td><td className="px-3 py-3">{row.flagged ? 'Flagged' : 'No'}</td><td className="px-3 py-3"><button onClick={() => setSelectedObservation(row)} className="font-semibold text-[var(--accent-cyan)]">Open record</button></td></tr>)}</tbody></table> : <div className="p-8 text-center text-sm spu-text-secondary">No observations match these filters.</div>}</div>
      </>}

      {!loading && view === 'detail' && selectedModel && <>
        <div className="text-xs spu-text-secondary"><button onClick={backToRegistry} className="hover:text-[var(--accent-cyan)]">Models Centre</button> / {selectedModel.model_name}</div>
        <div className="grid gap-3 xl:grid-cols-3"><article className="spu-card p-5 xl:col-span-2"><div className="flex flex-wrap items-start justify-between gap-3"><div><h3 className="text-lg font-bold">{selectedModel.model_name}</h3><p className="mt-1 text-sm spu-text-secondary">{selectedModel.purpose}</p></div><span className="rounded-full border spu-border px-2.5 py-1 text-[10px]">{selectedModel.model_type}</span></div><dl className="mt-5 grid gap-3 sm:grid-cols-2"><div><dt className="text-[10px] spu-text-muted">Version</dt><dd className="mt-1 text-xs">{display(selectedModel.version)}</dd></div><div><dt className="text-[10px] spu-text-muted">Provider</dt><dd className="mt-1 text-xs">{display(selectedModel.provider)}</dd></div><div><dt className="text-[10px] spu-text-muted">Lookback</dt><dd className="mt-1 text-xs">{display(selectedModel.lookback_window)}</dd></div><div><dt className="text-[10px] spu-text-muted">Monitored nodes</dt><dd className="mt-1 text-xs">{(selectedModel.nodes_monitored || []).join(', ') || 'Not reported'}</dd></div></dl><div className="mt-5 flex flex-wrap gap-2">{isAdmin && <button onClick={() => setView('live')} className="rounded-lg border spu-border px-3 py-2 text-xs font-semibold">Model configuration</button>}<button onClick={() => openObservationHistory(selectedModel.model_key)} className="rounded-lg border spu-border px-3 py-2 text-xs font-semibold">Observation history</button></div></article>
          <article className="spu-card p-5"><h4 className="font-semibold">Operational health</h4><div className="mt-4 space-y-3 text-xs">{[['API reachable', selectedModel.runtime?.api_reachable], ['Model loaded', selectedModel.runtime?.model_loaded], ['Pipeline running', selectedModel.runtime?.pipeline_running], ['Recent inference successful', selectedModel.runtime?.recent_inference_success], ['Observation fresh', selectedModel.runtime?.observation_fresh]].map(([label, value]) => <div key={label} className="flex items-center justify-between gap-2"><span className="spu-text-secondary">{label}</span><StatusPill value={value} /></div>)}</div><div className="mt-4 border-t spu-border pt-3 text-[10px] spu-text-secondary">Last API success: {timeLabel(selectedModel.runtime?.last_success_utc)}<br />API endpoint: backend-managed; credentials are not exposed.</div></article></div>
        <article className="spu-card p-5"><div className="flex flex-wrap items-center justify-between gap-2"><div><h4 className="font-semibold">Latest stored observation</h4><p className="mt-1 text-[11px] spu-text-secondary">Read from the existing SQLite observation history.</p></div><button onClick={() => openObservationHistory(selectedModel.model_key)} className="text-xs font-semibold text-[var(--accent-cyan)]">View all observations</button></div>{selectedModel.latest_observation ? <div className="mt-4 grid gap-3 sm:grid-cols-3"><div><div className="text-[10px] spu-text-muted">Node / time</div><div className="mt-1 text-xs">{dashNode(selectedModel.latest_observation.node_id)} · {timeLabel(selectedModel.latest_observation.observation_utc)}</div></div><div><div className="text-[10px] spu-text-muted">Score / threshold</div><div className="mt-1 font-mono text-xs">{display(selectedModel.latest_observation.score)} / {display(selectedModel.latest_observation.threshold)}</div></div><div><div className="text-[10px] spu-text-muted">Classification</div><div className="mt-1 text-xs">{display(selectedModel.latest_observation.classification)} · {selectedModel.latest_observation.flagged ? 'Flagged' : 'Not flagged'}</div></div></div> : <div className="mt-4 text-xs spu-text-secondary">No observation has been stored for this model.</div>}</article>
        {selectedModel.runtime?.runtime_schema && <details className="spu-card p-4"><summary className="cursor-pointer text-sm font-semibold">Runtime schema and supported outputs</summary><pre className="mt-3 overflow-x-auto whitespace-pre-wrap text-[11px] spu-text-secondary">{JSON.stringify(selectedModel.runtime.runtime_schema, null, 2)}</pre></details>}
        <details className="spu-card p-4"><summary className="cursor-pointer text-sm font-semibold">Latest runtime payload</summary><pre className="mt-3 max-h-96 overflow-auto whitespace-pre-wrap text-[11px] spu-text-secondary">{JSON.stringify(selectedModel.runtime?.state || selectedModel.runtime?.nodes_with_current_results || {}, null, 2)}</pre></details>
      </>}

      {!loading && view === 'history' && selectedObservation && <>
        <div className="text-xs spu-text-secondary"><button onClick={() => setSelectedObservation(null)} className="hover:text-[var(--accent-cyan)]">Observation history</button> / Record {selectedObservation.id}</div>
        <article className="spu-card p-5"><h3 className="text-base font-bold">Observation details</h3><dl className="mt-4 grid gap-4 sm:grid-cols-2 xl:grid-cols-4">{[['Model', selectedObservation.model_name], ['Node', dashNode(selectedObservation.node_id)], ['Timestamp', timeLabel(selectedObservation.observation_utc)], ['Score', selectedObservation.score], ['Threshold', selectedObservation.threshold], ['Classification', selectedObservation.classification], ['Flagged', selectedObservation.flagged ? 'Yes' : 'No']].map(([label, value]) => <div key={label}><dt className="text-[10px] spu-text-muted">{label}</dt><dd className="mt-1 text-xs">{display(value)}</dd></div>)}</dl><h4 className="mt-5 text-xs font-semibold">Original model details</h4><pre className="mt-2 max-h-96 overflow-auto rounded-lg border spu-border p-3 text-[11px] spu-text-secondary">{JSON.stringify(selectedObservation.details || {}, null, 2)}</pre><p className="mt-3 text-[10px] spu-text-secondary">This record contains model output only. No root cause or incident relationship is inferred by this page.</p></article>
      </>}
    </section>
  );
}
