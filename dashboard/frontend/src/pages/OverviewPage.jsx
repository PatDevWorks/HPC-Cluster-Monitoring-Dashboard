import React, { useEffect, useState } from 'react';
import {
  Activity,
  AlertTriangle,
  ArrowRight,
  BarChart2,
  Bell,
  Calendar,
  CheckCircle2,
  ChevronRight,
  Cpu,
  Download,
  ExternalLink,
  HardDrive,
  RefreshCw,
  Server,
  ShieldOff,
  Zap,
} from 'lucide-react';
import {
  Area,
  AreaChart,
  CartesianGrid,
  Line,
  LineChart,
  ResponsiveContainer,
  Tooltip,
  XAxis,
  YAxis,
} from 'recharts';
import { api } from '../api.js';
import { useTheme } from '../context/ThemeContext.jsx';

function MiniSparkline({ data, dataKey, color }) {
  if (!data || data.length < 2) return null;
  return (
    <div className="h-10 w-24 shrink-0">
      <ResponsiveContainer width="100%" height="100%">
        <LineChart data={data.slice(-18)}>
          <Line
            type="monotone"
            dataKey={dataKey}
            stroke={color}
            strokeWidth={2}
            dot={false}
            isAnimationActive={false}
            connectNulls={false}
          />
        </LineChart>
      </ResponsiveContainer>
    </div>
  );
}

