import React, { useMemo, useState } from 'react';
import {
  BrainCircuit,
  Check,
  Copy,
  Flame,
  RefreshCw,
  ShieldAlert,
  Sparkles,
  Terminal,
} from 'lucide-react';
import {
  Area,
  CartesianGrid,
  ComposedChart,
  Legend,
  Line,
  ReferenceLine,
  ResponsiveContainer,
  Tooltip,
  XAxis,
  YAxis,
} from 'recharts';
import { useTheme } from '../context/ThemeContext.jsx';

export default function AiPredictionsPage({
  snapshot,
  selectedNodeId,
  onSelectNode,
  onReloadModels,
  onOpenFaultLab,
  busyAction,
}) {
  const { chartTheme } = useTheme();
  const [horizon, setHorizon] = useState('1h');
  const [copied, setCopied] = useState(false);

  const nodes = snapshot?.nodes || [];
  const modelStatus = snapshot?.model_status || {};
  const activeNode = useMemo(
    () => nodes.find((n) => n.node_id === selectedNodeId) || nodes[0] || null,
    [nodes, selectedNodeId]
  );

  const nodeSeries = snapshot?.history?.[activeNode?.node_id] || [];
  const evalMetrics = modelStatus.evaluation_metrics;

  const getHorizonProb = (node) => {
    if (!node) return 0;
    if (horizon === '6h') return (node.failure_prob_6h || 0) * 100;
    if (horizon === '24h') return (node.failure_prob_24h || 0) * 100;
    return (node.failure_prob_1h || 0) * 100;
  };

  const copyPlaybook = () => {
    if (!activeNode?.playbook_cmd) return;
    navigator.clipboard.writeText(activeNode.playbook_cmd);
    setCopied(true);
    setTimeout(() => setCopied(false), 1800);
  };

  return (
    <div className="space-y-5">
      {/* Header */}
      <div className="flex flex-wrap items-center justify-between gap-3">
        <div className="flex items-center gap-3">
          <div className="flex h-10 w-10 items-center justify-center rounded-xl bg-cyan-500/15 text-[var(--accent-cyan)]">
            <BrainCircuit className="h-5 w-5" />
          </div>
          <div>
            <h2 className="text-xl font-bold tracking-tight">AI &amp; Predictions</h2>
            <p className="text-xs spu-text-secondary">
              Predictive node failure analysis, multi-detector anomaly consensus &amp; root-cause attributions
            </p>
          </div>
        </div>

        <div className="flex flex-wrap items-center gap-2">
          {/* Horizon Picker */}
          <div className="spu-subcard inline-flex p-1 text-xs">
            {[
              { id: '1h', label: '1h Horizon' },
              { id: '6h', label: '6h Horizon' },
              { id: '24h', label: '24h Horizon' },
            ].map((h) => (
              <button
                key={h.id}
                onClick={() => setHorizon(h.id)}
                className={`rounded-md px-2.5 py-1 font-semibold transition ${
                  horizon === h.id
                    ? 'bg-[var(--accent-cyan-strong)] text-white'
                    : 'spu-text-secondary hover:text-[var(--text-primary)]'
                }`}
              >
                {h.label}
              </button>
            ))}
          </div>

          <button
            onClick={onReloadModels}
            disabled={busyAction}
            className="spu-btn-secondary inline-flex items-center gap-1.5"
          >
            <RefreshCw className={`h-3.5 w-3.5 ${busyAction ? 'animate-spin' : ''}`} />
            Reload .pkl Models
          </button>

          {snapshot?.mode === 'live_cluster_sim' && (
            <button
              onClick={onOpenFaultLab}
              className="spu-btn-secondary inline-flex items-center gap-1.5 text-rose-400 border-rose-500/40"
            >
              <Flame className="h-3.5 w-3.5" />
              Fault Test Lab
            </button>
          )}
        </div>
      </div>

      {/* Provenance Legend Strip */}
      <div className="spu-card flex flex-wrap items-center justify-between gap-3 px-4 py-3 text-xs">
        <div className="flex flex-wrap items-center gap-4">
          <span className="inline-flex items-center gap-1.5">
            <span className="h-2.5 w-2.5 rounded-full bg-emerald-400" />
            <strong>Live Observation:</strong> Measured Prometheus/Exporter telemetry
          </span>
          <span className="inline-flex items-center gap-1.5">
            <span className="h-2.5 w-2.5 rounded-full bg-cyan-400" />
            <strong>Anomaly Score:</strong> Unsupervised 4-detector consensus (IF, OCSVM, LOF, K-Means)
          </span>
          <span className="inline-flex items-center gap-1.5">
            <span className="h-2.5 w-2.5 rounded-full bg-rose-400" />
            <strong>Model Prediction:</strong> Supervised failure probability ({modelStatus.engine_label})
          </span>
        </div>
      </div>

      {/* Per-Node Prediction Matrix */}
      <section className="grid grid-cols-1 gap-3.5 sm:grid-cols-2 xl:grid-cols-4">
        {nodes.map((node) => {
          const prob = getHorizonProb(node);
          const selected = activeNode?.node_id === node.node_id;
          const votes = node.consensus_votes || {};

          return (
            <div
              key={node.node_id}
              onClick={() => onSelectNode(node.node_id)}
              className={`spu-card cursor-pointer p-4 transition ${
                selected ? 'ring-2 ring-[var(--accent-cyan)]' : 'hover:border-[var(--accent-cyan)]'
              }`}
            >
              <div className="flex items-start justify-between">
                <div>
                  <div className="text-sm font-bold">{node.display_name || node.node_id}</div>
                  <div className="text-[11px] spu-text-muted">
                    Class: <strong>{node.health_classification || 'Healthy'}</strong>
                  </div>
                </div>
                <span
                  className={`rounded px-2 py-0.5 text-[10px] font-bold ${
                    prob >= 40
                      ? 'bg-rose-500 text-white'
                      : prob >= 18
                      ? 'bg-amber-500 text-slate-950'
                      : prob >= 1.5
                      ? 'bg-sky-500/20 text-sky-400'
                      : 'bg-emerald-500/15 text-emerald-400'
                  }`}
                >
                  {node.alert_priority === 'OK' ? 'NORMAL' : node.alert_priority}
                </span>
              </div>

              <div className="mt-3 grid grid-cols-2 gap-2">
                <div className="spu-subcard p-2.5">
                  <div className="text-[10px] uppercase spu-text-muted">
                    {horizon} Failure Prob
                  </div>
                  <div
                    className={`font-mono text-lg font-extrabold ${
                      prob >= 40
                        ? 'text-rose-400'
                        : prob >= 18
                        ? 'text-amber-400'
                        : 'text-emerald-400'
                    }`}
                  >
                    {prob.toFixed(2)}%
                  </div>
                </div>

                <div className="spu-subcard p-2.5">
                  <div className="text-[10px] uppercase spu-text-muted">Anomaly Score</div>
                  <div className="font-mono text-lg font-extrabold text-[var(--accent-cyan)]">
                    {((node.anomaly_score || 0) * 100).toFixed(1)}%
                  </div>
                </div>
              </div>

              <div className="mt-3 flex items-center justify-between text-[11px]">
                <span className="spu-text-secondary">
                  Early Warning: <strong className="font-mono">{node.persistence_progress}</strong>
                </span>
                <div className="flex gap-1">
                  {[
                    ['IF', votes.isolation_forest],
                    ['SVM', votes.one_class_svm],
                    ['LOF', votes.lof],
                    ['KM', votes.kmeans],
                  ].map(([tag, active]) => (
                    <span
                      key={tag}
                      className={`rounded px-1 py-0.5 font-mono text-[9px] font-bold ${
                        active
                          ? 'bg-rose-500/25 text-rose-400 border border-rose-500/40'
                          : 'spu-subcard spu-text-muted'
                      }`}
                    >
                      {tag}
                    </span>
                  ))}
                </div>
              </div>

              <div className="mt-2 border-t pt-2 text-[10.5px] spu-border spu-text-muted flex justify-between">
                <span>
                  Confidence:{' '}
                  {node.prediction_confidence != null
                    ? `${(node.prediction_confidence * 100).toFixed(1)}%`
                    : 'N/A (No ensemble .pkl)'}
                </span>
                <span className="font-mono">{node.fault_class}</span>
              </div>
            </div>
          );
        })}
      </section>

      {/* Main Intelligence Row: Prediction History Chart + SHAP / Explainability */}
      {activeNode && (
        <section className="grid grid-cols-1 gap-4 lg:grid-cols-12">
          {/* Left: Historical Observations vs Predicted Failure Risk */}
          <div className="spu-card p-5 lg:col-span-7">
            <div className="mb-3 flex flex-wrap items-center justify-between gap-2">
              <div>
                <h3 className="text-sm font-bold">
                  Prediction History &amp; Observed Stress Overlay —{' '}
                  <span className="text-[var(--accent-cyan)]">
                    {activeNode.display_name || activeNode.node_id}
                  </span>
                </h3>
                <p className="text-xs spu-text-secondary">
                  1h &amp; 6h predicted failure risk (%) overlaid against unsupervised anomaly score &amp; observed memory %
                </p>
              </div>
              <span className="rounded-md px-2 py-1 font-mono text-[11px] spu-subcard">
                Source: {activeNode.prediction_source}
              </span>
            </div>

            <div className="h-72">
              <ResponsiveContainer width="100%" height="100%">
                <ComposedChart data={nodeSeries}>
                  <CartesianGrid strokeDasharray="3 3" stroke={chartTheme.grid} />
                  <XAxis dataKey="time" tick={{ fill: chartTheme.axis, fontSize: 10 }} />
                  <YAxis domain={[0, 100]} tick={{ fill: chartTheme.axis, fontSize: 10 }} width={34} />
                  <Tooltip contentStyle={chartTheme.tooltipStyle} />
                  <Legend wrapperStyle={{ fontSize: '11px' }} />
                  <ReferenceLine y={40} stroke={chartTheme.red} strokeDasharray="4 4" />
                  <ReferenceLine y={18} stroke={chartTheme.amber} strokeDasharray="4 4" />
                  <Area
                    type="monotone"
                    dataKey="failure_prob_pct"
                    name="Predicted 1h Failure %"
                    stroke={chartTheme.red}
                    fill={chartTheme.red}
                    fillOpacity={0.18}
                    strokeWidth={2.2}
                    isAnimationActive={false}
                  />
                  <Line
                    type="monotone"
                    dataKey="failure_prob_6h_pct"
                    name="Predicted 6h Failure %"
                    stroke={chartTheme.amber}
                    strokeDasharray="4 2"
                    strokeWidth={1.8}
                    dot={false}
                    isAnimationActive={false}
                  />
                  <Line
                    type="monotone"
                    dataKey="anomaly_score_pct"
                    name="Unsupervised Anomaly %"
                    stroke={chartTheme.cyan}
                    strokeWidth={2}
                    dot={false}
                    isAnimationActive={false}
                  />
                  <Line
                    type="monotone"
                    dataKey="memory"
                    name="Observed Memory %"
                    stroke={chartTheme.purple}
                    strokeWidth={1.5}
                    dot={false}
                    connectNulls={false}
                    isAnimationActive={false}
                  />
                </ComposedChart>
              </ResponsiveContainer>
            </div>

            {/* Model Registry & Honest Performance Monitor */}
            <div className="mt-4 rounded-xl p-3.5 spu-subcard">
              <div className="flex items-center justify-between">
                <div className="flex items-center gap-2 text-xs font-bold">
                  <ShieldAlert className="h-4 w-4 text-[var(--accent-cyan)]" />
                  Model Registry &amp; Validation Monitor
                </div>
                <span className="font-mono text-[11px] spu-text-secondary">
                  {modelStatus.loaded_files?.length || 0} artifact(s) loaded
                </span>
              </div>

              {evalMetrics ? (
                <div className="mt-2.5 grid grid-cols-2 gap-2 sm:grid-cols-4 text-xs">
                  {Object.entries(evalMetrics).map(([k, v]) => (
                    <div key={k} className="rounded-lg bg-[var(--bg-card)] p-2">
                      <span className="block text-[10px] uppercase spu-text-muted">{k}</span>
                      <strong className="font-mono">{String(v)}</strong>
                    </div>
                  ))}
                </div>
              ) : (
                <p className="mt-2 text-xs spu-text-secondary">
                  Active Engine: <strong>{modelStatus.engine_label}</strong>. Validation accuracy/AUC metrics are only displayed when exported from your Phase 1 notebook (<code className="font-mono">backend/models/model_metrics.json</code> &amp; <code className="font-mono">.pkl</code> files) — no synthetic accuracy figures are fabricated.
                </p>
              )}
            </div>
          </div>

          {/* Right: Feature Importance / Attribution + Anomaly Diagnostic Playbook */}
          <div className="spu-card flex flex-col justify-between p-5 lg:col-span-5">
            <div>
              <div className="flex items-center justify-between border-b pb-3 spu-border">
                <div className="flex items-center gap-2">
                  <Sparkles className="h-4 w-4 text-[var(--accent-cyan)]" />
                  <h3 className="text-sm font-bold">
                    {modelStatus.shap_or_importances_available
                      ? 'SHAP / Model Feature Importance'
                      : 'Anomaly Root-Cause Attributions'}
                  </h3>
                </div>
                <span className="rounded px-2 py-0.5 font-mono text-[11px] spu-subcard text-[var(--accent-cyan)]">
                  {activeNode.fault_label}
                </span>
              </div>

              <div className="mt-3 space-y-2.5">
                {(activeNode.top_features || []).map((feat) => {
                  const pct = Math.round((feat.impact || 0) * 100);
                  return (
                    <div key={feat.feature} className="rounded-xl p-3 spu-subcard">
                      <div className="flex items-center justify-between text-xs">
                        <span className="font-mono font-semibold">{feat.feature}</span>
                        <span className="font-mono text-[var(--accent-cyan)]">
                          {feat.value} {feat.unit} ({pct}% impact)
                        </span>
                      </div>
                      <div className="mt-1.5 h-1.5 w-full overflow-hidden rounded-full bg-[var(--bg-card)]">
                        <div
                          className={`h-full ${
                            pct >= 65
                              ? 'bg-rose-500'
                              : pct >= 30
                              ? 'bg-amber-400'
                              : 'bg-cyan-400'
                          }`}
                          style={{ width: `${Math.max(4, Math.min(100, pct))}%` }}
                        />
                      </div>
                      <div className="mt-1 text-[11px] spu-text-muted">{feat.detail}</div>
                    </div>
                  );
                })}
              </div>
            </div>

            {/* Diagnostic Playbook */}
            <div className="mt-4 rounded-xl border border-cyan-500/30 p-3.5 spu-subcard">
              <div className="flex items-center justify-between">
                <span className="inline-flex items-center gap-1.5 text-xs font-bold text-[var(--accent-cyan)]">
                  <Terminal className="h-3.5 w-3.5" />
                  Recommended Diagnostic Playbook
                </span>
                <button
                  onClick={copyPlaybook}
                  className="spu-btn-secondary inline-flex items-center gap-1 px-2 py-1 text-[11px]"
                >
                  {copied ? (
                    <>
                      <Check className="h-3 w-3 text-emerald-400" /> Copied
                    </>
                  ) : (
                    <>
                      <Copy className="h-3 w-3" /> Copy
                    </>
                  )}
                </button>
              </div>
              <p className="mt-1.5 text-xs leading-relaxed spu-text-secondary">
                {activeNode.playbook_advice}
              </p>
              <pre
                style={{ backgroundColor: 'var(--bg-log)' }}
                className="mt-2 overflow-x-auto rounded-lg p-2.5 font-mono text-[11px] text-amber-400 border spu-border"
              >
                {activeNode.playbook_cmd}
              </pre>
            </div>
          </div>
        </section>
      )}
    </div>
  );
}
