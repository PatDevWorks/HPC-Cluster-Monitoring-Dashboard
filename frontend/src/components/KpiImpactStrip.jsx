import React from 'react';
import {
  Activity,
  AlertTriangle,
  BatteryCharging,
  CheckCircle2,
  Cpu,
  ShieldAlert,
} from 'lucide-react';

export default function KpiImpactStrip({ kpis }) {
  if (!kpis) return null;

  const peakRisk = kpis.peak_failure_prob_pct ?? 0;
  const straggler = kpis.peak_straggler_pct ?? 0;

  return (
    <section className="grid grid-cols-2 gap-3 md:grid-cols-3 xl:grid-cols-6">
      {/* 1. Node Availability */}
      <div className="rounded-xl border border-slate-800/90 bg-slate-900/70 p-3.5">
        <div className="flex items-center justify-between text-xs text-slate-400">
          <span>Cluster Nodes</span>
          <CheckCircle2 className="h-4 w-4 text-emerald-400" />
        </div>
        <div className="mt-2 flex items-baseline gap-2">
          <span className="text-2xl font-bold text-white">
            {kpis.nodes_online}/{kpis.nodes_total}
          </span>
          <span className="text-xs text-emerald-400">Online</span>
        </div>
        <div className="mt-1 text-[11px] text-slate-400">
          {kpis.nodes_drained > 0 ? (
            <span className="text-amber-300">{kpis.nodes_drained} Proactively Drained</span>
          ) : (
            'All compute queues active'
          )}
        </div>
      </div>

      {/* 2. Smart Priority Alert Episodes */}
      <div className="rounded-xl border border-slate-800/90 bg-slate-900/70 p-3.5">
        <div className="flex items-center justify-between text-xs text-slate-400">
          <span>Active Alert Episodes</span>
          <ShieldAlert
            className={`h-4 w-4 ${
              kpis.p1_count > 0
                ? 'text-rose-400'
                : kpis.p2_count > 0
                ? 'text-amber-400'
                : 'text-cyan-400'
            }`}
          />
        </div>
        <div className="mt-2 flex items-baseline gap-2">
          <span className="text-2xl font-bold text-white">{kpis.active_episodes_total}</span>
          <div className="flex items-center gap-1 text-[11px] font-semibold">
            <span className="rounded bg-rose-500/20 px-1.5 py-0.5 text-rose-300">
              P1:{kpis.p1_count}
            </span>
            <span className="rounded bg-amber-500/20 px-1.5 py-0.5 text-amber-300">
              P2:{kpis.p2_count}
            </span>
            <span className="rounded bg-sky-500/20 px-1.5 py-0.5 text-sky-300">
              P3:{kpis.p3_count}
            </span>
          </div>
        </div>
        <div className="mt-1 text-[11px] text-slate-400">2-of-2 &amp; 3-of-3 persistence gated</div>
      </div>

      {/* 3. Peak 1-Hour Failure Probability */}
      <div className="rounded-xl border border-slate-800/90 bg-slate-900/70 p-3.5">
        <div className="flex items-center justify-between text-xs text-slate-400">
          <span>Peak 1h Failure Risk</span>
          <AlertTriangle
            className={`h-4 w-4 ${
              peakRisk >= 40
                ? 'text-rose-400'
                : peakRisk >= 18
                ? 'text-amber-400'
                : 'text-emerald-400'
            }`}
          />
        </div>
        <div className="mt-2 flex items-baseline gap-2">
          <span
            className={`text-2xl font-bold ${
              peakRisk >= 40
                ? 'text-rose-400'
                : peakRisk >= 18
                ? 'text-amber-300'
                : 'text-emerald-300'
            }`}
          >
            {peakRisk.toFixed(1)}%
          </span>
          <span className="text-xs text-slate-400">horizon=60m</span>
        </div>
        <div className="mt-1.5 h-1.5 w-full overflow-hidden rounded-full bg-slate-800">
          <div
            className={`h-full transition-all duration-500 ${
              peakRisk >= 40
                ? 'bg-rose-500'
                : peakRisk >= 18
                ? 'bg-amber-400'
                : 'bg-emerald-400'
            }`}
            style={{ width: `${Math.min(100, Math.max(3, peakRisk))}%` }}
          />
        </div>
      </div>

      {/* 4. MPI Symmetry / Straggler Score */}
      <div className="rounded-xl border border-slate-800/90 bg-slate-900/70 p-3.5">
        <div className="flex items-center justify-between text-xs text-slate-400">
          <span>MPI Straggler Index</span>
          <Activity className="h-4 w-4 text-cyan-400" />
        </div>
        <div className="mt-2 flex items-baseline gap-2">
          <span
            className={`text-2xl font-bold ${
              straggler >= 45 ? 'text-amber-300' : 'text-cyan-300'
            }`}
          >
            {straggler.toFixed(0)}%
          </span>
          <span className="text-xs text-slate-400">
            {straggler >= 45 ? 'Asymmetric Lag' : 'Balanced Mesh'}
          </span>
        </div>
        <div className="mt-1 text-[11px] text-slate-400">
          Cross-node peer median comparison
        </div>
      </div>

      {/* 5. Core-Hours Protected */}
      <div className="rounded-xl border border-slate-800/90 bg-slate-900/70 p-3.5">
        <div className="flex items-center justify-between text-xs text-slate-400">
          <span>Core-Hours Protected</span>
          <Cpu className="h-4 w-4 text-indigo-400" />
        </div>
        <div className="mt-2 flex items-baseline gap-2">
          <span className="text-2xl font-bold text-indigo-300">
            {kpis.core_hours_saved?.toFixed(1) ?? '0.0'}
          </span>
          <span className="text-xs text-slate-400">core-hrs</span>
        </div>
        <div className="mt-1 text-[11px] text-slate-400">
          {kpis.jobs_protected ?? 0} MPI jobs shielded from crash
        </div>
      </div>

      {/* 6. 80+ Platinum Energy Waste Avoided */}
      <div className="rounded-xl border border-slate-800/90 bg-slate-900/70 p-3.5">
        <div className="flex items-center justify-between text-xs text-slate-400">
          <span>Energy Waste Avoided</span>
          <BatteryCharging className="h-4 w-4 text-emerald-400" />
        </div>
        <div className="mt-2 flex items-baseline gap-2">
          <span className="text-2xl font-bold text-emerald-300">
            {kpis.kwh_saved?.toFixed(2) ?? '0.00'}
          </span>
          <span className="text-xs text-slate-400">kWh</span>
        </div>
        <div className="mt-1 text-[11px] text-slate-400">
          80+ Platinum PSU (~R{kpis.zar_energy_saved?.toFixed(2) ?? '0.00'} saved)
        </div>
      </div>
    </section>
  );
}
