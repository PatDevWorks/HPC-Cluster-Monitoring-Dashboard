
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
  AlertTriangle,
  Clock,
  Cpu,
  MemoryStick,
  Network,
  HardDrive,
  Activity,
  Server,
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

const LSTM_NODE_MAP = {
  'head-node': 'headnode',
  'compute-01': 'compute001',
  'compute-02': 'compute002',
  'compute-03': 'compute003',
};

const DASHBOARD_NODE_MAP = {
  headnode: 'head-node',
  compute001: 'compute-01',
  compute002: 'compute-02',
  compute003: 'compute-03',
};

const FORECAST_METRICS = {
  cpu_utilisation_pct_mean: {
    label: 'CPU Utilisation',
    shortLabel: 'CPU',
    unit: '%',
    icon: Cpu,
    color: '#06b6d4',
  },
  memory_used_pct_mean: {
    label: 'Memory Utilisation',
    shortLabel: 'Memory',
    unit: '%',
    icon: MemoryStick,
    color: '#a78bfa',
  },
  network_rx_mib_s_mean: {
    label: 'Network Receive',
    shortLabel: 'Network RX',
    unit: 'MiB/s',
    icon: Network,
    color: '#10b981',
  },
  network_tx_mib_s_mean: {
    label: 'Network Transmit',
    shortLabel: 'Network TX',
    unit: 'MiB/s',
    icon: Network,
    color: '#f59e0b',
  },
  disk_read_mib_s_mean: {
    label: 'Disk Read',
    shortLabel: 'Disk Read',
    unit: 'MiB/s',
    icon: HardDrive,
    color: '#8b5cf6',
  },
  disk_write_mib_s_mean: {
    label: 'Disk Write',
    shortLabel: 'Disk Write',
    unit: 'MiB/s',
    icon: HardDrive,
    color: '#ec4899',
  },
  node_load1_per_core_mean: {
    label: 'Load Average per Core',
    shortLabel: 'Load/Core',
    unit: '',
    icon: Activity,
    color: '#f97316',
  },
  iowait_pct_mean: {
    label: 'I/O Wait',
    shortLabel: 'I/O Wait',
    unit: '%',
    icon: Clock,
    color: '#eab308',
  },
};

const formatNumber = (value, decimals = 2) => {
  if (value === null || value === undefined || !Number.isFinite(Number(value))) {
    return 'N/A';
  }

  return Number(value).toFixed(decimals);
};

const formatTimestamp = (value) => {
  if (!value) return 'Not available';

  const date = new Date(value);

  if (Number.isNaN(date.getTime())) return value;

  return date.toLocaleString();
};

const getLstmNodeName = (nodeId) => {
  const names = {
    headnode: 'Head Node',
    compute001: 'Compute Node 001',
    compute002: 'Compute Node 002',
    compute003: 'Compute Node 003',
  };

  return names[nodeId] || nodeId;
};

