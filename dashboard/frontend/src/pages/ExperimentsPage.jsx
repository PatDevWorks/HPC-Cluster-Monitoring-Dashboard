import React, { useEffect, useState } from 'react';
import {
  CheckCircle2,
  FlaskConical,
  Plus,
  Trash2,
  XCircle,
} from 'lucide-react';
import { api } from '../api.js';

const CATEGORIES = [
  { id: 'failure_injection', label: 'Failure Injection' },
  { id: 'november_experiment', label: 'November Experiment' },
  { id: 'operational_incident', label: 'Operational Incident' },
  { id: 'planned_workload', label: 'Planned Stress / Benchmark' },
  { id: 'healthy_baseline', label: 'Healthy Baseline Window' },
];

export default function ExperimentsPage({
  snapshot,
  user,
  showToast,
}) {
  const [data, setData] = useState({ experiments: [], evaluation: null });
  const [categoryFilter, setCategoryFilter] = useState('');
  const [submitting, setSubmitting] = useState(false);

  const nowIso = new Date().toISOString().slice(0, 19) + 'Z';
  const [form, setForm] = useState({
    name: '',
    category: 'failure_injection',
    node_id: 'compute-01',
    fault_type: 'memory_exhaustion',
    label: 'positive_fault',
    start_utc: nowIso,
    end_utc: '',
    workload_condition: 'high_load',
    notes: '',
  });

  const isAdmin = ['admin', 'super_admin'].includes(user?.role);

  const loadExperiments = async () => {
    try {
      const res = await api.getExperiments(categoryFilter || null);
      setData({
        experiments: res.experiments || [],
        evaluation: res.evaluation || null,
      });
    } catch (err) {
      showToast?.(`Could not load experiments: ${err.message}`);
    }
  };

  useEffect(() => {
    loadExperiments();
  }, [categoryFilter]);

  const handleCreate = async (e) => {
    e.preventDefault();
    if (!form.name.trim() || !form.start_utc.trim()) return;
    setSubmitting(true);
    try {
      await api.createExperiment({
        ...form,
        end_utc: form.end_utc.trim() || null,
      });
      setForm((prev) => ({
        ...prev,
        name: '',
        notes: '',
        start_utc: new Date().toISOString().slice(0, 19) + 'Z',
        end_utc: '',
      }));
      await loadExperiments();
      showToast?.('Experiment recorded and model comparison recomputed');
    } catch (err) {
      showToast?.(`Experiment create failed: ${err.message}`);
    } finally {
      setSubmitting(false);
    }
  };

  const handleCloseNow = async (exp) => {
    try {
      await api.updateExperiment(exp.id, {
        end_utc: new Date().toISOString().slice(0, 19) + 'Z',
      });
      await loadExperiments();
      showToast?.(`Closed experiment "${exp.name}"`);
    } catch (err) {
      showToast?.(`Update failed: ${err.message}`);
    }
  };

  const handleDelete = async (id) => {
    try {
      await api.deleteExperiment(id);
      await loadExperiments();
      showToast?.('Experiment removed');
    } catch (err) {
      showToast?.(`Delete failed: ${err.message}`);
    }
  };

  const evaluation = data.evaluation;
  const detEval = evaluation?.detector_evaluation || {};
  const expResults = evaluation?.experiment_results || [];

  return (
    <div className="space-y-6">
      {/* Header */}
      <div className="flex flex-wrap items-center justify-between gap-3">
        <div className="flex items-center gap-3">
          <div className="flex h-10 w-10 items-center justify-center rounded-xl bg-cyan-500/15 text-[var(--accent-cyan)]">
            <FlaskConical className="h-5 w-5" />
          </div>
          <div>
            <h2 className="text-xl font-bold tracking-tight">Experiments &amp; Evaluation</h2>
            <p className="text-xs spu-text-secondary">
              Failure-injection windows, November experiment ground truth, and event-level evaluation comparing V7, LSTM V8, and simple telemetry thresholds
            </p>
          </div>
        </div>

        <select
          value={categoryFilter}
          onChange={(e) => setCategoryFilter(e.target.value)}
          className="spu-input text-xs"
        >
          <option value="">All Categories</option>
          {CATEGORIES.map((c) => (
            <option key={c.id} value={c.id}>{c.label}</option>
          ))}
        </select>
      </div>

      {/* Methodological Principle */}
      <div className="spu-card p-4 text-xs spu-text-secondary">
        <strong className="text-[var(--text-primary)]">Evaluation Standard:</strong>{' '}
        {evaluation?.methodology_note ||
          'Model quality is evaluated against labelled fault and benign workload windows using detection coverage, missed events, detection timing, and false-positive rate — never raw alert counts alone.'}
      </div>

      {/* Detector Comparison Scorecard */}
      <section className="spu-card p-5">
        <h3 className="text-sm font-bold mb-3">
          Model Detection Performance vs Simple Telemetry Threshold Baseline
        </h3>

        {!evaluation?.has_labelled_experiments ? (
          <div className="rounded-xl p-6 text-center text-xs spu-subcard spu-text-secondary">
            No labelled experiments recorded yet. Tag a failure-injection run, November experiment interval, or benign workload window below to compute real evaluation metrics.
          </div>
        ) : (
          <div className="overflow-x-auto">
            <table className="w-full text-left text-xs">
              <thead>
                <tr className="border-b spu-border spu-text-secondary">
                  <th className="py-2 pr-4">Detector / Baseline</th>
                  <th className="py-2 pr-4">Detected / Positives</th>
                  <th className="py-2 pr-4">Missed</th>
                  <th className="py-2 pr-4">Coverage %</th>
                  <th className="py-2 pr-4">Mean Delay (min)</th>
                  <th className="py-2 pr-4">False Alarm Windows</th>
                  <th className="py-2 pr-4">FP Rate %</th>
                  <th className="py-2 pr-4">Event F1</th>
                </tr>
              </thead>
              <tbody className="divide-y spu-border font-mono">
                {[
                  { key: 'v7', name: 'V7 Isolation Forest (28-feat)' },
                  { key: 'lstm_v8', name: 'LSTM V8 Temporal Warning' },
                  { key: 'telemetry', name: 'Simple Telemetry Thresholds' },
                ].map((rowMeta) => {
                  const s = detEval[rowMeta.key] || {};
                  return (
                    <tr key={rowMeta.key}>
                      <td className="py-2.5 pr-4 font-sans font-semibold">{rowMeta.name}</td>
                      <td className="py-2.5 pr-4">{s.detected_events ?? 0} / {s.positive_events ?? 0}</td>
                      <td className="py-2.5 pr-4">{s.missed_events ?? 0}</td>
                      <td className="py-2.5 pr-4">{s.detection_coverage_pct != null ? `${s.detection_coverage_pct}%` : '--'}</td>
                      <td className="py-2.5 pr-4">{s.mean_detection_delay_min != null ? `${s.mean_detection_delay_min}m` : '--'}</td>
                      <td className="py-2.5 pr-4">{s.false_positive_windows ?? 0} / {s.benign_windows ?? 0}</td>
                      <td className="py-2.5 pr-4">{s.false_positive_rate_pct != null ? `${s.false_positive_rate_pct}%` : '--'}</td>
                      <td className="py-2.5 pr-4">{s.event_f1 ?? '--'}</td>
                    </tr>
                  );
                })}
              </tbody>
            </table>
          </div>
        )}
      </section>

      <div className="grid grid-cols-1 gap-5 lg:grid-cols-12">
        {/* Create / Tag Experiment Form */}
        {isAdmin && (
          <form onSubmit={handleCreate} className="spu-card p-5 lg:col-span-5 space-y-3">
            <div className="flex items-center gap-2 text-sm font-bold">
              <Plus className="h-4 w-4 text-[var(--accent-cyan)]" />
              Tag New Experiment / Event Window
            </div>

            <div>
              <label className="block text-[11px] font-semibold spu-text-secondary mb-1">Experiment Name</label>
              <input
                type="text"
                required
                value={form.name}
                onChange={(e) => setForm({ ...form, name: e.target.value })}
                placeholder="e.g. Nov Compute001 Memory Leak Stress"
                className="spu-input w-full text-xs"
              />
            </div>

            <div className="grid grid-cols-2 gap-2.5">
              <div>
                <label className="block text-[11px] font-semibold spu-text-secondary mb-1">Category</label>
                <select
                  value={form.category}
                  onChange={(e) => setForm({ ...form, category: e.target.value })}
                  className="spu-input w-full text-xs"
                >
                  {CATEGORIES.map((c) => (
                    <option key={c.id} value={c.id}>{c.label}</option>
                  ))}
                </select>
              </div>
              <div>
                <label className="block text-[11px] font-semibold spu-text-secondary mb-1">Target Node</label>
                <select
                  value={form.node_id}
                  onChange={(e) => setForm({ ...form, node_id: e.target.value })}
                  className="spu-input w-full text-xs"
                >
                  <option value="cluster">All Cluster</option>
                  {(snapshot?.nodes || []).map((n) => (
                    <option key={n.node_id} value={n.node_id}>{n.display_name || n.node_id}</option>
                  ))}
                </select>
              </div>
            </div>

            <div className="grid grid-cols-2 gap-2.5">
              <div>
                <label className="block text-[11px] font-semibold spu-text-secondary mb-1">Ground Truth Label</label>
                <select
                  value={form.label}
                  onChange={(e) => setForm({ ...form, label: e.target.value })}
                  className="spu-input w-full text-xs"
                >
                  <option value="positive_fault">Positive Fault / Anomaly</option>
                  <option value="benign_workload">Benign High Workload (FP Test)</option>
                  <option value="normal">Normal Baseline (FP Test)</option>
                </select>
              </div>
              <div>
                <label className="block text-[11px] font-semibold spu-text-secondary mb-1">Workload Condition</label>
                <select
                  value={form.workload_condition}
                  onChange={(e) => setForm({ ...form, workload_condition: e.target.value })}
                  className="spu-input w-full text-xs"
                >
                  <option value="idle">Idle / Low</option>
                  <option value="moderate">Moderate Load</option>
                  <option value="high_load">High Load</option>
                  <option value="benchmark">Benchmark / MPI Stress</option>
                  <option value="mixed">Mixed</option>
                </select>
              </div>
            </div>

            <div className="grid grid-cols-2 gap-2.5">
              <div>
                <label className="block text-[11px] font-semibold spu-text-secondary mb-1">Start UTC</label>
                <input
                  type="text"
                  required
                  value={form.start_utc}
                  onChange={(e) => setForm({ ...form, start_utc: e.target.value })}
                  className="spu-input w-full font-mono text-[11px]"
                />
              </div>
              <div>
                <label className="block text-[11px] font-semibold spu-text-secondary mb-1">End UTC (blank if live)</label>
                <input
                  type="text"
                  value={form.end_utc}
                  onChange={(e) => setForm({ ...form, end_utc: e.target.value })}
                  placeholder="2026-11-13T05:00:00Z"
                  className="spu-input w-full font-mono text-[11px]"
                />
              </div>
            </div>

            <div>
              <label className="block text-[11px] font-semibold spu-text-secondary mb-1">Notes</label>
              <textarea
                rows={2}
                value={form.notes}
                onChange={(e) => setForm({ ...form, notes: e.target.value })}
                placeholder="Hypothesis, injection parameters, or observed behavior..."
                className="spu-input w-full text-xs"
              />
            </div>

            <button type="submit" disabled={submitting} className="spu-btn-primary w-full">
              {submitting ? 'Saving...' : 'Save Labelled Experiment'}
            </button>
          </form>
        )}

        {/* Per-Experiment Detection Matrix */}
        <div className={`spu-card p-5 ${isAdmin ? 'lg:col-span-7' : 'lg:col-span-12'}`}>
          <h3 className="text-sm font-bold mb-3">
            Experiment Timeline &amp; Detector Match Matrix ({expResults.length})
          </h3>

          <div className="space-y-2.5 max-h-[460px] overflow-y-auto pr-1">
            {data.experiments.length === 0 ? (
              <div className="py-10 text-center text-xs spu-text-secondary">
                No experiments logged yet.
              </div>
            ) : (
              data.experiments.map((exp) => {
                const matchRow = expResults.find((r) => r.id === exp.id) || {};
                return (
                  <div key={exp.id} className="spu-subcard rounded-xl p-3.5 text-xs space-y-2">
                    <div className="flex flex-wrap items-center justify-between gap-2">
                      <div>
                        <span className="font-bold">{exp.name}</span>{' '}
                        <span className="font-mono text-[10px] spu-text-muted">
                          ({exp.category} • {exp.node_id} • {exp.workload_condition})
                        </span>
                      </div>
                      <span
                        className={`rounded px-2 py-0.5 font-mono text-[10px] font-bold uppercase ${
                          exp.label === 'positive_fault'
                            ? 'bg-rose-500/15 text-rose-400'
                            : 'bg-sky-500/15 text-sky-400'
                        }`}
                      >
                        {exp.label}
                      </span>
                    </div>

                    <div className="font-mono text-[11px] spu-text-secondary">
                      Window: {exp.start_utc} → {exp.end_utc || 'Ongoing'}
                    </div>

                    <div className="grid grid-cols-3 gap-2 pt-1 text-[11px]">
                      {[
                        { label: 'V7 IF', det: matchRow.v7_detected, delay: matchRow.v7_delay_min },
                        { label: 'LSTM V8', det: matchRow.lstm_v8_detected, delay: matchRow.lstm_delay_min },
                        { label: 'Thresholds', det: matchRow.telemetry_detected, delay: matchRow.telemetry_delay_min },
                      ].map((m) => (
                        <div key={m.label} className="rounded-lg bg-black/15 px-2.5 py-1.5 flex items-center justify-between">
                          <span className="font-semibold">{m.label}</span>
                          <span className="inline-flex items-center gap-1 font-mono">
                            {m.det ? (
                              <>
                                <CheckCircle2 className="h-3.5 w-3.5 text-emerald-400" />
                                {m.delay != null ? `${m.delay}m` : 'Hit'}
                              </>
                            ) : (
                              <>
                                <XCircle className="h-3.5 w-3.5 spu-text-muted" />
                                Miss
                              </>
                            )}
                          </span>
                        </div>
                      ))}
                    </div>

                    {isAdmin && (
                      <div className="flex justify-end gap-2 pt-1">
                        {!exp.end_utc && (
                          <button
                            onClick={() => handleCloseNow(exp)}
                            className="spu-btn-secondary text-[11px] py-1 px-2"
                          >
                            End Window Now
                          </button>
                        )}
                        <button
                          onClick={() => handleDelete(exp.id)}
                          className="rounded px-2 py-1 text-[11px] text-rose-400 hover:bg-rose-500/15 inline-flex items-center gap-1"
                        >
                          <Trash2 className="h-3 w-3" /> Delete
                        </button>
                      </div>
                    )}
                  </div>
                );
              })
            )}
          </div>
        </div>
      </div>
    </div>
  );
}
