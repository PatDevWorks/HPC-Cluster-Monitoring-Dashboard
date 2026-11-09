import React from 'react';
import { PlayCircle, ShieldOff, Thermometer, HardDrive, Cpu } from 'lucide-react';

const PRIORITY_STYLES = {
  P1: {
    card: 'border-rose-500/70 bg-rose-950/20 shadow-lg shadow-rose-950/30',
    badge: 'bg-rose-500 text-white',
    label: 'P1 CRITICAL',
  },
  P2: {
    card: 'border-amber-500/60 bg-amber-950/15',
    badge: 'bg-amber-500 text-slate-950',
    label: 'P2 WARNING',
  },
  P3: {
    card: 'border-sky-500/50 bg-sky-950/15',
    badge: 'bg-sky-500/30 text-sky-200 ring-1 ring-sky-400/50',
    label: 'P3 WATCH',
  },
  MAINTENANCE: {
    card: 'border-purple-500/40 bg-purple-950/15 opacity-85',
    badge: 'bg-purple-500/30 text-purple-200',
    label: 'MAINTENANCE',
  },
  OK: {
    card: 'border-slate-800 bg-slate-900/70 hover:border-slate-700',
    badge: 'bg-emerald-500/20 text-emerald-300 ring-1 ring-emerald-500/30',
    label: 'HEALTHY',
  },
};

