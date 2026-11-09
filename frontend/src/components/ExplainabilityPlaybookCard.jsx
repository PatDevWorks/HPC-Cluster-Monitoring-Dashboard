import React, { useState } from 'react';
import { Check, Copy, Sparkles, Terminal, ShieldOff } from 'lucide-react';

export default function ExplainabilityPlaybookCard({
  selectedNode,
  modelStatus,
  onDrainNode,
}) {
  const [copied, setCopied] = useState(false);

  if (!selectedNode) return null;

  const topFeatures = selectedNode.top_features || [];
  const votes = selectedNode.consensus_votes || {};
  const detectorsMeta = modelStatus?.detectors || {};
  const isDrained = String(selectedNode.slurm_state || '').includes('DRAIN');

  const copyCommand = () => {
    if (!selectedNode.playbook_cmd) return;
    navigator.clipboard.writeText(selectedNode.playbook_cmd);
    setCopied(true);
    setTimeout(() => setCopied(false), 1800);
  };

  return (
    <div className="flex flex-col justify-between rounded-2xl border border-slate-800/90 bg-slate-900/60 p-4">
      <div>
        {/* Header */}
        <div className="flex items-center justify-between border-b border-slate-800/80 pb-3">
          <div className="flex items-center gap-2">
            <Sparkles className="h-4 w-4 text-cyan-400" />
            <h3 className="text-sm font-bold text-white">
              Root-Cause Explainability &amp; Admin Playbook ({selectedNode.node_id})
            </h3>
          </div>
          <span className="rounded-md bg-slate-800 px-2 py-0.5 font-mono text-[11px] text-cyan-300">
            {selectedNode.fault_class}
          </span>
        </div>

        {/* Top-3 Contributing Features (SHAP / Attribution Contract) */}
        <div className="mt-3">
          <div className="text-xs font-semibold text-slate-300">
            Top-3 Contributing Signals (Why This Score?)
          </div>
          {topFeatures.length === 0 ? (
            <p className="mt-2 text-xs text-slate-400">
              Node inside scheduled maintenance window — scoring suppressed.
            </p>
          ) : (
            <div className="mt-2 space-y-2.5">
              {topFeatures.map((feat) => {
                const pct = Math.round((feat.impact || 0) * 100);
                return (
                  <div
                    key={feat.feature}
                    className="rounded-xl border border-slate-800/80 bg-slate-950/70 p-2.5"
                  >
                    <div className="flex items-center justify-between text-xs">
                      <span className="font-mono font-semibold text-slate-200">
                        {feat.feature}
                      </span>
                      <span className="font-mono text-cyan-300">
                        {feat.value} {feat.unit} • Impact {pct}%
                      </span>
                    </div>
                    <div className="mt-1.5 h-1.5 w-full overflow-hidden rounded-full bg-slate-800">
                      <div
                        className={`h-full transition-all duration-300 ${
                          pct >= 65
                            ? 'bg-rose-500'
                            : pct >= 30
                            ? 'bg-amber-400'
                            : 'bg-cyan-400'
                        }`}
                        style={{ width: `${Math.max(4, Math.min(100, pct))}%` }}
                      />
                    </div>
                    <div className="mt-1 text-[11px] text-slate-400">{feat.detail}</div>
                  </div>
                );
              })}
            </div>
          )}
        </div>

        {/* Multi-Model Consensus Breakdown */}
        <div className="mt-4">
          <div className="text-xs font-semibold text-slate-300">
            Ensemble Detector Agreement ({selectedNode.consensus_count || 0}/4 Unsupervised)
          </div>
          <div className="mt-2 grid grid-cols-2 gap-2 text-xs">
            {[
              ['isolation_forest', 'Isolation Forest', votes.isolation_forest],
              ['one_class_svm', 'One-Class SVM', votes.one_class_svm],
              ['lof', 'Local Outlier Factor', votes.lof],
              ['kmeans', 'K-Means Distance', votes.kmeans],
            ].map(([key, name, flagged]) => (
              <div
                key={key}
                className="flex items-center justify-between rounded-lg border border-slate-800 bg-slate-950/60 px-2.5 py-1.5"
              >
                <div>
                  <div className="text-[11px] font-medium text-slate-200">{name}</div>
                  <div className="text-[9px] uppercase text-slate-500">
                    {detectorsMeta[key] === 'pkl' ? '.pkl active' : 'placeholder'}
                  </div>
                </div>
                <span
                  className={`rounded px-1.5 py-0.5 text-[10px] font-bold ${
                    flagged
                      ? 'bg-rose-500/25 text-rose-300 ring-1 ring-rose-500/40'
                      : 'bg-emerald-500/15 text-emerald-300'
                  }`}
                >
                  {flagged ? 'ANOMALY' : 'NORMAL'}
                </span>
              </div>
            ))}
          </div>
        </div>
      </div>

      {/* Recommended Admin Playbook */}
      <div className="mt-4 rounded-xl border border-cyan-500/30 bg-slate-950 p-3">
        <div className="flex items-center justify-between">
          <span className="inline-flex items-center gap-1.5 text-xs font-semibold text-cyan-300">
            <Terminal className="h-3.5 w-3.5" />
            Automated Diagnostic &amp; Mitigation Playbook
          </span>
          <button
            onClick={copyCommand}
            className="inline-flex items-center gap-1 rounded-md bg-slate-800 px-2 py-1 text-[11px] text-slate-200 hover:bg-slate-700"
          >
            {copied ? (
              <>
                <Check className="h-3 w-3 text-emerald-400" />
                Copied
              </>
            ) : (
              <>
                <Copy className="h-3 w-3" />
                Copy Cmd
              </>
            )}
          </button>
        </div>

        <p className="mt-1.5 text-[11px] leading-relaxed text-slate-300">
          {selectedNode.playbook_advice}
        </p>

        <pre className="mt-2 overflow-x-auto rounded-lg bg-slate-900 p-2 font-mono text-[11px] text-amber-200">
          {selectedNode.playbook_cmd}
        </pre>

        {selectedNode.role !== 'management' && !isDrained && (
          <button
            onClick={() =>
              onDrainNode(
                selectedNode.node_id,
                `Playbook mitigation: ${selectedNode.fault_label}`
              )
            }
            className="mt-2.5 inline-flex w-full items-center justify-center gap-1.5 rounded-lg bg-amber-500/20 py-1.5 text-xs font-semibold text-amber-200 ring-1 ring-amber-500/40 hover:bg-amber-500/30"
          >
            <ShieldOff className="h-3.5 w-3.5" />
            Execute Graceful Slurm Drain on {selectedNode.node_id}
          </button>
        )}
      </div>
    </div>
  );
}
