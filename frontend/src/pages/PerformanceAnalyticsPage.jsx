import React, { useEffect, useState } from 'react';
import {
  AlertCircle,
  BarChart3,
  CheckCircle2,
  Download,
  FileText,
} from 'lucide-react';
import {
  Area,
  AreaChart,
  Bar,
  BarChart,
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

const RANGE_MINUTES_MAP = {
  '1h': 60,
  '6h': 360,
  '12h': 720,
  '24h': 1440,
};

export default function PerformanceAnalyticsPage({ snapshot }) {
  const { chartTheme } = useTheme();
  const [rangeKey, setRangeKey] = useState('1h');
  const [historySeries, setHistorySeries] = useState([]);
  const [analytics, setAnalytics] = useState(null);

  useEffect(() => {
    let cancelled = false;
    Promise.all([
      api.getMonitoringHistory(rangeKey, null),
      api.getAnalyticsSummary(rangeKey),
    ])
      .then(([histRes, sumRes]) => {
        if (cancelled) return;
        setHistorySeries(histRes.series || []);
        setAnalytics(sumRes);
      })
      .catch(() => {});
    return () => {
      cancelled = true;
    };
  }, [rangeKey, snapshot?.mode, snapshot?.timestamp_utc]);

  const rangeMins = RANGE_MINUTES_MAP[rangeKey] || 60;
  const comparisons = analytics?.node_comparisons || [];
  const bottlenecks = analytics?.bottlenecks || [];
  const availability = analytics?.overall_availability_pct ?? 100;

  return (
    <div className="space-y-5">
      {/* Header + CSV / PDF Exports */}
      <div className="flex flex-wrap items-center justify-between gap-3">
        <div className="flex items-center gap-3">
          <div className="flex h-10 w-10 items-center justify-center rounded-xl bg-cyan-500/15 text-[var(--accent-cyan)]">
            <BarChart3 className="h-5 w-5" />
          </div>
          <div>
            <h2 className="text-xl font-bold tracking-tight">Performance Analytics</h2>
            <p className="text-xs spu-text-secondary">
              Historical resource trends, node-to-node comparisons, availability SLA &amp; bottleneck detection
            </p>
          </div>
        </div>

        <div className="flex flex-wrap items-center gap-2">
          <div className="spu-subcard inline-flex p-1 text-xs">
            {['1h', '6h', '12h', '24h'].map((rk) => (
              <button
                key={rk}
                onClick={() => setRangeKey(rk)}
                className={`rounded-md px-2.5 py-1 font-semibold transition ${
                  rangeKey === rk
                    ? 'bg-[var(--accent-cyan-strong)] text-white'
                    : 'spu-text-secondary hover:text-[var(--text-primary)]'
                }`}
              >
                {rk}
              </button>
            ))}
          </div>

          <a
            href={api.getReportExportUrl('performance_history', 'csv', rangeMins)}
            className="spu-btn-secondary inline-flex items-center gap-1.5"
          >
            <Download className="h-3.5 w-3.5 text-[var(--accent-cyan)]" />
            Export CSV
          </a>

          <a
            href={api.getReportExportUrl('performance_history', 'pdf', rangeMins)}
            className="spu-btn-primary inline-flex items-center gap-1.5"
          >
            <FileText className="h-3.5 w-3.5" />
            Export PDF
          </a>
        </div>
      </div>

      {/* Availability & Bottleneck Banner */}
      <section className="grid grid-cols-1 gap-4 lg:grid-cols-12">
        <div className="spu-card p-4 lg:col-span-4 flex flex-col justify-center">
          <div className="text-xs spu-text-secondary">Cluster Availability ({rangeKey})</div>
          <div className="mt-1 text-3xl font-extrabold text-emerald-400">
            {availability.toFixed(2)}%
          </div>
          <div className="mt-1 text-[11px] spu-text-muted">
            Core-Hours Protected: {snapshot?.kpis?.core_hours_saved ?? 0} core-hrs
          </div>
        </div>

        <div className="spu-card p-4 lg:col-span-8">
          <div className="text-xs font-bold mb-2">Automated Bottleneck Analysis</div>
          {bottlenecks.length === 0 ? (
            <div className="flex items-center gap-2.5 text-xs text-emerald-400 py-2">
              <CheckCircle2 className="h-4 w-4" />
              <span>
                No compute, memory, storage I/O, or MPI straggler bottlenecks detected across the {rangeKey} window.
              </span>
            </div>
          ) : (
            <div className="space-y-1.5">
              {bottlenecks.map((b, idx) => (
                <div
                  key={`${b.node_id}-${idx}`}
                  className="flex items-start gap-2 rounded-lg p-2 text-xs spu-subcard"
                >
                  <AlertCircle className="h-4 w-4 shrink-0 text-amber-400 mt-0.5" />
                  <div>
                    <strong>
                      {b.node_id} — {b.type}:
                    </strong>{' '}
                    <span className="spu-text-secondary">{b.detail}</span>
                  </div>
                </div>
              ))}
            </div>
          )}
        </div>
      </section>

      {/* Historical Charts Grid */}
      <section className="grid grid-cols-1 gap-4 lg:grid-cols-2">
        {/* 1. Historical CPU & Memory */}
        <div className="spu-card p-4">
          <h3 className="mb-2 text-xs font-bold">
            Historical Cluster CPU &amp; Memory Utilisation (%)
          </h3>
          <div className="h-60">
            <ResponsiveContainer width="100%" height="100%">
              <AreaChart data={historySeries}>
                <CartesianGrid strokeDasharray="3 3" stroke={chartTheme.grid} />
                <XAxis dataKey="time" tick={{ fill: chartTheme.axis, fontSize: 10 }} />
                <YAxis domain={[0, 100]} tick={{ fill: chartTheme.axis, fontSize: 10 }} width={34} />
                <Tooltip contentStyle={chartTheme.tooltipStyle} />
                <Legend wrapperStyle={{ fontSize: '11px' }} />
                <Area
                  type="monotone"
                  dataKey="cpu"
                  name="Mean CPU %"
                  stroke={chartTheme.cyan}
                  fill={chartTheme.cyan}
                  fillOpacity={0.14}
                  strokeWidth={2}
                  isAnimationActive={false}
                />
                <Area
                  type="monotone"
                  dataKey="memory"
                  name="Mean Memory %"
                  stroke={chartTheme.purple}
                  fill={chartTheme.purple}
                  fillOpacity={0.12}
                  strokeWidth={2}
                  isAnimationActive={false}
                />
              </AreaChart>
            </ResponsiveContainer>
          </div>
        </div>

        {/* 2. Node-to-Node Comparison */}
        <div className="spu-card p-4">
          <h3 className="mb-2 text-xs font-bold">
            Node-to-Node Resource Comparison ({rangeKey} Mean %)
          </h3>
          <div className="h-60">
            <ResponsiveContainer width="100%" height="100%">
              <BarChart data={comparisons}>
                <CartesianGrid strokeDasharray="3 3" stroke={chartTheme.grid} />
                <XAxis dataKey="display_name" tick={{ fill: chartTheme.axis, fontSize: 10 }} />
                <YAxis domain={[0, 100]} tick={{ fill: chartTheme.axis, fontSize: 10 }} width={34} />
                <Tooltip contentStyle={chartTheme.tooltipStyle} />
                <Legend wrapperStyle={{ fontSize: '11px' }} />
                <Bar dataKey="avg_cpu" name="CPU %" fill={chartTheme.cyan} radius={[4, 4, 0, 0]} />
                <Bar dataKey="avg_memory" name="Memory %" fill={chartTheme.purple} radius={[4, 4, 0, 0]} />
                <Bar dataKey="avg_iowait" name="I/O Wait %" fill={chartTheme.amber} radius={[4, 4, 0, 0]} />
              </BarChart>
            </ResponsiveContainer>
          </div>
        </div>

        {/* 3. Disk Write & Network Throughput Trends */}
        <div className="spu-card p-4 lg:col-span-2">
          <h3 className="mb-2 text-xs font-bold">
            Aggregate Disk Write &amp; Network Receive Throughput Trends (MB/s)
          </h3>
          <div className="h-56">
            <ResponsiveContainer width="100%" height="100%">
              <LineChart data={historySeries}>
                <CartesianGrid strokeDasharray="3 3" stroke={chartTheme.grid} />
                <XAxis dataKey="time" tick={{ fill: chartTheme.axis, fontSize: 10 }} />
                <YAxis tick={{ fill: chartTheme.axis, fontSize: 10 }} width={40} />
                <Tooltip contentStyle={chartTheme.tooltipStyle} />
                <Legend wrapperStyle={{ fontSize: '11px' }} />
                <Line
                  type="monotone"
                  dataKey="net_rx_mb"
                  name="Network RX MB/s"
                  stroke={chartTheme.emerald}
                  strokeWidth={2}
                  dot={false}
                  isAnimationActive={false}
                />
                <Line
                  type="monotone"
                  dataKey="disk_write_mb"
                  name="Disk Write MB/s"
                  stroke={chartTheme.amber}
                  strokeWidth={2}
                  dot={false}
                  isAnimationActive={false}
                />
              </LineChart>
            </ResponsiveContainer>
          </div>
        </div>
      </section>
    </div>
  );
}
