import React from 'react';
import {
  Area,
  CartesianGrid,
  ComposedChart,
  Legend,
  Line,
  LineChart,
  ReferenceLine,
  ResponsiveContainer,
  Tooltip,
  XAxis,
  YAxis,
} from 'recharts';

const TOOLTIP_STYLE = {
  backgroundColor: '#0f172a',
  border: '1px solid #334155',
  borderRadius: '10px',
  fontSize: '11px',
  color: '#f1f5f9',
};

export default function TelemetryChartsPanel({ selectedNode, series, isSynthetic }) {
  if (!selectedNode) return null;

  const data = series || [];

  return (
    <section className="rounded-2xl border border-slate-800/90 bg-slate-900/60 p-4">
      <div className="mb-3 flex flex-wrap items-center justify-between gap-2 border-b border-slate-800/80 pb-3">
        <div>
          <div className="flex items-center gap-2">
            <h2 className="text-sm font-bold text-white">
              Synchronized Node Telemetry &amp; AI Risk Overlay —{' '}
              <span className="font-mono text-cyan-300">{selectedNode.node_id}</span>
            </h2>
            {isSynthetic && (
              <span className="rounded bg-amber-500/20 px-1.5 py-0.5 text-[10px] font-semibold uppercase text-amber-300">
                Synthetic Telemetry
              </span>
            )}
          </div>
          <p className="text-xs text-slate-400">
            Instance {selectedNode.instance} • Persistence:{' '}
            <span className="font-mono text-slate-200">
              {selectedNode.persistence_progress || '0/2'}
            </span>{' '}
            • Diagnosis:{' '}
            <span className="font-semibold text-cyan-300">{selectedNode.fault_label}</span>
          </p>
        </div>

        <div className="flex items-center gap-3 text-xs">
          <div className="rounded-lg bg-slate-950 px-2.5 py-1 ring-1 ring-slate-800">
            <span className="text-slate-400">1h Prob: </span>
            <strong className="font-mono text-rose-300">
              {((selectedNode.failure_prob_1h || 0) * 100).toFixed(1)}%
            </strong>
          </div>
          <div className="rounded-lg bg-slate-950 px-2.5 py-1 ring-1 ring-slate-800">
            <span className="text-slate-400">6h Prob: </span>
            <strong className="font-mono text-amber-300">
              {((selectedNode.failure_prob_6h || 0) * 100).toFixed(1)}%
            </strong>
          </div>
          <div className="rounded-lg bg-slate-950 px-2.5 py-1 ring-1 ring-slate-800">
            <span className="text-slate-400">Anomaly: </span>
            <strong className="font-mono text-cyan-300">
              {((selectedNode.anomaly_score || 0) * 100).toFixed(1)}%
            </strong>
          </div>
        </div>
      </div>

      <div className="grid grid-cols-1 gap-4 lg:grid-cols-3">
        {/* Chart 1: AI Failure Probability + Unsupervised Anomaly + Straggler */}
        <div className="rounded-xl border border-slate-800/80 bg-slate-950/60 p-3">
          <div className="mb-1.5 flex items-center justify-between">
            <span className="text-xs font-semibold text-slate-200">
              1. AI Failure Risk (1h) &amp; Anomaly Score (%)
            </span>
            <span className="text-[10px] text-slate-400">Cutoffs: 18% Warn / 40% Crit</span>
          </div>
          <div className="h-52">
            <ResponsiveContainer width="100%" height="100%">
              <ComposedChart data={data} syncId="hpcNodeSync">
                <defs>
                  <linearGradient id="failGrad" x1="0" y1="0" x2="0" y2="1">
                    <stop offset="5%" stopColor="#f43f5e" stopOpacity={0.4} />
                    <stop offset="95%" stopColor="#f43f5e" stopOpacity={0.0} />
                  </linearGradient>
                  <linearGradient id="anomGrad" x1="0" y1="0" x2="0" y2="1">
                    <stop offset="5%" stopColor="#22d3ee" stopOpacity={0.3} />
                    <stop offset="95%" stopColor="#22d3ee" stopOpacity={0.0} />
                  </linearGradient>
                </defs>
                <CartesianGrid strokeDasharray="3 3" stroke="#1e293b" />
                <XAxis dataKey="time" tick={{ fill: '#94a3b8', fontSize: 10 }} />
                <YAxis domain={[0, 100]} tick={{ fill: '#94a3b8', fontSize: 10 }} width={32} />
                <Tooltip contentStyle={TOOLTIP_STYLE} />
                <Legend wrapperStyle={{ fontSize: '11px' }} />
                <ReferenceLine y={40} stroke="#f43f5e" strokeDasharray="4 4" />
                <ReferenceLine y={18} stroke="#f59e0b" strokeDasharray="4 4" />
                <Area
                  type="monotone"
                  dataKey="failure_prob_pct"
                  name="1h Failure Prob %"
                  stroke="#f43f5e"
                  strokeWidth={2}
                  fill="url(#failGrad)"
                  isAnimationActive={false}
                />
                <Area
                  type="monotone"
                  dataKey="anomaly_score_pct"
                  name="Anomaly Score %"
                  stroke="#22d3ee"
                  strokeWidth={1.8}
                  fill="url(#anomGrad)"
                  isAnimationActive={false}
                />
                <Line
                  type="monotone"
                  dataKey="straggler_pct"
                  name="MPI Straggler %"
                  stroke="#a855f7"
                  strokeWidth={1.5}
                  dot={false}
                  isAnimationActive={false}
                />
              </ComposedChart>
            </ResponsiveContainer>
          </div>
        </div>

        {/* Chart 2: CPU, I/O Wait & Temperature */}
        <div className="rounded-xl border border-slate-800/80 bg-slate-950/60 p-3">
          <div className="mb-1.5 flex items-center justify-between">
            <span className="text-xs font-semibold text-slate-200">
              2. CPU Utilization, I/O Wait &amp; Package Temp
            </span>
            <span className="text-[10px] text-slate-400">Gaps preserved when up=0</span>
          </div>
          <div className="h-52">
            <ResponsiveContainer width="100%" height="100%">
              <LineChart data={data} syncId="hpcNodeSync">
                <CartesianGrid strokeDasharray="3 3" stroke="#1e293b" />
                <XAxis dataKey="time" tick={{ fill: '#94a3b8', fontSize: 10 }} />
                <YAxis domain={[0, 105]} tick={{ fill: '#94a3b8', fontSize: 10 }} width={32} />
                <Tooltip contentStyle={TOOLTIP_STYLE} />
                <Legend wrapperStyle={{ fontSize: '11px' }} />
                <Line
                  type="monotone"
                  dataKey="cpu"
                  name="CPU %"
                  stroke="#10b981"
                  strokeWidth={2}
                  dot={false}
                  connectNulls={false}
                  isAnimationActive={false}
                />
                <Line
                  type="monotone"
                  dataKey="iowait"
                  name="I/O Wait %"
                  stroke="#f59e0b"
                  strokeWidth={2}
                  dot={false}
                  connectNulls={false}
                  isAnimationActive={false}
                />
                <Line
                  type="monotone"
                  dataKey="temp"
                  name="Temp (°C)"
                  stroke="#fb7185"
                  strokeWidth={1.8}
                  dot={false}
                  connectNulls={false}
                  isAnimationActive={false}
                />
              </LineChart>
            </ResponsiveContainer>
          </div>
        </div>

        {/* Chart 3: Memory %, Scratch %, Disk & 10GbE Network */}
        <div className="rounded-xl border border-slate-800/80 bg-slate-950/60 p-3">
          <div className="mb-1.5 flex items-center justify-between">
            <span className="text-xs font-semibold text-slate-200">
              3. Memory %, /scratch Pool &amp; I/O Throughput
            </span>
            <span className="text-[10px] text-slate-400">90% /scratch limit</span>
          </div>
          <div className="h-52">
            <ResponsiveContainer width="100%" height="100%">
              <LineChart data={data} syncId="hpcNodeSync">
                <CartesianGrid strokeDasharray="3 3" stroke="#1e293b" />
                <XAxis dataKey="time" tick={{ fill: '#94a3b8', fontSize: 10 }} />
                <YAxis tick={{ fill: '#94a3b8', fontSize: 10 }} width={36} />
                <Tooltip contentStyle={TOOLTIP_STYLE} />
                <Legend wrapperStyle={{ fontSize: '11px' }} />
                <ReferenceLine y={90} stroke="#ef4444" strokeDasharray="3 3" />
                <Line
                  type="monotone"
                  dataKey="memory"
                  name="Memory %"
                  stroke="#38bdf8"
                  strokeWidth={2}
                  dot={false}
                  connectNulls={false}
                  isAnimationActive={false}
                />
                <Line
                  type="monotone"
                  dataKey="scratch"
                  name="/scratch %"
                  stroke="#c084fc"
                  strokeWidth={1.8}
                  dot={false}
                  connectNulls={false}
                  isAnimationActive={false}
                />
                <Line
                  type="monotone"
                  dataKey="disk_write_mb"
                  name="Disk Write MB/s"
                  stroke="#facc15"
                  strokeWidth={1.5}
                  dot={false}
                  connectNulls={false}
                  isAnimationActive={false}
                />
              </LineChart>
            </ResponsiveContainer>
          </div>
        </div>
      </div>
    </section>
  );
}