export default function NodeHealthGrid({
  nodes,
  selectedNodeId,
  onSelectNode,
  onDrainNode,
  onResumeNode,
}) {
  if (!nodes || nodes.length === 0) return null;

  const compactGrid = nodes.length > 4;

  return (
    <section>
      <div className="mb-2.5 flex items-center justify-between">
        <h2 className="text-sm font-semibold uppercase tracking-wider text-slate-300">
          Cluster Node Health &amp; Multi-Model Consensus Matrix
        </h2>
        <span className="text-xs text-slate-400">
          Click any node to inspect synchronized telemetry, SHAP attributions &amp; playbooks
        </span>
      </div>

      <div
        className={`grid gap-3 ${
          compactGrid
            ? 'grid-cols-1 sm:grid-cols-2 lg:grid-cols-4 xl:grid-cols-6'
            : 'grid-cols-1 md:grid-cols-2 xl:grid-cols-4'
        }`}
      >
        {nodes.map((node) => {
          const prio = node.alert_priority || 'OK';
          const st = PRIORITY_STYLES[prio] || PRIORITY_STYLES.OK;
          const isSelected = node.node_id === selectedNodeId;
          const isDrained = String(node.slurm_state || '').includes('DRAIN');
          const probPct = ((node.failure_prob_1h || 0) * 100).toFixed(1);
          const votes = node.consensus_votes || {};
          const up = node.up === 1;

          return (
            <div
              key={node.node_id}
              onClick={() => onSelectNode(node.node_id)}
              className={`cursor-pointer rounded-xl border p-3.5 transition-all ${st.card} ${
                isSelected ? 'ring-2 ring-cyan-400' : ''
              }`}
            >
              {/* Card Header */}
              <div className="flex items-start justify-between gap-2">
                <div>
                  <div className="flex items-center gap-1.5">
                    <span
                      className={`h-2.5 w-2.5 rounded-full ${
                        !up
                          ? 'bg-rose-500'
                          : isDrained
                          ? 'bg-amber-400'
                          : 'bg-emerald-400'
                      }`}
                    />
                    <span className="font-mono text-sm font-bold text-white">
                      {node.node_id}
                    </span>
                  </div>
                  <div className="mt-0.5 font-mono text-[11px] text-slate-400">
                    {node.ip} • {node.cpu_cores}c / {node.memory_gib}G
                  </div>
                </div>

                <span className={`rounded px-1.5 py-0.5 text-[10px] font-bold ${st.badge}`}>
                  {st.label}
                </span>
              </div>

              {/* Risk & Consensus Strip */}
              <div className="mt-3 flex items-center justify-between rounded-lg bg-slate-950/75 px-2.5 py-2">
                <div>
                  <div className="text-[10px] uppercase text-slate-400">1h Failure Risk</div>
                  <div
                    className={`font-mono text-base font-bold ${
                      Number(probPct) >= 40
                        ? 'text-rose-400'
                        : Number(probPct) >= 18
                        ? 'text-amber-300'
                        : Number(probPct) >= 1.5
                        ? 'text-sky-300'
                        : 'text-emerald-300'
                    }`}
                  >
                    {probPct}%
                  </div>
                </div>

                <div className="text-right">
                  <div className="text-[10px] uppercase text-slate-400">
                    Consensus ({node.consensus_count || 0}/4)
                  </div>
                  <div className="mt-1 flex items-center justify-end gap-1">
                    {[
                      ['IF', votes.isolation_forest],
                      ['SVM', votes.one_class_svm],
                      ['LOF', votes.lof],
                      ['KM', votes.kmeans],
                    ].map(([tag, active]) => (
                      <span
                        key={tag}
                        title={`${tag}: ${active ? 'Anomaly Flagged' : 'Normal'}`}
                        className={`rounded px-1 py-0.5 font-mono text-[9px] font-bold ${
                          active
                            ? 'bg-rose-500/30 text-rose-200 ring-1 ring-rose-500/50'
                            : 'bg-slate-800 text-slate-500'
                        }`}
                      >
                        {tag}
                      </span>
                    ))}
                  </div>
                </div>
              </div>

              {/* Key Telemetry Bars */}
              {up ? (
                <div className="mt-3 space-y-1.5 text-[11px]">
                  <div className="flex items-center justify-between">
                    <span className="inline-flex items-center gap-1 text-slate-400">
                      <Cpu className="h-3 w-3" /> CPU / IOWait
                    </span>
                    <span className="font-mono text-slate-200">
                      {node.cpu_utilization_percent?.toFixed(0) ?? 0}% /{' '}
                      <span
                        className={
                          (node.cpu_iowait_percent || 0) > 10 ? 'text-amber-300' : 'text-slate-400'
                        }
                      >
                        {node.cpu_iowait_percent?.toFixed(1) ?? 0}%
                      </span>
                    </span>
                  </div>

                  <div className="flex items-center justify-between">
                    <span className="inline-flex items-center gap-1 text-slate-400">
                      <HardDrive className="h-3 w-3" /> RAM / Scratch
                    </span>
                    <span className="font-mono text-slate-200">
                      <span
                        className={
                          (node.memory_used_percent || 0) > 85 ? 'text-rose-300' : 'text-slate-200'
                        }
                      >
                        {node.memory_used_percent?.toFixed(1) ?? 0}%
                      </span>{' '}
                      /{' '}
                      <span
                        className={
                          (node.scratch_used_percent || 0) > 88 ? 'text-rose-300' : 'text-slate-400'
                        }
                      >
                        {node.scratch_used_percent?.toFixed(0) ?? 0}%
                      </span>
                    </span>
                  </div>

                  <div className="flex items-center justify-between">
                    <span className="inline-flex items-center gap-1 text-slate-400">
                      <Thermometer className="h-3 w-3" /> Temp / Load
                    </span>
                    <span className="font-mono text-slate-200">
                      {node.cpu_temperature_celsius != null
                        ? `${node.cpu_temperature_celsius.toFixed(1)}°C`
                        : 'VM N/A'}{' '}
                      • {node.normalized_load1?.toFixed(2)}x
                    </span>
                  </div>
                </div>
              ) : (
                <div className="mt-3 rounded-lg border border-rose-500/30 bg-rose-950/30 p-2 text-center text-xs font-medium text-rose-200">
                  {node.fault_class === 'scrape_gap'
                    ? 'Scrape Gap (Exporter Timeout)'
                    : 'Node Unreachable (up=0)'}
                </div>
              )}

              {/* Footer: Slurm State + 1-Click Drain / Resume */}
              <div className="mt-3 flex items-center justify-between border-t border-slate-800/80 pt-2.5 text-[11px]">
                <span className="font-mono text-[10px] text-slate-400">
                  Slurm:{' '}
                  <strong className={isDrained ? 'text-amber-300' : 'text-slate-200'}>
                    {node.slurm_state}
                  </strong>
                </span>

                {node.role !== 'management' && (
                  <div onClick={(e) => e.stopPropagation()}>
                    {isDrained ? (
                      <button
                        onClick={() => onResumeNode(node.node_id)}
                        className="inline-flex items-center gap-1 rounded-md bg-emerald-500/20 px-2 py-1 text-[11px] font-semibold text-emerald-300 ring-1 ring-emerald-500/40 hover:bg-emerald-500/30"
                      >
                        <PlayCircle className="h-3 w-3" />
                        Resume
                      </button>
                    ) : (
                      <button
                        onClick={() =>
                          onDrainNode(
                            node.node_id,
                            `AI Early Warning (${node.fault_label || 'Risk'} - ${probPct}%)`
                          )
                        }
                        className={`inline-flex items-center gap-1 rounded-md px-2 py-1 text-[11px] font-semibold transition ${
                          prio === 'P1' || prio === 'P2'
                            ? 'bg-amber-500 text-slate-950 hover:bg-amber-400'
                            : 'bg-slate-800 text-slate-300 hover:bg-slate-700'
                        }`}
                      >
                        <ShieldOff className="h-3 w-3" />
                        Drain Node
                      </button>
                    )}
                  </div>
                )}
              </div>
            </div>
          );
        })}
      </div>
    </section>
  );
}
