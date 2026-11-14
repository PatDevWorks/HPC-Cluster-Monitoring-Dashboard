import React, { useEffect, useMemo, useState } from 'react';
import {
  Activity,
  Clock,
  Cpu,
  Gauge,
  HardDrive,
  Layers,
  Network,
  RefreshCw,
  Download, CheckCircle2,
} from 'lucide-react';
import {
  Area,
  AreaChart,
  CartesianGrid,
  Legend,
  Line,
  LineChart,
  ResponsiveContainer,
  Tooltip,
  XAxis,
  YAxis,
} from 'recharts';
import { api } from '../api.js';
import { useTheme } from '../context/ThemeContext.jsx';

const TIME_RANGES = [
  { id: '5m', label: '5m' },
  { id: '15m', label: '15m' },
  { id: '1h', label: '1h' },
  { id: '6h', label: '6h' },
  { id: '12h', label: '12h' },
  { id: '24h', label: '24h' },
];

function fmtVal(val, unit = '', digits = 1) {
  if (val === null || val === undefined || Number.isNaN(Number(val))) {
    return 'Unavailable';
  }
  return `${Number(val).toFixed(digits)}${unit}`;
}

function fmtBytesPerSec(bps) {
  if (bps === null || bps === undefined) return 'Unavailable';
  const mb = Number(bps) / (1024 * 1024);
  if (mb >= 1) return `${mb.toFixed(2)} MB/s`;
  return `${(Number(bps) / 1024).toFixed(1)} KB/s`;
}

function fmtUptime(sec) {
  if (sec === null || sec === undefined) return 'Unavailable';
  const d = Math.floor(sec / 86400);
  const h = Math.floor((sec % 86400) / 3600);
  const m = Math.floor((sec % 3600) / 60);
  return d > 0 ? `${d}d ${h}h ${m}m` : `${h}h ${m}m`;
}