function LSTMV8Section({
  snapshot,
  selectedNodeId,
  onSelectNode,
}) {
  const { chartTheme } = useTheme();
  const lstmStatus = snapshot?.lstm_v8 || {};
  const lstmState = lstmStatus.state || {};
  const lstmNodes = lstmState.nodes || {};

  const availableNodes = Object.keys(lstmNodes);

  const selectedLstmNodeId =
    LSTM_NODE_MAP[selectedNodeId] ||
    (availableNodes.includes(selectedNodeId) ? selectedNodeId : null) ||
    availableNodes[0] ||
    null;

  const [selectedMetric, setSelectedMetric] = useState(
    'cpu_utilisation_pct_mean'
  );

  const [selectedForecastHorizon, setSelectedForecastHorizon] =
    useState(15);

  const activeLstmNode = selectedLstmNodeId
    ? lstmNodes[selectedLstmNodeId]
    : null;

  const forecast = activeLstmNode?.latest_forecast;
  const warning = activeLstmNode?.latest_warning;

  const horizons = forecast?.horizons || [];

  const selectedForecast =
    horizons.find(
      (item) => item.horizon_minutes === selectedForecastHorizon
    ) || horizons[0];

  const predictedMetrics = selectedForecast?.predicted_metrics || {};

  const chartData = useMemo(() => {
    return horizons.map((item) => ({
      horizon: `${item.horizon_minutes} min`,
      minutes: item.horizon_minutes,
      value: item.predicted_metrics?.[selectedMetric] ?? null,
    }));
  }, [horizons, selectedMetric]);

  const metricConfig = FORECAST_METRICS[selectedMetric];

  const warningComponents = warning?.components || {};

  const connected = Boolean(lstmStatus.connected);

  const nodeCount = availableNodes.length;

  const handleNodeSelect = (nodeId) => {
    const dashboardId = DASHBOARD_NODE_MAP[nodeId];

    if (dashboardId && onSelectNode) {
      onSelectNode(dashboardId);
    }
  };

  return (
    <section className="space-y-4">
      {/* LSTM V8 Header */}
      <div className="spu-card p-5">
        <div className="flex flex-wrap items-center justify-between gap-4">
          <div className="flex items-center gap-3">
            <div className="flex h-11 w-11 items-center justify-center rounded-xl bg-cyan-500/15 text-[var(--accent-cyan)]">
              <BrainCircuit className="h-6 w-6" />
            </div>

            <div>
              <div className="flex flex-wrap items-center gap-2">
                <h3 className="text-lg font-bold">
                  LSTM V8 Early Warning & Forecasting
                </h3>

                <span
                  className={`rounded-full px-2 py-1 text-[10px] font-bold ${
                    connected
                      ? 'bg-emerald-500/15 text-emerald-400'
                      : 'bg-rose-500/15 text-rose-400'
                  }`}
                >
                  {connected ? 'API CONNECTED' : 'API DISCONNECTED'}
                </span>
              </div>

              <p className="text-xs spu-text-secondary">
                Deployed LSTM V8 inference service · HPC cluster resource forecasting
              </p>
            </div>
          </div>

          <div className="text-right text-xs spu-text-secondary">
            <div>Last successful API update</div>
            <strong className="font-mono">
              {formatTimestamp(lstmStatus.last_success_utc)}
            </strong>
          </div>
        </div>

        {lstmStatus.last_error && (
          <div className="mt-3 rounded-lg border border-rose-500/30 bg-rose-500/10 p-3 text-xs text-rose-400">
            API error: {lstmStatus.last_error}
          </div>
        )}

        <div className="mt-4 grid grid-cols-2 gap-3 lg:grid-cols-4">
          <div className="spu-subcard rounded-xl p-3">
            <div className="text-[10px] uppercase spu-text-muted">
              Connected Nodes
            </div>
            <div className="mt-1 font-mono text-2xl font-bold">
              {connected ? `${nodeCount}/4` : '0/4'}
            </div>
            <div className="text-[10px] spu-text-secondary">
              LSTM monitored nodes
            </div>
          </div>

          <div className="spu-subcard rounded-xl p-3">
            <div className="text-[10px] uppercase spu-text-muted">
              History Requirement
            </div>
            <div className="mt-1 font-mono text-2xl font-bold">
              {activeLstmNode
                ? `${activeLstmNode.history_count || 0}/${activeLstmNode.required_observations || 60}`
                : 'N/A'}
            </div>
            <div className="text-[10px] spu-text-secondary">
              Observations collected
            </div>
          </div>

          <div className="spu-subcard rounded-xl p-3">
            <div className="text-[10px] uppercase spu-text-muted">
              Forecast Horizons
            </div>
            <div className="mt-1 font-mono text-2xl font-bold">
              {horizons.length || 0}
            </div>
            <div className="text-[10px] spu-text-secondary">
              Forecast intervals
            </div>
          </div>

          <div className="spu-subcard rounded-xl p-3">
            <div className="text-[10px] uppercase spu-text-muted">
              Warning Status
            </div>
            <div
              className={`mt-1 text-lg font-bold ${
                warning?.is_warning
                  ? 'text-rose-400'
                  : warning?.status === 'scored'
                  ? 'text-emerald-400'
                  : 'spu-text-secondary'
              }`}
            >
              {warning?.status === 'scored'
                ? warning.is_warning
                  ? 'WARNING'
                  : 'NORMAL'
                : 'PENDING'}
            </div>
            <div className="text-[10px] spu-text-secondary">
              Latest model warning
            </div>
          </div>
        </div>
      </div>

      {/* Node Selection */}
      <div>
        <div className="mb-2 flex items-center justify-between">
          <h4 className="text-sm font-bold">LSTM Node Monitoring</h4>
          <span className="text-[10px] spu-text-secondary">
            Select a node to inspect its forecasts
          </span>
        </div>

        <div className="grid grid-cols-1 gap-3 sm:grid-cols-2 xl:grid-cols-4">
          {availableNodes.map((nodeId) => {
            const node = lstmNodes[nodeId];
            const nodeWarning = node.latest_warning;
            const nodeForecast = node.latest_forecast;

            const isSelected = nodeId === selectedLstmNodeId;

            return (
              <button
                key={nodeId}
                type="button"
                onClick={() => handleNodeSelect(nodeId)}
                className={`spu-card p-4 text-left transition ${
                  isSelected
                    ? 'ring-2 ring-[var(--accent-cyan)]'
                    : 'hover:border-[var(--accent-cyan)]'
                }`}
              >
                <div className="flex items-start justify-between gap-2">
                  <div>
                    <div className="flex items-center gap-2 text-sm font-bold">
                      <Server className="h-4 w-4 text-[var(--accent-cyan)]" />
                      {getLstmNodeName(nodeId)}
                    </div>

                    <div className="mt-1 text-[10px] spu-text-muted font-mono">
                      {nodeId}
                    </div>
                  </div>

                  <span
                    className={`rounded px-2 py-1 text-[9px] font-bold ${
                      nodeWarning?.is_warning
                        ? 'bg-rose-500/15 text-rose-400'
                        : nodeWarning?.status === 'scored'
                        ? 'bg-emerald-500/15 text-emerald-400'
                        : 'bg-amber-500/15 text-amber-400'
                    }`}
                  >
                    {nodeWarning?.status === 'scored'
                      ? nodeWarning.is_warning
                        ? 'WARNING'
                        : 'NORMAL'
                      : 'PENDING'}
                  </span>
                </div>

                <div className="mt-4 grid grid-cols-2 gap-2">
                  <div className="spu-subcard rounded-lg p-2">
                    <div className="text-[9px] uppercase spu-text-muted">
                      History
                    </div>
                    <div className="mt-1 font-mono text-lg font-bold">
                      {node.history_count ?? 0}/
                      {node.required_observations ?? 60}
                    </div>
                  </div>

                  <div className="spu-subcard rounded-lg p-2">
                    <div className="text-[9px] uppercase spu-text-muted">
                      Warning Score
                    </div>
                    <div className="mt-1 font-mono text-lg font-bold">
                      {formatNumber(nodeWarning?.warning_score)}
                    </div>
                  </div>
                </div>

                <div className="mt-3 text-[10px] spu-text-secondary">
                  Forecast:{' '}
                  {nodeForecast ? 'Available' : 'Not available'}
                </div>
              </button>
            );
          })}

          {connected && availableNodes.length === 0 && (
            <div className="spu-card p-4 text-xs spu-text-secondary">
              The API is connected, but no node states have been returned.
            </div>
          )}

          {!connected && (
            <div className="spu-card col-span-full p-4 text-xs spu-text-secondary">
              LSTM V8 is not currently connected. Check the backend API
              connection and SSH tunnel.
            </div>
          )}
        </div>
      </div>

      {/* Active Node Forecasts */}
      {activeLstmNode && (
        <>
          <div className="spu-card p-5">
            <div className="flex flex-wrap items-center justify-between gap-3">
              <div>
                <h4 className="text-sm font-bold">
                  Resource Forecasts — {getLstmNodeName(selectedLstmNodeId)}
                </h4>
                <p className="mt-1 text-xs spu-text-secondary">
                  Predicted resource metrics across the available forecast horizons.
                </p>
              </div>

              <div className="text-right text-[10px] spu-text-secondary">
                Forecast generated
                <div className="font-mono">
                  {formatTimestamp(forecast?.generated_at_utc)}
                </div>
              </div>
            </div>

            <div className="mt-4 flex flex-wrap gap-2">
              {[1, 15, 30, 60].map((minutes) => {
                const available = horizons.some(
                  (item) => item.horizon_minutes === minutes
                );

                return (
                  <button
                    key={minutes}
                    type="button"
                    disabled={!available}
                    onClick={() => setSelectedForecastHorizon(minutes)}
                    className={`rounded-lg px-4 py-2 text-xs font-semibold transition disabled:cursor-not-allowed disabled:opacity-30 ${
                      selectedForecastHorizon === minutes
                        ? 'bg-[var(--accent-cyan-strong)] text-white'
                        : 'spu-subcard spu-text-secondary'
                    }`}
                  >
                    {minutes} min
                  </button>
                );
              })}
            </div>

            {activeLstmNode.forecast_pending_validation && (
              <div className="mt-3 flex items-start gap-2 rounded-lg border border-amber-500/30 bg-amber-500/10 p-3 text-xs text-amber-400">
                <Clock className="mt-0.5 h-4 w-4 shrink-0" />
                <div>
                  <strong>Forecast awaiting validation.</strong>
                  These are model-generated predictions. They have not yet
                  been confirmed against the corresponding future observations.
                </div>
              </div>
            )}

            <div className="mt-4 grid grid-cols-2 gap-3 sm:grid-cols-4">
              {Object.entries(FORECAST_METRICS).map(([key, config]) => {
                const Icon = config.icon;
                const value = predictedMetrics[key];

                return (
                  <div
                    key={key}
                    className="spu-subcard rounded-xl p-3"
                  >
                    <div className="flex items-center gap-2 text-[10px] spu-text-secondary">
                      <Icon
                        className="h-4 w-4"
                        style={{ color: config.color }}
                      />
                      {config.shortLabel}
                    </div>

                    <div className="mt-2 font-mono text-xl font-bold">
                      {formatNumber(value)}
                    </div>

                    <div className="text-[10px] spu-text-muted">
                      {config.unit || 'Load'}
                    </div>
                  </div>
                );
              })}
            </div>

            <div className="mt-4 border-t pt-3 spu-border">
              <div className="flex flex-wrap justify-between gap-2 text-xs spu-text-secondary">
                <span>
                  Target time:{' '}
                  <strong className="font-mono">
                    {formatTimestamp(selectedForecast?.target_timestamp_utc)}
                  </strong>
                </span>

                <span>
                  Forecast horizon:{' '}
                  <strong>
                    {selectedForecast?.horizon_minutes ?? 'N/A'} minutes
                  </strong>
                </span>
              </div>
            </div>
          </div>

          {/* Forecast Trend Chart */}
          <div className="spu-card p-5">
            <div className="flex flex-wrap items-center justify-between gap-3">
              <div>
                <h4 className="text-sm font-bold">
                  Forecast Trend Analysis
                </h4>
                <p className="mt-1 text-xs spu-text-secondary">
                  How the selected resource metric changes across the four
                  forecast horizons.
                </p>
              </div>

              <select
                value={selectedMetric}
                onChange={(event) => setSelectedMetric(event.target.value)}
                className="spu-subcard rounded-lg px-3 py-2 text-xs"
              >
                {Object.entries(FORECAST_METRICS).map(([key, config]) => (
                  <option key={key} value={key}>
                    {config.label}
                  </option>
                ))}
              </select>
            </div>

            <div className="mt-4 h-72">
              {chartData.length > 0 ? (
                <ResponsiveContainer width="100%" height="100%">
                  <ComposedChart data={chartData}>
                    <CartesianGrid
                      strokeDasharray="3 3"
                      stroke={chartTheme.grid}
                    />

                    <XAxis
                      dataKey="horizon"
                      tick={{
                        fill: chartTheme.axis,
                        fontSize: 11,
                      }}
                    />

                    <YAxis
                      tick={{
                        fill: chartTheme.axis,
                        fontSize: 10,
                      }}
                      width={55}
                      domain={['auto', 'auto']}
                    />

                    <Tooltip
                      contentStyle={chartTheme.tooltipStyle}
                      formatter={(value) => [
                        `${formatNumber(value)} ${metricConfig.unit}`,
                        metricConfig.label,
                      ]}
                    />

                    <Legend wrapperStyle={{ fontSize: '11px' }} />

                    <Line
                      type="monotone"
                      dataKey="value"
                      name={`${metricConfig.label} Forecast`}
                      stroke={metricConfig.color}
                      strokeWidth={2.5}
                      dot={{ r: 5 }}
                      activeDot={{ r: 7 }}
                      connectNulls={false}
                      isAnimationActive={false}
                    />
                  </ComposedChart>
                </ResponsiveContainer>
              ) : (
                <div className="flex h-full items-center justify-center text-xs spu-text-secondary">
                  No forecast values available for this metric.
                </div>
              )}
            </div>

            <p className="mt-2 text-[10px] spu-text-muted">
              Chart values are raw model outputs. Negative predictions for
              non-negative physical quantities are retained for visibility
              and should be investigated during model validation.
            </p>
          </div>

          {/* Warning Analysis */}
          <div className="spu-card p-5">
            <div className="flex flex-wrap items-center justify-between gap-3">
              <div className="flex items-center gap-2">
                <ShieldAlert className="h-5 w-5 text-[var(--accent-cyan)]" />
                <div>
                  <h4 className="text-sm font-bold">
                    LSTM V8 Early Warning Analysis
                  </h4>
                  <p className="text-xs spu-text-secondary">
                    Model warning score and contributing components
                  </p>
                </div>
              </div>

              <span
                className={`rounded-lg px-3 py-1.5 text-xs font-bold ${
                  warning?.is_warning
                    ? 'bg-rose-500/15 text-rose-400'
                    : warning?.status === 'scored'
                    ? 'bg-emerald-500/15 text-emerald-400'
                    : 'bg-amber-500/15 text-amber-400'
                }`}
              >
                {warning?.status === 'scored'
                  ? warning.is_warning
                    ? 'WARNING THRESHOLD CROSSED'
                    : 'NO WARNING'
                  : 'NOT SCORED'}
              </span>
            </div>

            {warning?.status === 'scored' ? (
              <>
                <div className="mt-4 grid grid-cols-1 gap-3 sm:grid-cols-3">
                  <div className="spu-subcard rounded-xl p-3">
                    <div className="text-[10px] uppercase spu-text-muted">
                      Warning Score
                    </div>
                    <div className="mt-1 font-mono text-2xl font-bold">
                      {formatNumber(warning.warning_score, 4)}
                    </div>
                  </div>

                  <div className="spu-subcard rounded-xl p-3">
                    <div className="text-[10px] uppercase spu-text-muted">
                      Warning Threshold
                    </div>
                    <div className="mt-1 font-mono text-2xl font-bold">
                      {formatNumber(warning.warning_threshold, 6)}
                    </div>
                  </div>

                  <div className="spu-subcard rounded-xl p-3">
                    <div className="text-[10px] uppercase spu-text-muted">
                      Residual Z Threshold
                    </div>
                    <div className="mt-1 font-mono text-2xl font-bold">
                      {formatNumber(
                        warningComponents.residual_z_threshold
                      )}
                    </div>
                  </div>
                </div>

                <div className="mt-4">
                  <h5 className="mb-2 text-xs font-bold">
                    Warning Components
                  </h5>

                  <div className="grid grid-cols-1 gap-3 sm:grid-cols-3">
                    <div className="spu-subcard rounded-lg p-3">
                      <div className="text-[10px] spu-text-muted">
                        Stress 60m
                      </div>
                      <div className="mt-1 font-mono text-lg font-bold">
                        {formatNumber(warningComponents.stress_60m, 4)}
                      </div>
                    </div>

                    <div className="spu-subcard rounded-lg p-3">
                      <div className="text-[10px] spu-text-muted">
                        Residual Z
                      </div>
                      <div className="mt-1 font-mono text-lg font-bold">
                        {formatNumber(warningComponents.residual_z, 4)}
                      </div>
                      <div
                        className={`mt-1 text-[10px] font-bold ${
                          warningComponents.residual_z_exceeded
                            ? 'text-rose-400'
                            : 'text-emerald-400'
                        }`}
                      >
                        {warningComponents.residual_z_exceeded
                          ? 'Threshold exceeded'
                          : 'Within threshold'}
                      </div>
                    </div>

                    <div className="spu-subcard rounded-lg p-3">
                      <div className="text-[10px] spu-text-muted">
                        Drift Z
                      </div>
                      <div className="mt-1 font-mono text-lg font-bold">
                        {formatNumber(warningComponents.drift_z, 4)}
                      </div>
                    </div>
                  </div>
                </div>

                <div className="mt-4 space-y-1 text-[10px] spu-text-secondary">
                  <div>
                    Forecast origin:{' '}
                    <strong className="font-mono">
                      {formatTimestamp(
                        warning.forecast_origin_timestamp_utc
                      )}
                    </strong>
                  </div>

                  <div>
                    Evaluated at:{' '}
                    <strong className="font-mono">
                      {formatTimestamp(
                        warning.evaluated_at_timestamp_utc
                      )}
                    </strong>
                  </div>
                </div>
              </>
            ) : (
              <div className="mt-4 text-xs spu-text-secondary">
                The model has not returned a scored warning for this node.
              </div>
            )}
          </div>
        </>
      )}
    </section>
  );
}

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
      {/* Existing dashboard ModelEngine predictions remain separate. */}
      <div className="flex flex-wrap items-center justify-between gap-3">
        <div className="flex items-center gap-3">
          <div className="flex h-10 w-10 items-center justify-center rounded-xl bg-cyan-500/15 text-[var(--accent-cyan)]">
            <BrainCircuit className="h-5 w-5" />
          </div>
          <div>
            <h2 className="text-xl font-bold tracking-tight">
              AI &amp; Predictions
            </h2>
            <p className="text-xs spu-text-secondary">
              Predictive node failure analysis, multi-detector anomaly
              consensus &amp; root-cause attributions
            </p>
          </div>
        </div>

        <div className="flex flex-wrap items-center gap-2">
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
            <RefreshCw
              className={`h-3.5 w-3.5 ${
                busyAction ? 'animate-spin' : ''
              }`}
            />
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

      {/* NEW: Deployed LSTM V8 model integration */}
      <LSTMV8Section
        snapshot={snapshot}
        selectedNodeId={selectedNodeId}
        onSelectNode={onSelectNode}
      />

      {/* Existing provenance legend */}
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

      {/* Existing per-node ModelEngine prediction matrix */}
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
                selected
                  ? 'ring-2 ring-[var(--accent-cyan)]'
                  : 'hover:border-[var(--accent-cyan)]'
              }`}
            >
              <div className="flex items-start justify-between">
                <div>
                  <div className="text-sm font-bold">
                    {node.display_name || node.node_id}
                  </div>
                  <div className="text-[11px] spu-text-muted">
                    Class:{' '}
                    <strong>
                      {node.health_classification || 'Healthy'}
                    </strong>
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
                  {node.alert_priority === 'OK'
                    ? 'NORMAL'
                    : node.alert_priority}
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
                  <div className="text-[10px] uppercase spu-text-muted">
                    Anomaly Score
                  </div>
                  <div className="font-mono text-lg font-extrabold text-[var(--accent-cyan)]">
                    {((node.anomaly_score || 0) * 100).toFixed(1)}%
                  </div>
                </div>
              </div>

              <div className="mt-3 flex items-center justify-between text-[11px]">
                <span className="spu-text-secondary">
                  Early Warning:{' '}
                  <strong className="font-mono">
                    {node.persistence_progress}
                  </strong>
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

      {/* Existing history, SHAP, model registry and playbook */}
      {activeNode && (
        <section className="grid grid-cols-1 gap-4 lg:grid-cols-12">
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
                  1h &amp; 6h predicted failure risk (%) overlaid against
                  unsupervised anomaly score &amp; observed memory %
                </p>
              </div>
              <span className="rounded-md px-2 py-1 font-mono text-[11px] spu-subcard">
                Source: {activeNode.prediction_source}
              </span>
            </div>

            <div className="h-72">
              <ResponsiveContainer width="100%" height="100%">
                <ComposedChart data={nodeSeries}>
                  <CartesianGrid
                    strokeDasharray="3 3"
                    stroke={chartTheme.grid}
                  />
                  <XAxis
                    dataKey="time"
                    tick={{ fill: chartTheme.axis, fontSize: 10 }}
                  />
                  <YAxis
                    domain={[0, 100]}
                    tick={{ fill: chartTheme.axis, fontSize: 10 }}
                    width={34}
                  />
                  <Tooltip contentStyle={chartTheme.tooltipStyle} />
                  <Legend wrapperStyle={{ fontSize: '11px' }} />
                  <ReferenceLine
                    y={40}
                    stroke={chartTheme.red}
                    strokeDasharray="4 4"
                  />
                  <ReferenceLine
                    y={18}
                    stroke={chartTheme.amber}
                    strokeDasharray="4 4"
                  />
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
                    <div
                      key={k}
                      className="rounded-lg bg-[var(--bg-card)] p-2"
                    >
                      <span className="block text-[10px] uppercase spu-text-muted">
                        {k}
                      </span>
                      <strong className="font-mono">{String(v)}</strong>
                    </div>
                  ))}
                </div>
              ) : (
                <p className="mt-2 text-xs spu-text-secondary">
                  Active Engine: <strong>{modelStatus.engine_label}</strong>.
                  Validation accuracy/AUC metrics are only displayed when
                  exported from your Phase 1 notebook
                  (<code className="font-mono">backend/models/model_metrics.json</code>
                  {' '}and .pkl files) — no synthetic accuracy figures are fabricated.
                </p>
              )}
            </div>
          </div>

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
                    <div
                      key={feat.feature}
                      className="rounded-xl p-3 spu-subcard"
                    >
                      <div className="flex items-center justify-between text-xs">
                        <span className="font-mono font-semibold">
                          {feat.feature}
                        </span>
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
                          style={{
                            width: `${Math.max(4, Math.min(100, pct))}%`,
                          }}
                        />
                      </div>

                      <div className="mt-1 text-[11px] spu-text-muted">
                        {feat.detail}
                      </div>
                    </div>
                  );
                })}
              </div>
            </div>

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
                      <Check className="h-3 w-3 text-emerald-400" />
                      Copied
                    </>
                  ) : (
                    <>
                      <Copy className="h-3 w-3" />
                      Copy
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