export default function OverviewPage({
  snapshot,
  onNavigate,
  onInspectNode,
  onOpenQuickDrain,
  onRefresh,
  refreshing,
}) {
  const { chartTheme } = useTheme();
  const [rangeKey, setRangeKey] = useState('1h');
  const [telemetrySeries, setTelemetrySeries] = useState([]);
  const [nodeFilter, setNodeFilter] = useState('all');

  const kpis = snapshot?.kpis || {};
  const nodes = snapshot?.nodes || [];
  const clusterHistory = snapshot?.cluster_history || [];
  const episodes = snapshot?.alert_episodes || [];

  useEffect(() => {
    let cancelled = false;
    api
      .getMonitoringHistory(rangeKey, null)
      .then((res) => {
        if (!cancelled && res?.series?.length > 0) {
          setTelemetrySeries(
            res.series.map((pt) => ({
              time: pt.time,
              cpu_percent: pt.cpu,
              memory_percent: pt.memory,
            }))
          );
        }
      })
      .catch(() => {});
    return () => {
      cancelled = true;
    };
  }, [rangeKey, snapshot?.mode]);

  const chartData =
    clusterHistory.length >= 3 && rangeKey === '1h'
      ? clusterHistory
      : telemetrySeries.length > 0
      ? telemetrySeries
      : clusterHistory;

  const nodesOnline = kpis.nodes_online ?? 0;
  const nodesTotal = kpis.nodes_total ?? 4;
  const nodesOffline = kpis.nodes_offline ?? 0;
  const cpuPct = kpis.cluster_cpu_percent;
  const memPct = kpis.cluster_memory_percent;
  const clusterStatus = kpis.cluster_status || 'healthy';
  const clusterStatusLabel = kpis.cluster_status_label || 'Healthy';

  const allNodesOnline = nodesOnline === nodesTotal && nodesTotal > 0;
  const activeEpisodes = episodes.filter(
    (e) => e.status === 'active' || e.status === 'acknowledged'
  );

  const statusColor =
    clusterStatus === 'healthy'
      ? chartTheme.emerald
      : clusterStatus === 'warning'
      ? chartTheme.amber
      : chartTheme.red;

  return (
    <div className="space-y-5">
      {/* Page Subheader */}
      <div className="flex flex-wrap items-center justify-between gap-3">
        <div className="flex items-center gap-3">
          <div className="flex h-10 w-10 items-center justify-center rounded-xl bg-cyan-500/15 text-[var(--accent-cyan)]">
            <BarChart2 className="h-5 w-5" />
          </div>
          <div>
            <h2 className="text-xl font-bold tracking-tight">Overview</h2>
            <p className="text-xs spu-text-secondary">
              Latest sample:{' '}
              <span className="font-mono">
                {kpis.latest_telemetry_utc
                  ? `${kpis.latest_telemetry_utc.slice(0, 19).replace('T', ' ')}Z`
                  : 'Waiting for telemetry'}
              </span>
            </p>
          </div>
        </div>

        <div className="flex flex-wrap items-center gap-2.5">
          {/* Cluster Online Pill */}
          <span
            className={`inline-flex items-center gap-2 rounded-full border px-3.5 py-1.5 text-xs font-semibold ${
              nodesOnline > 0
                ? 'border-emerald-500/40 bg-emerald-500/10 text-emerald-400'
                : 'border-rose-500/40 bg-rose-500/10 text-rose-400'
            }`}
          >
            <span
              className={`h-2 w-2 rounded-full ${
                nodesOnline > 0 ? 'bg-emerald-400' : 'bg-rose-500'
              }`}
            />
            {nodesOnline > 0 ? 'Cluster Online' : 'Cluster Unreachable'}
          </span>

          {/* Node Filter */}
          <select
            value={nodeFilter}
            onChange={(e) => setNodeFilter(e.target.value)}
            className="spu-input py-1.5 px-2.5 text-xs font-medium"
            title="Filter Overview nodes"
          >
            <option value="all">All Nodes ({nodes.length})</option>
            {nodes.map((n) => (
              <option key={n.node_id} value={n.node_id}>
                {n.display_name || n.node_id}
              </option>
            ))}
          </select>

          {/* Time Window Selector */}
          <div className="relative inline-flex items-center">
            <Calendar className="pointer-events-none absolute left-3 h-3.5 w-3.5 spu-text-secondary" />
            <select
              value={rangeKey}
              onChange={(e) => setRangeKey(e.target.value)}
              className="spu-input pl-8 pr-7 py-1.5 text-xs font-medium"
            >
              <option value="15m">Last 15 Minutes</option>
              <option value="1h">Last 1 Hour</option>
              <option value="6h">Last 6 Hours</option>
              <option value="24h">Last 24 Hours</option>
            </select>
          </div>

          {/* Refresh Button */}
          <button
            onClick={onRefresh}
            disabled={refreshing}
            title="Refresh cluster state"
            className="spu-btn-secondary inline-flex items-center justify-center p-2"
          >
            <RefreshCw className={`h-4 w-4 ${refreshing ? 'animate-spin' : ''}`} />
          </button>
        </div>
      </div>

      {/* Top 4 KPI Cards */}
      <section className="grid grid-cols-1 gap-4 sm:grid-cols-2 xl:grid-cols-4">
        {/* 1. Nodes Online */}
        <div
          onClick={() => onNavigate('topology')}
          className="spu-card flex cursor-pointer items-center justify-between p-4 transition hover:border-[var(--accent-cyan)]"
          style={{ borderLeft: `3px solid ${allNodesOnline ? '#10b981' : '#f59e0b'}` }}
        >
          <div className="flex items-center gap-3.5">
            <div className="flex h-11 w-11 items-center justify-center rounded-xl bg-cyan-500/12 text-[var(--accent-cyan)]">
              <Server className="h-5 w-5" />
            </div>
            <div>
              <div className="text-2xl font-extrabold tracking-tight">
                {nodesOnline} / {nodesTotal}
              </div>
              <div className="text-xs font-medium spu-text-secondary">Nodes Online</div>
            </div>
          </div>
          {kpis.nodes_drained > 0 && (
            <span className="rounded-md bg-amber-500/15 px-2 py-0.5 text-[10px] font-semibold text-amber-400">
              {kpis.nodes_drained} Drained
            </span>
          )}
        </div>

        {/* 2. CPU Utilisation */}
        <div
          onClick={() => onNavigate('monitoring')}
          className="spu-card flex cursor-pointer items-center justify-between p-4 transition hover:border-[var(--accent-cyan)]"
          style={{ borderLeft: `3px solid ${chartTheme.cyan}` }}
        >
          <div className="flex items-center gap-3.5">
            <div className="flex h-11 w-11 items-center justify-center rounded-xl bg-sky-500/12 text-sky-400">
              <Cpu className="h-5 w-5" />
            </div>
            <div>
              <div className="text-2xl font-extrabold tracking-tight">
                {cpuPct != null ? `${Math.round(cpuPct)}%` : 'N/A'}
              </div>
              <div className="text-xs font-medium spu-text-secondary">CPU Utilisation</div>
            </div>
          </div>
          <MiniSparkline
            data={clusterHistory}
            dataKey="cpu_percent"
            color={chartTheme.cyan}
          />
        </div>

        {/* 3. Memory Utilisation */}
        <div
          onClick={() => onNavigate('monitoring')}
          className="spu-card flex cursor-pointer items-center justify-between p-4 transition hover:border-[var(--accent-cyan)]"
          style={{ borderLeft: `3px solid ${chartTheme.purple}` }}
        >
          <div className="flex items-center gap-3.5">
            <div className="flex h-11 w-11 items-center justify-center rounded-xl bg-purple-500/12 text-purple-400">
              <HardDrive className="h-5 w-5" />
            </div>
            <div>
              <div className="text-2xl font-extrabold tracking-tight">
                {memPct != null ? `${Math.round(memPct)}%` : 'N/A'}
              </div>
              <div className="text-xs font-medium spu-text-secondary">
                Memory Utilisation
              </div>
            </div>
          </div>
          <MiniSparkline
            data={clusterHistory}
            dataKey="memory_percent"
            color={chartTheme.purple}
          />
        </div>

        {/* 4. Active Incidents & Slurm Queue */}
        <button
          onClick={() => onNavigate(activeEpisodes.length > 0 ? 'alerts' : 'jobs')}
          className="spu-card flex items-center justify-between p-4 text-left transition hover:border-[var(--accent-cyan)]"
          style={{
            borderLeft: `3px solid ${
              (kpis.p1_count || 0) > 0
                ? chartTheme.red
                : activeEpisodes.length > 0
                ? chartTheme.amber
                : chartTheme.emerald
            }`,
          }}
        >
          <div className="flex items-center gap-3.5">
            <div
              className={`flex h-11 w-11 items-center justify-center rounded-xl ${
                (kpis.p1_count || 0) > 0
                  ? 'bg-rose-500/15 text-rose-400'
                  : activeEpisodes.length > 0
                  ? 'bg-amber-500/15 text-amber-400'
                  : 'bg-emerald-500/15 text-emerald-400'
              }`}
            >
              <AlertTriangle className="h-5 w-5" />
            </div>
            <div>
              <div className="text-2xl font-extrabold tracking-tight">
                {activeEpisodes.length}
              </div>
              <div className="text-xs font-medium spu-text-secondary">
                Active Incidents • {kpis.active_slurm_jobs ?? 0} Running Jobs
              </div>
            </div>
          </div>
          <div className="text-right font-mono text-[10px] spu-text-muted">
            <div>{kpis.pending_slurm_jobs ?? 0} Pending</div>
            <div>{kpis.failed_slurm_jobs ?? 0} Failed</div>
          </div>
        </button>
      </section>

      {/* Integration & Model Status Strip (Kept Strictly Separate) */}
      <section className="grid grid-cols-1 gap-3 sm:grid-cols-2 lg:grid-cols-5 text-xs">
        {[
          {
            label: 'Prometheus',
            status: kpis.prometheus_status || 'offline',
            sub: kpis.latest_telemetry_utc
              ? `Updated ${kpis.latest_telemetry_utc.slice(11, 19)}Z`
              : 'No collection yet',
            page: 'monitoring',
          },
          {
            label: 'V7 Isolation Forest',
            status: kpis.v7_api_status || 'not_configured',
            sub: `${kpis.nodes_with_v7_anomaly ?? 0} anomaly flag(s)`,
            page: 'predictions',
          },
          {
            label: 'LSTM V8 Forecaster',
            status: kpis.lstm_v8_api_status || 'connecting',
            sub: `${kpis.nodes_with_lstm_warning ?? 0} warning flag(s)`,
            page: 'predictions',
          },
          {
            label: 'Gemini LLM',
            status: kpis.gemini_status || 'not_configured',
            sub: 'AI Intelligence & Reports',
            page: 'intelligence',
          },
          {
            label: 'Slurm Workload',
            status: snapshot?.slurm_connected ? 'connected' : 'unavailable',
            sub: snapshot?.slurm_connected
              ? `${kpis.active_slurm_jobs ?? 0} active / ${kpis.pending_slurm_jobs ?? 0} pending${
                  (snapshot?.slurm_nodes || []).length > 0
                    ? ' • ' + snapshot.slurm_nodes.length + ' nodes'
                    : ''
                }`
              : snapshot?.slurm_error
              ? 'Slurm CLI unreachable — check SSH'
              : `${kpis.active_slurm_jobs ?? 0} active / ${kpis.pending_slurm_jobs ?? 0} pending`,
            page: 'jobs',
          },
        ].map((svc) => {
          const isOk =
            svc.status === 'connected' ||
            svc.status === 'configured' ||
            svc.status === 'ready';
          const isWarn =
            svc.status === 'simulated' ||
            svc.status === 'connecting' ||
            svc.status === 'not_configured';
          return (
            <button
              key={svc.label}
              onClick={() => onNavigate(svc.page)}
              className="spu-card flex items-center justify-between px-3.5 py-2.5 text-left transition hover:border-[var(--accent-cyan)]"
            >
              <div>
                <div className="font-bold">{svc.label}</div>
                <div className="text-[11px] spu-text-muted">{svc.sub}</div>
              </div>
              <span
                className={`rounded px-2 py-0.5 font-mono text-[10px] font-bold uppercase ${
                  isOk
                    ? 'bg-emerald-500/15 text-emerald-400'
                    : isWarn
                    ? 'bg-amber-500/15 text-amber-400'
                    : 'bg-rose-500/15 text-rose-400'
                }`}
              >
                {svc.status}
              </span>
            </button>
          );
        })}
      </section>

      {/* Main Content: A. Cluster Compute & Memory Utilisation + B. Node Status */}
      <section className="grid grid-cols-1 gap-4 lg:grid-cols-12">
        {/* A. Cluster Compute & Memory Utilisation */}
        <div className="spu-card p-5 lg:col-span-8">
          <div className="mb-4 flex items-center justify-between">
            <div className="flex items-center gap-2.5">
              <Activity className="h-4 w-4 text-[var(--accent-cyan)]" />
              <h3 className="text-base font-bold">Cluster CPU &amp; Memory Utilisation</h3>
            </div>
            <div className="flex items-center gap-3 text-xs font-medium spu-text-secondary">
              <span className="inline-flex items-center gap-1.5">
                <span className="h-2.5 w-2.5 rounded-full" style={{ backgroundColor: chartTheme.cyan }} />
                CPU %
              </span>
              <span className="inline-flex items-center gap-1.5">
                <span className="h-2.5 w-2.5 rounded-full" style={{ backgroundColor: chartTheme.purple }} />
                Memory %
              </span>
            </div>
          </div>

          <div className="grid grid-cols-1 items-center gap-4 md:grid-cols-12">
            <div className="h-60 md:col-span-9">
              <ResponsiveContainer width="100%" height="100%">
                <AreaChart data={chartData}>
                  <defs>
                    <linearGradient id="overviewCpuGrad" x1="0" y1="0" x2="0" y2="1">
                      <stop offset="5%" stopColor={chartTheme.cyan} stopOpacity={0.32} />
                      <stop offset="95%" stopColor={chartTheme.cyan} stopOpacity={0.02} />
                    </linearGradient>
                    <linearGradient id="overviewMemGrad" x1="0" y1="0" x2="0" y2="1">
                      <stop offset="5%" stopColor={chartTheme.purple} stopOpacity={0.28} />
                      <stop offset="95%" stopColor={chartTheme.purple} stopOpacity={0.02} />
                    </linearGradient>
                  </defs>
                  <CartesianGrid strokeDasharray="3 3" stroke={chartTheme.grid} />
                  <XAxis
                    dataKey="time"
                    tick={{ fill: chartTheme.axis, fontSize: 11 }}
                    axisLine={{ stroke: chartTheme.grid }}
                  />
                  <YAxis
                    domain={[0, 100]}
                    ticks={[0, 25, 50, 75, 100]}
                    tickFormatter={(v) => `${v}%`}
                    tick={{ fill: chartTheme.axis, fontSize: 11 }}
                    axisLine={{ stroke: chartTheme.grid }}
                    width={42}
                  />
                  <Tooltip
                    contentStyle={chartTheme.tooltipStyle}
                    formatter={(val, name) => [
                      val != null ? `${Number(val).toFixed(1)}%` : '--',
                      name === 'cpu_percent' ? 'CPU' : 'Memory',
                    ]}
                  />
                  <Area
                    type="monotone"
                    dataKey="cpu_percent"
                    stroke={chartTheme.cyan}
                    strokeWidth={2}
                    fill="url(#overviewCpuGrad)"
                    isAnimationActive={false}
                    connectNulls={false}
                  />
                  <Area
                    type="monotone"
                    dataKey="memory_percent"
                    stroke={chartTheme.purple}
                    strokeWidth={2}
                    fill="url(#overviewMemGrad)"
                    isAnimationActive={false}
                    connectNulls={false}
                  />
                </AreaChart>
              </ResponsiveContainer>
            </div>

            <div className="flex flex-col items-center justify-center border-t pt-4 md:col-span-3 md:border-t-0 md:border-l md:pt-0 spu-border">
              <div className="text-3xl font-extrabold tracking-tight" style={{ color: statusColor }}>
                {clusterStatusLabel}
              </div>
              <div className="mt-2 space-y-1 text-center text-[11px] font-mono spu-text-secondary">
                <div>{nodesOnline} Online • {nodesOffline} Offline</div>
                <div>{kpis.nodes_warning ?? 0} Warning • {kpis.nodes_critical ?? 0} Critical</div>
                <div>{kpis.nodes_stale ?? 0} Stale Telemetry</div>
              </div>
            </div>
          </div>
        </div>

        {/* B. Node Status */}
        <div className="spu-card flex flex-col justify-between p-5 lg:col-span-4">
          <div>
            <div className="mb-4 flex items-center justify-between gap-2">
              <div className="flex items-center gap-2">
                <Server className="h-4 w-4 text-[var(--accent-cyan)]" />
                <h3 className="text-base font-bold">Node Status</h3>
              </div>

              <span
                className={`inline-flex items-center gap-1 rounded-full border px-2.5 py-0.5 text-[11px] font-semibold ${
                  allNodesOnline && activeEpisodes.length === 0
                    ? 'border-emerald-500/35 bg-emerald-500/10 text-emerald-400'
                    : 'border-amber-500/35 bg-amber-500/10 text-amber-400'
                }`}
              >
                <CheckCircle2 className="h-3 w-3" />
                {allNodesOnline && activeEpisodes.length === 0
                  ? 'All Nodes Healthy'
                  : `${activeEpisodes.length} Active Incident(s)`}
              </span>
            </div>

            <div className="divide-y spu-border">
              {(nodeFilter === 'all' ? nodes : nodes.filter((n) => n.node_id === nodeFilter)).slice(0, 6).map((node) => {
                const st = node.health_status || (node.up === 1 ? 'healthy' : 'offline');
                const dotColor =
                  st === 'offline' || st === 'critical'
                    ? 'bg-rose-500'
                    : st === 'warning' || st === 'stale' || st === 'maintenance'
                    ? 'bg-amber-400'
                    : 'bg-emerald-400';

                return (
                  <button
                    key={node.node_id}
                    onClick={() => onInspectNode(node.node_id)}
                    className="flex w-full items-center justify-between py-3 text-left transition hover:bg-[var(--bg-hover)] rounded-lg px-2"
                  >
                    <div className="flex items-center gap-3">
                      <span className={`h-2.5 w-2.5 rounded-full ${dotColor}`} />
                      <div>
                        <div className="text-sm font-semibold">
                          {node.display_name || node.node_id}
                        </div>
                        <div className="text-[11px] spu-text-muted">
                          {node.health_classification || st} • CPU{' '}
                          {node.cpu_utilization_percent != null
                            ? `${Math.round(node.cpu_utilization_percent)}%`
                            : 'N/A'}
                        </div>
                      </div>
                    </div>

                    <div className="flex items-center gap-2">
                      <span className="font-mono text-xs spu-text-secondary">
                        {node.ip}
                      </span>
                      <ChevronRight className="h-4 w-4 spu-text-muted" />
                    </div>
                  </button>
                );
              })}
            </div>
          </div>

          {nodes.length > 6 && (
            <button
              onClick={() => onNavigate('monitoring')}
              className="mt-3 text-xs font-semibold text-[var(--accent-cyan)] hover:underline"
            >
              View all {nodes.length} nodes in Live Monitoring →
            </button>
          )}
        </div>
      </section>

      {/* Bottom Row: C. Recent Alerts + D. Quick Actions */}
      <section className="grid grid-cols-1 gap-4 lg:grid-cols-12">
        {/* C. Recent Alerts */}
        <div className="spu-card flex flex-col justify-between p-5 lg:col-span-6">
          <div className="flex items-center justify-between">
            <div className="flex items-center gap-2">
              <Bell className="h-4 w-4 text-rose-400" />
              <h3 className="text-base font-bold">Recent Alerts</h3>
            </div>
            <button
              onClick={() => onNavigate('alerts')}
              className="spu-btn-secondary inline-flex items-center gap-1.5 text-xs"
            >
              View All <ArrowRight className="h-3.5 w-3.5" />
            </button>
          </div>

          {activeEpisodes.length === 0 ? (
            <div className="my-5 flex items-center gap-4 py-2">
              <div className="flex h-12 w-12 shrink-0 items-center justify-center rounded-full bg-emerald-500/15 text-emerald-400">
                <CheckCircle2 className="h-6 w-6" />
              </div>
              <div>
                <div className="text-sm font-bold">No critical alerts</div>
                <div className="text-xs spu-text-secondary">
                  Cluster is operating normally.
                </div>
              </div>
            </div>
          ) : (
            <div className="mt-3 space-y-2">
              {activeEpisodes.slice(0, 3).map((ep) => (
                <div
                  key={ep.id}
                  onClick={() => onNavigate('alerts')}
                  className="flex cursor-pointer items-center justify-between rounded-lg p-2.5 text-xs transition spu-subcard hover:border-[var(--accent-cyan)]"
                >
                  <div className="flex items-center gap-2.5 truncate">
                    <span
                      className={`rounded px-1.5 py-0.5 text-[10px] font-bold uppercase ${
                        ep.priority === 'P1'
                          ? 'bg-rose-500 text-white'
                          : ep.priority === 'P2'
                          ? 'bg-amber-500 text-slate-950'
                          : 'bg-sky-500/25 text-sky-400'
                      }`}
                    >
                      {ep.severity || ep.priority}
                    </span>
                    <span className="truncate font-semibold">{ep.title}</span>
                  </div>
                  <span className="ml-2 shrink-0 font-mono text-[11px] spu-text-muted">
                    {ep.last_seen_utc?.slice(11, 19)}Z
                  </span>
                </div>
              ))}
            </div>
          )}
        </div>

        {/* D. Quick Actions */}
        <div className="spu-card p-5 lg:col-span-6">
          <div className="mb-4 flex items-center gap-2">
            <Zap className="h-4 w-4 text-[var(--accent-cyan)]" />
            <h3 className="text-base font-bold">Quick Actions</h3>
          </div>

          <div className="grid grid-cols-2 gap-3 sm:grid-cols-4">
            <a
              href={api.getClusterDiagnosticBundleUrl()}
              className="spu-subcard flex flex-col items-center justify-center gap-2 p-3.5 text-center transition hover:border-[var(--accent-cyan)] hover:bg-[var(--bg-hover)]"
            >
              <Download className="h-5 w-5 text-[var(--accent-cyan)]" />
              <span className="text-xs font-semibold leading-snug">Download Logs</span>
            </a>

            <button
              onClick={() => onNavigate('reports')}
              className="spu-subcard flex flex-col items-center justify-center gap-2 p-3.5 text-center transition hover:border-[var(--accent-cyan)] hover:bg-[var(--bg-hover)]"
            >
              <ExternalLink className="h-5 w-5 text-[var(--accent-cyan)]" />
              <span className="text-xs font-semibold leading-snug">View Reports</span>
            </button>

            <button
              onClick={onOpenQuickDrain}
              className="spu-subcard flex flex-col items-center justify-center gap-2 p-3.5 text-center transition hover:border-amber-400 hover:bg-[var(--bg-hover)]"
            >
              <ShieldOff className="h-5 w-5 text-amber-400" />
              <span className="text-xs font-semibold leading-snug">
                Drain Node (Slurm)
              </span>
            </button>

            <a
              href={snapshot?.grafana_url || 'http://localhost:3000'}
              target="_blank"
              rel="noopener noreferrer"
              className="spu-subcard flex flex-col items-center justify-center gap-2 p-3.5 text-center transition hover:border-[var(--accent-cyan)] hover:bg-[var(--bg-hover)]"
            >
              <Activity className="h-5 w-5 text-[var(--accent-cyan)]" />
              <span className="text-xs font-semibold leading-snug">Open Grafana</span>
            </a>
          </div>
        </div>
      </section>
    </div>
  );
}