export default function LiveMonitoringPage({
  snapshot,
  selectedNodeId,
  onSelectNode,
}) {
  const { chartTheme } = useTheme();
  const [rangeKey, setRangeKey] = useState('1h');
  const [rangeData, setRangeData] = useState([]);
  const [rangeSource, setRangeSource] = useState('in_memory_buffer');
  const [loadingRange, setLoadingRange] = useState(false);

  const nodes = snapshot?.nodes || [];
  const activeNode = useMemo(
    () => nodes.find((n) => n.node_id === selectedNodeId) || nodes[0] || null,
    [nodes, selectedNodeId]
  );

  const fetchRange = async () => {
    if (!activeNode) return;
    setLoadingRange(true);
    try {
      const res = await api.getMonitoringHistory(rangeKey, activeNode.node_id);
      setRangeData(res.series || []);
      setRangeSource(res.source || 'recorded_telemetry_db');
    } catch {
      setRangeData([]);
    } finally {
      setLoadingRange(false);
    }
  };

  useEffect(() => {
    fetchRange();
  }, [activeNode?.node_id, rangeKey, snapshot?.mode]);

  // Merge live WebSocket ring buffer for short ranges so charts update seamlessly without page refresh
  const liveRing = snapshot?.history?.[activeNode?.node_id] || [];
  const chartSeries =
    (rangeKey === '5m' || rangeKey === '15m') && rangeSource !== 'prometheus_query_range' && liveRing.length > 0
      ? liveRing
      : rangeData.length > 0
      ? rangeData
      : liveRing;

  if (!activeNode) {
    return <div className="spu-card p-6 text-sm spu-text-secondary">Waiting for node telemetry...</div>;
  }

  return (
    <div className="space-y-5">
      {/* Header + Time Range Selector */}
      <div className="flex flex-wrap items-center justify-between gap-3">
        <div className="flex items-center gap-3">
          <div className="flex h-10 w-10 items-center justify-center rounded-xl bg-cyan-500/15 text-[var(--accent-cyan)]">
            <Activity className="h-5 w-5" />
          </div>
          <div>
            <h2 className="text-xl font-bold tracking-tight">Live Monitoring</h2>
           
           
          </div>
        </div>

        {/* Time Range Buttons (5m, 15m, 1h, 6h, 12h, 24h) */}
        <div className="flex items-center gap-2">
          <div className="spu-subcard inline-flex p-1">
            {TIME_RANGES.map((tr) => (
              <button
                key={tr.id}
                onClick={() => setRangeKey(tr.id)}
                className={`rounded-md px-2.5 py-1 text-xs font-semibold transition ${
                  rangeKey === tr.id
                    ? 'bg-[var(--accent-cyan-strong)] text-white'
                    : 'spu-text-secondary hover:text-[var(--text-primary)]'
                }`}
              >
                {tr.label}
              </button>
            ))}
          </div>
          <button
            onClick={fetchRange}
            disabled={loadingRange}
            title="Reload range query"
            className="spu-btn-secondary p-2"
          >
            <RefreshCw className={`h-3.5 w-3.5 ${loadingRange ? 'animate-spin' : ''}`} />
          </button>
          <a
            href={api.getMonitoringExportUrl(rangeKey, activeNode?.node_id)}
            className="spu-btn-secondary inline-flex items-center gap-1.5 text-xs"
            title="Export telemetry CSV for current window"
          >
            <Download className="h-3.5 w-3.5" />
            Export CSV
          </a>
        </div>
      </div>

      {/* Node Selector Strip */}
      <div className="flex flex-wrap gap-2">
        {nodes.map((n) => {
          const selected = n.node_id === activeNode.node_id;
          return (
            <button
              key={n.node_id}
              onClick={() => onSelectNode(n.node_id)}
              className={`inline-flex items-center gap-2 rounded-xl border px-3.5 py-2 text-xs font-semibold transition ${
                selected
                  ? 'border-[var(--accent-cyan)] bg-cyan-500/12 text-[var(--accent-cyan)]'
                  : 'spu-card spu-text-secondary hover:text-[var(--text-primary)]'
              }`}
            >
              <span
                className={`h-2 w-2 rounded-full ${
                  n.up === 1 ? 'bg-emerald-400' : 'bg-rose-500'
                }`}
              />
              <span>{n.display_name || n.node_id}</span>
              <span className="font-mono text-[10px] opacity-75">{n.ip}</span>
            </button>
          );
        })}
      </div>

      {/* Instant Metric Telemetry Cards (Explicitly shows Unavailable when null) */}
      <section className="grid grid-cols-2 gap-3 sm:grid-cols-3 xl:grid-cols-6">
        {[
          {
            label: 'CPU Utilisation',
            value: fmtVal(activeNode.cpu_utilization_percent, '%'),
            sub: `I/O Wait: ${fmtVal(activeNode.cpu_iowait_percent, '%')}`,
            icon: Cpu,
          },
          {
            label: 'Memory & Swap',
            value: fmtVal(activeNode.memory_used_percent, '%'),
            sub: `Swap: ${fmtVal(activeNode.swap_used_percent, '%')}`,
            icon: HardDrive,
          },
          {
            label: 'Load Averages',
            value:
              activeNode.load1 != null
                ? `${activeNode.load1} / ${activeNode.load5 ?? '-'} / ${activeNode.load15 ?? '-'}`
                : 'Unavailable',
            sub: `Normalized: ${fmtVal(activeNode.normalized_load1, 'x', 2)}`,
            icon: Gauge,
          },
          {
            label: 'Filesystem Usage',
            value: `/: ${fmtVal(activeNode.root_used_percent, '%')}`,
            sub: `/scratch: ${fmtVal(activeNode.scratch_used_percent, '%')}`,
            icon: Layers,
          },
          {
            label: 'Network RX / TX',
            value: fmtBytesPerSec(activeNode.network_receive_bytes_per_second),
            sub: `TX: ${fmtBytesPerSec(activeNode.network_transmit_bytes_per_second)} • Err: ${fmtVal(
              activeNode.network_errors_per_second,
              '/s',
              3
            )}`,
            icon: Network,
          },
          {
            label: 'Uptime & Processes',
            value: fmtUptime(activeNode.uptime_seconds),
            sub: `Run: ${fmtVal(activeNode.procs_running, '', 0)} • Blk: ${fmtVal(
              activeNode.procs_blocked,
              '',
              0
            )}`,
            icon: Clock,
          },
        ].map((card) => {
          const Icon = card.icon;
          const isUnavail = String(card.value).includes('Unavailable');
          return (
            <div key={card.label} className="spu-card p-3.5">
              <div className="flex items-center justify-between text-[11px] spu-text-secondary">
                <span>{card.label}</span>
                <Icon className="h-3.5 w-3.5 text-[var(--accent-cyan)]" />
              </div>
              <div
                className={`mt-1.5 font-mono text-base font-bold ${
                  isUnavail ? 'spu-text-muted text-xs' : ''
                }`}
              >
                {card.value}
              </div>
              <div className="mt-1 text-[10.5px] spu-text-muted">{card.sub}</div>
            </div>
          );
        })}
      </section>

      {/* Telemetry Freshness, Collector Health & Linux Kernel PSI */}
      <section className="spu-card p-4 space-y-3">
        <div className="flex flex-wrap items-center justify-between gap-3">
          <div>
            <h3 className="text-xs font-bold uppercase tracking-wider">
              Linux Kernel Pressure Stalls (PSI), Packet Drops &amp; Collector Health
            </h3>
            <p className="text-[11px] spu-text-secondary">
               <code className="font-mono"></code> • Last update:{' '}
              <span className="font-mono">
                {activeNode.last_telemetry_utc
                  ? `${activeNode.last_telemetry_utc.slice(0, 19).replace('T', ' ')}Z`
                  : 'Unavailable'}
              </span>{' '}
              {activeNode.telemetry_age_seconds != null && `(${Math.round(activeNode.telemetry_age_seconds)}s ago)`}
            </p>
          </div>

          <div className="grid grid-cols-2 gap-3 sm:grid-cols-5 text-xs">
            <div className="spu-subcard px-3 py-2">
              <span className="spu-text-muted block text-[10px]">CPU Pressure</span>
              <strong className="font-mono">{fmtVal(activeNode.psi_cpu_percent, '%', 2)}</strong>
            </div>
            <div className="spu-subcard px-3 py-2">
              <span className="spu-text-muted block text-[10px]">Memory Pressure</span>
              <strong className="font-mono">{fmtVal(activeNode.psi_memory_percent, '%', 2)}</strong>
            </div>
            <div className="spu-subcard px-3 py-2">
              <span className="spu-text-muted block text-[10px]">I/O Pressure (PSI)</span>
              <strong className="font-mono">{fmtVal(activeNode.psi_io_percent, '%', 2)}</strong>
            </div>
            <div className="spu-subcard px-3 py-2">
              <span className="spu-text-muted block text-[10px]">Net Packet Drops</span>
              <strong className="font-mono">{fmtVal(activeNode.network_drop_per_second, '/s', 3)}</strong>
            </div>
            <div className="spu-subcard px-3 py-2">
              <span className="spu-text-muted block text-[10px]">Scrape Collector</span>
              <strong className={`font-mono ${activeNode.up === 1 ? 'text-emerald-400' : 'text-rose-400'}`}>
                {activeNode.up === 1 ? 'UP' : 'SCRAPE DOWN'}
              </strong>
            </div>
          </div>
        </div>
        
      </section>

      {/* 4 Synchronized Time-Series Charts */}
      <section className="grid grid-cols-1 gap-4 lg:grid-cols-2">
        {/* 1. CPU & I/O Wait */}
        <div className="spu-card p-4">
          <div className="mb-2 flex items-center justify-between">
            <h3 className="text-xs font-bold">CPU Utilisation &amp; I/O Wait (%)</h3>
            <span className="text-[11px] spu-text-muted">{rangeKey} window</span>
          </div>
          <div className="h-56">
            <ResponsiveContainer width="100%" height="100%">
              <AreaChart data={chartSeries} syncId="liveMonSync">
                <CartesianGrid strokeDasharray="3 3" stroke={chartTheme.grid} />
                <XAxis dataKey="time" tick={{ fill: chartTheme.axis, fontSize: 10 }} />
                <YAxis domain={[0, 100]} tick={{ fill: chartTheme.axis, fontSize: 10 }} width={34} />
                <Tooltip contentStyle={chartTheme.tooltipStyle} />
                <Legend wrapperStyle={{ fontSize: '11px' }} />
                <Area
                  type="monotone"
                  dataKey="cpu"
                  name="CPU %"
                  stroke={chartTheme.cyan}
                  fill={chartTheme.cyan}
                  fillOpacity={0.14}
                  strokeWidth={2}
                  isAnimationActive={false}
                  connectNulls={false}
                />
                <Area
                  type="monotone"
                  dataKey="iowait"
                  name="I/O Wait %"
                  stroke={chartTheme.amber}
                  fill={chartTheme.amber}
                  fillOpacity={0.12}
                  strokeWidth={2}
                  isAnimationActive={false}
                  connectNulls={false}
                />
              </AreaChart>
            </ResponsiveContainer>
          </div>
        </div>

        {/* 2. Memory, Swap & /scratch */}
        <div className="spu-card p-4">
          <div className="mb-2 flex items-center justify-between">
            <h3 className="text-xs font-bold">Memory, Swap &amp; Filesystem (%)</h3>
            <span className="text-[11px] spu-text-muted">Capacity tracking</span>
          </div>
          <div className="h-56">
            <ResponsiveContainer width="100%" height="100%">
              <LineChart data={chartSeries} syncId="liveMonSync">
                <CartesianGrid strokeDasharray="3 3" stroke={chartTheme.grid} />
                <XAxis dataKey="time" tick={{ fill: chartTheme.axis, fontSize: 10 }} />
                <YAxis domain={[0, 100]} tick={{ fill: chartTheme.axis, fontSize: 10 }} width={34} />
                <Tooltip contentStyle={chartTheme.tooltipStyle} />
                <Legend wrapperStyle={{ fontSize: '11px' }} />
                <Line
                  type="monotone"
                  dataKey="memory"
                  name="Memory %"
                  stroke={chartTheme.purple}
                  strokeWidth={2}
                  dot={false}
                  isAnimationActive={false}
                  connectNulls={false}
                />
                <Line
                  type="monotone"
                  dataKey="swap"
                  name="Swap %"
                  stroke={chartTheme.amber}
                  strokeWidth={1.8}
                  dot={false}
                  isAnimationActive={false}
                  connectNulls={false}
                />
                <Line
                  type="monotone"
                  dataKey="scratch"
                  name="Filesystem /scratch %"
                  stroke={chartTheme.emerald}
                  strokeWidth={1.8}
                  dot={false}
                  isAnimationActive={false}
                  connectNulls={false}
                />
              </LineChart>
            </ResponsiveContainer>
          </div>
        </div>

        {/* 3. Disk I/O Read / Write */}
        <div className="spu-card p-4">
          <div className="mb-2 flex items-center justify-between">
            <h3 className="text-xs font-bold">Disk Read / Write Throughput (MB/s)</h3>
            <span className="text-[11px] spu-text-muted">
              Disk Active: {fmtVal(activeNode.disk_io_utilization_percent, '%')}
            </span>
          </div>
          <div className="h-56">
            <ResponsiveContainer width="100%" height="100%">
              <LineChart data={chartSeries} syncId="liveMonSync">
                <CartesianGrid strokeDasharray="3 3" stroke={chartTheme.grid} />
                <XAxis dataKey="time" tick={{ fill: chartTheme.axis, fontSize: 10 }} />
                <YAxis tick={{ fill: chartTheme.axis, fontSize: 10 }} width={38} />
                <Tooltip contentStyle={chartTheme.tooltipStyle} />
                <Legend wrapperStyle={{ fontSize: '11px' }} />
                <Line
                  type="monotone"
                  dataKey="disk_read_mb"
                  name="Disk Read MB/s"
                  stroke={chartTheme.blue}
                  strokeWidth={2}
                  dot={false}
                  isAnimationActive={false}
                  connectNulls={false}
                />
                <Line
                  type="monotone"
                  dataKey="disk_write_mb"
                  name="Disk Write MB/s"
                  stroke={chartTheme.amber}
                  strokeWidth={2}
                  dot={false}
                  isAnimationActive={false}
                  connectNulls={false}
                />
              </LineChart>
            </ResponsiveContainer>
          </div>
        </div>

        {/* 4. Network Throughput & Load */}
        <div className="spu-card p-4">
          <div className="mb-2 flex items-center justify-between">
            <h3 className="text-xs font-bold">10GbE Network Throughput (MB/s) &amp; Load1</h3>
            <span className="text-[11px] spu-text-muted">
              Errors: {fmtVal(activeNode.network_errors_per_second, ' err/s', 3)}
            </span>
          </div>
          <div className="h-56">
            <ResponsiveContainer width="100%" height="100%">
              <LineChart data={chartSeries} syncId="liveMonSync">
                <CartesianGrid strokeDasharray="3 3" stroke={chartTheme.grid} />
                <XAxis dataKey="time" tick={{ fill: chartTheme.axis, fontSize: 10 }} />
                <YAxis tick={{ fill: chartTheme.axis, fontSize: 10 }} width={38} />
                <Tooltip contentStyle={chartTheme.tooltipStyle} />
                <Legend wrapperStyle={{ fontSize: '11px' }} />
                <Line
                  type="monotone"
                  dataKey="net_rx_mb"
                  name="Net RX MB/s"
                  stroke={chartTheme.emerald}
                  strokeWidth={2}
                  dot={false}
                  isAnimationActive={false}
                  connectNulls={false}
                />
                <Line
                  type="monotone"
                  dataKey="net_tx_mb"
                  name="Net TX MB/s"
                  stroke={chartTheme.cyan}
                  strokeWidth={1.8}
                  dot={false}
                  isAnimationActive={false}
                  connectNulls={false}
                />
                <Line
                  type="monotone"
                  dataKey="load1"
                  name="System Load (1m)"
                  stroke={chartTheme.red}
                  strokeWidth={1.6}
                  dot={false}
                  isAnimationActive={false}
                  connectNulls={false}
                />
              </LineChart>
            </ResponsiveContainer>
          </div>
        </div>
      </section>

      {/* Multi-Node Side-by-Side Comparison */}
      <section className="spu-card p-4">
        <div className="mb-3 flex flex-wrap items-center justify-between gap-2">
          <div>
            <h3 className="text-xs font-bold uppercase tracking-wider">
              Cluster Node Metric Comparison
            </h3>
            
          </div>
          <a
            href={api.getMonitoringExportUrl(rangeKey, null)}
            className="text-xs font-semibold text-[var(--accent-cyan)] hover:underline"
          >
            Export All Nodes CSV ({rangeKey})
          </a>
        </div>
        <div className="overflow-x-auto">
          <table className="w-full text-left text-xs font-mono">
            <thead>
              <tr className="border-b spu-border text-[10px] uppercase spu-text-muted">
                <th className="py-2 pr-3 font-sans">Node</th>
                <th className="py-2 px-2">Scrape</th>
                <th className="py-2 px-2">Health</th>
                <th className="py-2 px-2">CPU %</th>
                <th className="py-2 px-2">I/O Wait %</th>
                <th className="py-2 px-2">Mem %</th>
                <th className="py-2 px-2">Load1</th>
                <th className="py-2 px-2">Net Err/s</th>
                <th className="py-2 px-2">V7</th>
                <th className="py-2 pl-2">LSTM V8</th>
              </tr>
            </thead>
            <tbody className="divide-y spu-border">
              {nodes.map((n) => {
                const isSel = n.node_id === activeNode.node_id;
                return (
                  <tr
                    key={n.node_id}
                    onClick={() => onSelectNode(n.node_id)}
                    className={`cursor-pointer transition hover:bg-[var(--bg-hover)] ${
                      isSel ? 'bg-cyan-500/8' : ''
                    }`}
                  >
                    <td className="py-2 pr-3 font-sans font-semibold">{n.display_name || n.node_id}</td>
                    <td className={`py-2 px-2 ${n.up === 1 ? 'text-emerald-400' : 'text-rose-400'}`}>
                      {n.up === 1 ? 'OK' : 'DOWN'}
                    </td>
                    <td className="py-2 px-2">{n.health_status || (n.up === 1 ? 'healthy' : 'offline')}</td>
                    <td className="py-2 px-2">{fmtVal(n.cpu_utilization_percent, '%', 1)}</td>
                    <td className="py-2 px-2">{fmtVal(n.cpu_iowait_percent, '%', 1)}</td>
                    <td className="py-2 px-2">{fmtVal(n.memory_used_percent, '%', 1)}</td>
                    <td className="py-2 px-2">{n.load1 ?? '--'}</td>
                    <td className="py-2 px-2">{fmtVal(n.network_errors_per_second, '', 3)}</td>
                    <td className="py-2 px-2">
                      {n.v7_detection?.anomaly_score != null
                        ? `${n.v7_detection.anomaly_score.toFixed(3)} (${n.v7_detection.is_anomaly ? 'ANOM' : 'OK'})`
                        : '--'}
                    </td>
                    <td className="py-2 pl-2">
                      {n.lstm_v8_status?.latest_warning?.status || '--'}
                    </td>
                  </tr>
                );
              })}
            </tbody>
          </table>
        </div>
      </section>
    </div>
  );
}
