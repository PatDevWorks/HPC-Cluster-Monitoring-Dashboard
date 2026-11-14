import React, { useMemo, useState } from 'react';
import {
  Activity,
  Cpu,
  FileTerminal,
  HardDrive,
  Network,
  PlayCircle,
  Server,
  ShieldOff,
  Terminal,
  Wifi,
} from 'lucide-react';

function formatUptime(sec) {
  if (sec == null) return 'Unavailable';
  const d = Math.floor(sec / 86400);
  const h = Math.floor((sec % 86400) / 3600);
  const m = Math.floor((sec % 3600) / 60);
  return d > 0 ? `${d}d ${h}h ${m}m` : `${h}h ${m}m`;
}

export default function TopologyPage({
  snapshot,
  onInspectMonitoring,
  onInspectLogs,
  onOpenTerminal,
  onRequestDrain,
  onRequestResume,
}) {
  const nodes = snapshot?.nodes || [];
  const headNode = useMemo(
    () => nodes.find((n) => n.role === 'management') || nodes[0] || null,
    [nodes]
  );
  const computeNodes = useMemo(
    () => nodes.filter((n) => n !== headNode),
    [nodes, headNode]
  );

  const [selectedId, setSelectedId] = useState(() => headNode?.node_id || 'head-node');

  const selectedNode = useMemo(
    () => nodes.find((n) => n.node_id === selectedId) || headNode || nodes[0],
    [nodes, selectedId, headNode]
  );

  const jobsOnSelected = useMemo(() => {
    if (!selectedNode) return [];
    return (snapshot?.slurm_jobs || []).filter(
      (j) =>
        j.state === 'RUNNING' &&
        (j.nodes || []).includes(selectedNode.node_id)
    );
  }, [snapshot?.slurm_jobs, selectedNode]);

  return (
    <div className="space-y-5">
      {/* Header */}
      <div className="flex flex-wrap items-center justify-between gap-3">
        <div className="flex items-center gap-3">
          <div className="flex h-10 w-10 items-center justify-center rounded-xl bg-cyan-500/15 text-[var(--accent-cyan)]">
            <Network className="h-5 w-5" />
          </div>
          <div>
            <h2 className="text-xl font-bold tracking-tight">Cluster Topology</h2>
            
          </div>
        </div>

        
      </div>

      <div className="grid grid-cols-1 gap-5 xl:grid-cols-12">
        {/* Left: Interactive Topology Diagram */}
        <div className="spu-card p-6 xl:col-span-8">
          <div className="mb-4 flex items-center justify-between text-xs spu-text-secondary">
            <span>
              Source: <strong>{snapshot?.mode_label || 'Cluster Discovery'}</strong>
            </span>
            <span>Click any node to inspect hardware &amp; interconnect state</span>
          </div>

          <div className="flex flex-col items-center py-2">
            {/* Tier 1: Head / Management Node */}
            {headNode && (
              <div
                onClick={() => setSelectedId(headNode.node_id)}
                className={`w-full max-w-md cursor-pointer rounded-xl border-2 p-4 transition ${
                  selectedNode?.node_id === headNode.node_id
                    ? 'border-[var(--accent-cyan)] bg-cyan-500/8'
                    : 'spu-subcard hover:border-[var(--accent-cyan)]'
                }`}
              >
                <div className="flex items-center justify-between">
                  <div className="flex items-center gap-2.5">
                    <span
                      className={`h-3 w-3 rounded-full ${
                        headNode.health_status === 'offline' || headNode.health_status === 'critical' || headNode.up !== 1
                          ? 'bg-rose-500'
                          : headNode.health_status === 'warning' || headNode.health_status === 'stale'
                          ? 'bg-amber-400'
                          : 'bg-emerald-400'
                      }`}
                    />
                    <div>
                      <div className="text-sm font-bold">
                        {headNode.display_name || headNode.node_id}
                      </div>
                      <div className="font-mono text-[11px] spu-text-secondary">
                        {headNode.ip} • {headNode.role.toUpperCase()}
                      </div>
                    </div>
                  </div>
                  <span className="rounded-md bg-cyan-500/15 px-2 py-0.5 font-mono text-[10px] font-bold text-[var(--accent-cyan)]">
                    {headNode.slurm_state}
                  </span>
                </div>

                <div className="mt-2.5 flex flex-wrap gap-1.5 text-[10px] spu-text-secondary">
                  <span className="rounded border px-1.5 py-0.5 spu-border">slurmctld</span>
                  <span className="rounded border px-1.5 py-0.5 spu-border">Prometheus :9090</span>
                  <span className="rounded border px-1.5 py-0.5 spu-border">Grafana :3000</span>
                  <span className="rounded border px-1.5 py-0.5 spu-border">NFS /scratch</span>
                </div>
              </div>
            )}

            {/* Interconnect Fabric Spine */}
            <div className="my-2 flex w-full flex-col items-center">
              <div className="h-7 w-0.5 bg-[var(--accent-cyan)] opacity-60" />
              <div className="flex items-center gap-2 rounded-full border px-4 py-1 text-[11px] font-semibold spu-subcard text-[var(--accent-cyan)]">
                <Wifi className="h-3.5 w-3.5" />
                10GbE High-Speed Cluster Interconnect Fabric
              </div>
              <div className="h-6 w-0.5 bg-[var(--accent-cyan)] opacity-60" />
              <div className="h-0.5 w-4/5 bg-[var(--border-strong)]" />
            </div>

            {/* Tier 2: Compute Nodes Pool */}
            <div
              className={`mt-4 grid w-full gap-3.5 ${
                computeNodes.length <= 3
                  ? 'grid-cols-1 md:grid-cols-3'
                  : 'grid-cols-1 sm:grid-cols-2 lg:grid-cols-4'
              }`}
            >
              {computeNodes.map((node) => {
                const up = node.up === 1;
                const hs = node.health_status || (up ? 'healthy' : 'offline');
                const hasV7Anom = Boolean(node.v7_detection?.is_anomaly);
                const hasLstmWarn = Boolean(node.lstm_v8_status?.latest_warning?.is_warning);
                const isDrained = String(node.slurm_state || '').includes('DRAIN');
                const netErr = Number(node.network_errors_per_second || 0);
                const selected = selectedNode?.node_id === node.node_id;

                const statusColor =
                  !up || hs === 'offline' || hs === 'critical'
                    ? 'border-rose-500/70'
                    : hs === 'stale' || hs === 'warning' || hs === 'maintenance' || isDrained || hasV7Anom || hasLstmWarn
                    ? 'border-amber-500/70'
                    : selected
                    ? 'border-[var(--accent-cyan)]'
                    : 'border-[var(--border-subtle)]';

                const dotBg =
                  !up || hs === 'offline' || hs === 'critical'
                    ? 'bg-rose-500'
                    : hs === 'stale' || hs === 'warning' || hs === 'maintenance' || isDrained || hasV7Anom || hasLstmWarn
                    ? 'bg-amber-400'
                    : 'bg-emerald-400';

                return (
                  <div
                    key={node.node_id}
                    onClick={() => setSelectedId(node.node_id)}
                    className={`cursor-pointer rounded-xl border-2 p-3.5 transition spu-subcard hover:border-[var(--accent-cyan)] ${statusColor}`}
                  >
                    <div className="flex items-start justify-between gap-2">
                      <div className="flex items-center gap-2">
                        <span className={`h-2.5 w-2.5 rounded-full ${dotBg}`} />
                        <span className="text-sm font-bold">
                          {node.display_name || node.node_id}
                        </span>
                      </div>
                      <span className="rounded bg-[var(--bg-card)] px-1.5 py-0.5 font-mono text-[10px] font-semibold">
                        {node.slurm_state}
                      </span>
                    </div>

                    <div className="mt-1 font-mono text-[11px] spu-text-secondary">
                      IP: {node.ip}
                    </div>
                    <div className="mt-2 grid grid-cols-2 gap-1.5 text-[11px]">
                      <div className="rounded bg-[var(--bg-card)] px-2 py-1">
                        <span className="spu-text-muted">CPU: </span>
                        <strong className="font-mono">
                          {node.cpu_utilization_percent != null
                            ? `${Math.round(node.cpu_utilization_percent)}%`
                            : 'N/A'}
                        </strong>
                      </div>
                      <div className="rounded bg-[var(--bg-card)] px-2 py-1">
                        <span className="spu-text-muted">RAM: </span>
                        <strong className="font-mono">
                          {node.memory_used_percent != null
                            ? `${Math.round(node.memory_used_percent)}%`
                            : 'N/A'}
                        </strong>
                      </div>
                    </div>

                    <div className="mt-2 flex flex-wrap items-center justify-between gap-1 text-[10px] spu-text-muted">
                      <span className="uppercase font-mono">{hs}</span>
                      {(hasV7Anom || hasLstmWarn) && (
                        <span className="rounded bg-amber-500/20 px-1.5 py-0.5 font-mono text-amber-300">
                          {[hasV7Anom ? 'V7' : null, hasLstmWarn ? 'LSTM' : null].filter(Boolean).join('+')}
                        </span>
                      )}
                      <span className={netErr > 0.2 ? 'text-rose-400 font-semibold' : ''}>
                        {netErr > 0 ? `${netErr.toFixed(2)} err/s` : 'Link OK'}
                      </span>
                    </div>
                  </div>
                );
              })}
            </div>
          </div>
        </div>

        {/* Right: Selected Node Infrastructure Inspector */}
        <div className="spu-card flex flex-col justify-between p-5 xl:col-span-4">
          {selectedNode ? (
            <>
              <div>
                <div className="flex items-center justify-between border-b pb-3 spu-border">
                  <div className="flex items-center gap-2.5">
                    <Server className="h-5 w-5 text-[var(--accent-cyan)]" />
                    <div>
                      <h3 className="text-base font-bold">
                        {selectedNode.display_name || selectedNode.node_id}
                      </h3>
                      <p className="font-mono text-xs spu-text-secondary">
                        {selectedNode.instance}
                      </p>
                    </div>
                  </div>
                  <span
                    className={`rounded-full px-2.5 py-0.5 text-[11px] font-bold ${
                      selectedNode.up === 1
                        ? 'bg-emerald-500/15 text-emerald-400'
                        : 'bg-rose-500/15 text-rose-400'
                    }`}
                  >
                    {selectedNode.up === 1 ? 'ONLINE' : 'OFFLINE'}
                  </span>
                </div>

                {/* Spec Table */}
                <div className="mt-4 space-y-2 text-xs">
                  {[
                    ['Node Identifier', selectedNode.node_id],
                    ['IP Address', selectedNode.ip],
                    ['Cluster Role', selectedNode.role],
                    ['Rack Location', selectedNode.rack_id || 'rack-1'],
                    ['Slurm State', selectedNode.slurm_state],
                    ['Processor', selectedNode.cpu_model || 'x86_64 Server CPU'],
                    ['Logical Cores', `${selectedNode.cpu_cores} Cores`],
                    ['Installed Memory', `${selectedNode.memory_gib} GiB`],
                    ['OS / Kernel', selectedNode.os_kernel || 'Linux'],
                    ['Node Uptime', formatUptime(selectedNode.uptime_seconds)],
                    [
                      'Network RX / TX',
                      selectedNode.network_receive_bytes_per_second != null
                        ? `${(
                            selectedNode.network_receive_bytes_per_second / 1048576
                          ).toFixed(2)} / ${(
                            (selectedNode.network_transmit_bytes_per_second || 0) /
                            1048576
                          ).toFixed(2)} MB/s`
                        : 'Unavailable',
                    ],
                    [
                      'Operational Status',
                      `${selectedNode.health_classification || selectedNode.health_status || 'Healthy'} (${selectedNode.alert_priority || 'OK'})`,
                    ],
                    [
                      'V7 Isolation Forest',
                      selectedNode.v7_detection?.anomaly_score != null
                        ? `${selectedNode.v7_detection.anomaly_score.toFixed(4)} (${selectedNode.v7_detection.is_anomaly ? 'Anomaly' : 'Normal'})`
                        : selectedNode.v7_detection?.status || 'Pending',
                    ],
                    [
                      'LSTM V8 Warning',
                      selectedNode.lstm_v8_status?.latest_warning
                        ? `${selectedNode.lstm_v8_status.latest_warning.status || (selectedNode.lstm_v8_status.latest_warning.is_warning ? 'WARNING' : 'NORMAL')} (${Number(selectedNode.lstm_v8_status.latest_warning.warning_score ?? 0).toFixed(3)})`
                        : 'Unavailable',
                    ],
                    [
                      'Last Telemetry Update',
                      selectedNode.last_telemetry_utc
                        ? selectedNode.last_telemetry_utc.slice(0, 19).replace('T', ' ') + 'Z'
                        : 'Unavailable',
                    ],
                  ].map(([k, v]) => (
                    <div
                      key={k}
                      className="flex items-center justify-between border-b py-1.5 spu-border"
                    >
                      <span className="spu-text-secondary">{k}</span>
                      <span className="font-mono font-medium">{v}</span>
                    </div>
                  ))}
                </div>

                {/* Active Jobs on Node */}
                <div className="mt-4">
                  <div className="text-xs font-semibold spu-text-secondary">
                    Allocated Slurm Jobs ({jobsOnSelected.length})
                  </div>
                  {jobsOnSelected.length === 0 ? (
                    <p className="mt-1 text-xs spu-text-muted">
                      No active compute jobs currently allocated on this node.
                    </p>
                  ) : (
                    <div className="mt-2 space-y-1.5">
                      {jobsOnSelected.map((j) => (
                        <div
                          key={j.job_id}
                          className="flex items-center justify-between rounded-lg px-2.5 py-1.5 text-xs spu-subcard"
                        >
                          <span className="font-mono font-semibold text-[var(--accent-cyan)]">
                            #{j.job_id} {j.name}
                          </span>
                          <span className="spu-text-muted">{j.user}</span>
                        </div>
                      ))}
                    </div>
                  )}
                </div>
              </div>

              {/* Action Buttons */}
              <div className="mt-5 grid grid-cols-2 gap-2 pt-3 border-t spu-border">
                <button
                  onClick={() => onInspectMonitoring(selectedNode.node_id)}
                  className="spu-btn-primary inline-flex items-center justify-center gap-1.5"
                >
                  <Activity className="h-3.5 w-3.5" />
                  Live Metrics
                </button>
                <button
                  onClick={() => onInspectLogs(selectedNode.node_id)}
                  className="spu-btn-secondary inline-flex items-center justify-center gap-1.5"
                >
                  <FileTerminal className="h-3.5 w-3.5" />
                  Node Logs
                </button>
                {onOpenTerminal && (
                  <button
                    onClick={() => onOpenTerminal(selectedNode.node_id)}
                    className="spu-btn-secondary col-span-2 inline-flex items-center justify-center gap-1.5"
                  >
                    <Terminal className="h-3.5 w-3.5 text-[var(--accent-cyan)]" />
                    Open Instance Terminal ({selectedNode.display_name || selectedNode.node_id})
                  </button>
                )}
                {selectedNode.role !== 'management' && (
                  <div className="col-span-2">
                    {String(selectedNode.slurm_state || '').includes('DRAIN') ? (
                      <button
                        onClick={() => onRequestResume(selectedNode)}
                        className="w-full rounded-lg bg-emerald-600 py-2 text-xs font-semibold text-white hover:bg-emerald-500 inline-flex items-center justify-center gap-1.5"
                      >
                        <PlayCircle className="h-3.5 w-3.5" />
                        Resume Node in Slurm
                      </button>
                    ) : (
                      <button
                        onClick={() => onRequestDrain(selectedNode)}
                        className="w-full rounded-lg bg-amber-500/20 py-2 text-xs font-semibold text-amber-400 border border-amber-500/40 hover:bg-amber-500/30 inline-flex items-center justify-center gap-1.5"
                      >
                        <ShieldOff className="h-3.5 w-3.5" />
                        Drain Node via Slurm
                      </button>
                    )}
                  </div>
                )}
              </div>
            </>
          ) : (
            <p className="text-xs spu-text-secondary">Select a node to view specifications.</p>
          )}
        </div>
      </div>
    </div>
  );
}
