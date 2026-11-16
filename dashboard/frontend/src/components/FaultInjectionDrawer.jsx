import React, { useState } from 'react';
import { Flame, RotateCcw, X, Zap } from 'lucide-react';

const FAULT_SCENARIOS = [
  {
    id: 'memory_exhaustion',
    label: 'Gradual Memory Leak (EDAC / OOM Precursor)',
    desc: 'Simulates an MPI rank leaking ~2.8% RAM per tick + swap write surge. Triggers 2-of-2 P2 -> P1 escalation.',
  },
  {
    id: 'cpu_saturation',
    label: 'Compute CPU Saturation (Runaway Thread / Fork)',
    desc: 'Ramps single-node CPU utilization above 95% and normalized load past warning thresholds relative to peer nodes.',
  },
  {
    id: 'disk_failure',
    label: 'SAS Disk / /scratch I/O Medium Error',
    desc: 'Spikes CPU iowait > 35% and disk active time > 90% while collapsing write throughput.',
  },
  {
    id: 'mpi_straggler',
    label: 'Degraded MPI Straggler Node (Peer Asymmetry)',
    desc: 'Drops single-node CPU & 10GbE MPI throughput by 45% while peers stay busy—caught by Peer-Deviation & LOF.',
  },
  {
    id: 'network_degradation',
    label: '10GbE SFP+ DAC CRC / Packet Error Surge',
    desc: 'Injects continuous RX/TX frame errors on the cluster interconnect.',
  },
  {
    id: 'scrape_gap',
    label: 'Prometheus Exporter Scrape Gap (up=0)',
    desc: 'Tests that brief exporter timeouts are distinguished from confirmed hardware crashes.',
  },
];

export default function FaultInjectionDrawer({
  open,
  onClose,
  computeNodes,
  activeFaults,
  onInject,
  onClear,
}) {
  const [targetNode, setTargetNode] = useState(
    computeNodes?.[0]?.node_id || 'compute-01'
  );

  if (!open) return null;

  return (
    <div className="fixed inset-0 z-50 flex justify-end bg-black/60 backdrop-blur-xs">
      <div
        style={{
          backgroundColor: 'var(--bg-card)',
          borderLeft: '1px solid var(--border-subtle)',
        }}
        className="flex h-full w-full max-w-md flex-col p-5 shadow-2xl"
      >
        <div className="flex items-center justify-between border-b pb-3 spu-border">
          <div className="flex items-center gap-2">
            <Flame className="h-5 w-5 text-rose-400" />
            <h3 className="text-base font-bold">Fault-Injection Test Lab</h3>
          </div>
          <button
            onClick={onClose}
            className="rounded-lg p-1 spu-text-secondary hover:bg-[var(--bg-hover)]"
          >
            <X className="h-4 w-4" />
          </button>
        </div>

        <p className="mt-3 text-xs leading-relaxed spu-text-secondary">
          Available in Simulator mode: trigger controlled anomalies on a compute node to test threshold checks, persistence gating, V7/LSTM monitoring, and Slurm drain workflows. Note: real cluster hardware lacks hwmon thermal/fan/power sensors.
        </p>

        <div className="mt-4">
          <label className="block text-xs font-semibold uppercase tracking-wider spu-text-secondary">
            Target Compute Node
          </label>
          <div className="mt-1.5 grid grid-cols-3 gap-2">
            {computeNodes.map((n) => (
              <button
                key={n.node_id}
                onClick={() => setTargetNode(n.node_id)}
                className={`rounded-lg border px-2.5 py-2 font-mono text-xs font-semibold transition ${
                  targetNode === n.node_id
                    ? 'border-[var(--accent-cyan)] bg-cyan-500/15 text-[var(--accent-cyan)]'
                    : 'spu-subcard spu-text-secondary'
                }`}
              >
                {n.display_name || n.node_id}
              </button>
            ))}
          </div>
        </div>

        <div className="mt-4 flex-1 space-y-2.5 overflow-y-auto pr-1">
          {FAULT_SCENARIOS.map((sc) => {
            const isRunningOnNode = activeFaults?.[targetNode]?.type === sc.id;
            return (
              <div
                key={sc.id}
                className={`rounded-xl border p-3 transition spu-subcard ${
                  isRunningOnNode ? 'border-rose-500/70' : ''
                }`}
              >
                <div className="flex items-start justify-between gap-2">
                  <div className="text-xs font-semibold">{sc.label}</div>
                  <button
                    onClick={() => onInject(targetNode, sc.id)}
                    className="inline-flex shrink-0 items-center gap-1 rounded-md bg-rose-600 px-2.5 py-1 text-[11px] font-semibold text-white hover:bg-rose-500"
                  >
                    <Zap className="h-3 w-3" />
                    Inject
                  </button>
                </div>
                <p className="mt-1 text-[11px] leading-relaxed spu-text-secondary">
                  {sc.desc}
                </p>
              </div>
            );
          })}
        </div>

        <div className="mt-4 border-t pt-3 spu-border">
          <button
            onClick={() => onClear(null)}
            className="spu-btn-secondary inline-flex w-full items-center justify-center gap-2 py-2.5"
          >
            <RotateCcw className="h-4 w-4 text-emerald-400" />
            Clear All Injected Faults
          </button>
        </div>
      </div>
    </div>
  );
}
