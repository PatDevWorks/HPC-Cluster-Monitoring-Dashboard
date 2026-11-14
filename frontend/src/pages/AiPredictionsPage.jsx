
import React, { useEffect, useMemo, useState } from 'react';
import {
  BrainCircuit,
  BarChart3,
  Check,
  CheckCircle2,
  Copy,
  Flame,
  FlaskConical,
  Power,
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
  XCircle,
} from 'lucide-react';
import { api } from '../api.js';
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
  lstmOverride = null,
  isAdmin = false,
  busyAction = false,
  onToggleEnabled,
  onRefresh,
}) {
  const { chartTheme } = useTheme();
  const lstmStatus = lstmOverride || snapshot?.lstm_v8 || {};
  const lstmEnabled = lstmStatus.enabled !== false;
  const lstmStale = Boolean(lstmStatus.stale);
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
                  V8 LSTM 
                </h3>

                <span
                  className={`rounded-full px-2 py-1 text-[10px] font-bold uppercase ${
                    !lstmEnabled
                      ? 'bg-slate-500/20 spu-text-muted'
                      : lstmStale
                      ? 'bg-amber-500/15 text-amber-400'
                      : connected
                      ? 'bg-emerald-500/15 text-emerald-400'
                      : 'bg-rose-500/15 text-rose-400'
                  }`}
                >
                  {!lstmEnabled
                    ? 'DISABLED (CLUSTER SERVICE SEPARATE)'
                    : lstmStale
                    ? `STALE (${lstmStatus.age_seconds ?? '?'}s)`
                    : lstmStatus.status === 'not_configured'
                    ? 'NOT CONFIGURED'
                    : connected
                    ? 'API CONNECTED'
                    : 'API DISCONNECTED'}
                </span>
              </div>

             
              {lstmStatus.last_error && (
                <p className="mt-1 text-[11px] text-rose-400">
                  Last error: {lstmStatus.last_error}
                </p>
              )}
            </div>
          </div>

          <div className="flex flex-wrap items-center gap-3">
            <div className="text-right text-xs spu-text-secondary">
              <div>Last successful API update</div>
              <strong className="font-mono">
                {formatTimestamp(lstmStatus.last_success_utc)}
                {lstmStatus.age_seconds != null ? ` (${lstmStatus.age_seconds}s ago)` : ''}
              </strong>
            </div>
            {onRefresh && (
              <button
                type="button"
                disabled={busyAction || !lstmEnabled}
                onClick={onRefresh}
                className="inline-flex items-center gap-1.5 rounded-lg border spu-border px-2.5 py-1.5 text-xs font-semibold hover:border-[var(--accent-cyan)] disabled:opacity-50"
              >
                <RefreshCw className="h-3.5 w-3.5" />
                Refresh
              </button>
            )}
            {onToggleEnabled && isAdmin && (
              <button
                type="button"
                disabled={busyAction}
                onClick={() => onToggleEnabled(!lstmEnabled)}
                className={`inline-flex items-center gap-1.5 rounded-lg px-2.5 py-1.5 text-xs font-semibold transition ${
                  lstmEnabled
                    ? 'bg-rose-500/15 text-rose-300 hover:bg-rose-500/25'
                    : 'bg-emerald-500/15 text-emerald-300 hover:bg-emerald-500/25'
                }`}
              >
                <Power className="h-3.5 w-3.5" />
                {lstmEnabled ? 'Disable Polling' : 'Enable Polling'}
              </button>
            )}
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
                  Resource Forecasts - {getLstmNodeName(selectedLstmNodeId)}
                </h4>
                
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

export function unwrapModelPayload(payload, wrapperKey, prev = null) {
  if (!payload || typeof payload !== 'object') {
    return prev && typeof prev === 'object' ? prev : null;
  }
  const nestedStatus =
    payload.status && typeof payload.status === 'object' && !Array.isArray(payload.status)
      ? payload.status
      : null;
  const actionWrapped =
    wrapperKey &&
    payload[wrapperKey] &&
    typeof payload[wrapperKey] === 'object' &&
    !Array.isArray(payload[wrapperKey])
      ? payload[wrapperKey]
      : null;
  const flatStatus =
    !nestedStatus && !actionWrapped && typeof payload.status !== 'object' ? payload : null;

  const statusObj = nestedStatus || actionWrapped || flatStatus || {};
  const nextHistory =
    payload.history && typeof payload.history === 'object' && !Array.isArray(payload.history)
      ? payload.history
      : prev?.history && typeof prev.history === 'object'
      ? prev.history
      : undefined;

  const merged = {
    ...(prev && typeof prev === 'object' ? prev : {}),
    ...statusObj,
  };
  if (nextHistory !== undefined) {
    merged.history = nextHistory;
  }
  return merged;
}

function safeText(value, fallback = '') {
  if (value === null || value === undefined) return fallback;
  if (typeof value === 'string' || typeof value === 'number' || typeof value === 'boolean') {
    return String(value);
  }
  return fallback;
}

export default function AiPredictionsPage({
  snapshot,
  user,
  selectedNodeId,
  onSelectNode,
  onNavigate,
  showToast,
}) {
  const { chartTheme } = useTheme();
  const nodes = snapshot?.nodes || [];
  const isAdmin = ['admin', 'super_admin'].includes(user?.role);

  const [v7Detail, setV7Detail] = useState(null);
  const [lstmDetail, setLstmDetail] = useState(null);
  const [evaluation, setEvaluation] = useState(null);
  const [busyModel, setBusyModel] = useState('');

  const activeNode = useMemo(
    () => nodes.find((n) => n.node_id === selectedNodeId) || nodes[0] || null,
    [nodes, selectedNodeId]
  );

  const loadModelDetails = async () => {
    try {
      const [v7Res, lstmRes, evalRes] = await Promise.allSettled([
        api.getV7Scores(),
        api.getLstmV8State(),
        api.getModelsEvaluation(),
      ]);
      if (v7Res.status === 'fulfilled') {
        setV7Detail((prev) => unwrapModelPayload(v7Res.value, 'v7', prev));
      }
      if (lstmRes.status === 'fulfilled') {
        setLstmDetail((prev) => unwrapModelPayload(lstmRes.value, 'lstm_v8', prev));
      }
      if (evalRes.status === 'fulfilled' && evalRes.value && typeof evalRes.value === 'object') {
        setEvaluation(evalRes.value);
      }
    } catch {
      // Snapshot still provides baseline fields
    }
  };

  useEffect(() => {
    loadModelDetails();
    const timer = setInterval(loadModelDetails, 15000);
    return () => clearInterval(timer);
  }, []);

  const v7Meta = v7Detail || snapshot?.model_status?.v7_isolation_forest || {};
  const v7Enabled = v7Meta.enabled !== false;
  const v7NodesMap = v7Meta.nodes || {};
  const v7HistoryMap = v7Detail?.history || {};

  const lstmMeta = lstmDetail || snapshot?.lstm_v8 || snapshot?.model_status?.lstm_v8 || {};

  const activeModelNodeKey = activeNode
    ? LSTM_NODE_MAP[activeNode.node_id] || activeNode.node_id
    : 'compute001';

  const v7ChartData = useMemo(() => {
    const rawHist = v7HistoryMap[activeModelNodeKey] || [];
    return rawHist.slice(-45).map((pt) => ({
      time: pt.timestamp_utc
        ? new Date(pt.timestamp_utc).toLocaleTimeString([], { hour: '2-digit', minute: '2-digit' })
        : '',
      score: typeof pt.anomaly_score === 'number' ? Number(pt.anomaly_score.toFixed(4)) : null,
      threshold: typeof pt.threshold === 'number' ? Number(pt.threshold.toFixed(4)) : null,
    }));
  }, [v7HistoryMap, activeModelNodeKey]);

  const handleToggleV7 = async (nextEnabled) => {
    setBusyModel('v7');
    try {
      const res = await api.toggleV7Integration(nextEnabled);
      setV7Detail((prev) => unwrapModelPayload(res, 'v7', prev));
      showToast?.(
        nextEnabled
          ? 'V7 dashboard integration enabled (resuming /scores/latest polling)'
          : 'V7 dashboard integration disabled (cluster scoring service left untouched)'
      );
      await loadModelDetails();
    } catch (err) {
      showToast?.(`Failed to toggle V7 integration: ${err.message}`);
    } finally {
      setBusyModel('');
    }
  };

  const handleRefreshV7 = async () => {
    setBusyModel('v7');
    try {
      const res = await api.refreshV7Scores();
      setV7Detail((prev) => unwrapModelPayload(res, 'v7', prev));
      showToast?.('Refreshed V7 /scores/latest');
    } catch (err) {
      showToast?.(`V7 refresh error: ${err.message}`);
    } finally {
      setBusyModel('');
    }
  };

  const handleToggleLstm = async (nextEnabled) => {
    setBusyModel('lstm');
    try {
      const res = await api.toggleLstmV8Integration(nextEnabled);
      setLstmDetail((prev) => unwrapModelPayload(res, 'lstm_v8', prev));
      showToast?.(
        nextEnabled
          ? 'LSTM V8 dashboard polling enabled'
          : 'LSTM V8 dashboard polling disabled (cached results kept read-only)'
      );
      await loadModelDetails();
    } catch (err) {
      showToast?.(`Failed to toggle LSTM V8: ${err.message}`);
    } finally {
      setBusyModel('');
    }
  };

  const handleRefreshLstm = async () => {
    setBusyModel('lstm');
    try {
      const res = await api.refreshLstmV8State();
      setLstmDetail((prev) => unwrapModelPayload(res, 'lstm_v8', prev));
      showToast?.('Refreshed LSTM V8 state');
    } catch (err) {
      showToast?.(`LSTM V8 refresh error: ${err.message}`);
    } finally {
      setBusyModel('');
    }
  };

  const detectorEval = evaluation?.detector_evaluation || {};
  const runtimeBurden = evaluation?.runtime_burden || {};
  const workloadBreakdown = evaluation?.workload_breakdown || [];

  return (
    <div className="space-y-6">
      {/* Page Header */}
      <div className="flex flex-wrap items-center justify-between gap-3">
        <div className="flex items-center gap-3">
          <div className="flex h-10 w-10 items-center justify-center rounded-xl bg-cyan-500/15 text-[var(--accent-cyan)]">
            <BrainCircuit className="h-5 w-5" />
          </div>
          <div>
            <h2 className="text-xl font-bold tracking-tight">AI Model Centre</h2>
           
          </div>
        </div>

        
      </div>

      {/* Model Architecture Separation Notice */}
      <div className="spu-card flex flex-wrap items-center justify-between gap-3 p-4 text-xs spu-text-secondary">
        <div>
          
        </div>
        <div className="flex flex-wrap gap-2">
          {onNavigate && (
            <>
              <button
                type="button"
                onClick={() => onNavigate('intelligence')}
                className="inline-flex items-center gap-1.5 rounded-lg border spu-border px-2.5 py-1.5 font-semibold text-[var(--accent-cyan)] hover:bg-cyan-500/10"
              >
                <Sparkles className="h-3.5 w-3.5" />
                Ask Gemini LLM
              </button>
              <button
                type="button"
                onClick={() => onNavigate('experiments')}
                className="inline-flex items-center gap-1.5 rounded-lg border spu-border px-2.5 py-1.5 font-semibold hover:border-[var(--accent-cyan)]"
              >
                <FlaskConical className="h-3.5 w-3.5" />
                Label Experiments
              </button>
            </>
          )}
        </div>
      </div>

      {/* Section 1: V7 Isolation Forest */}
      <section className="spu-card space-y-4 p-5">
        <div className="flex flex-wrap items-center justify-between gap-3 border-b pb-3 spu-border">
          <div className="flex items-center gap-2.5">
            <ShieldAlert className="h-5 w-5 text-[var(--accent-cyan)]" />
            <div>
              <div className="flex flex-wrap items-center gap-2">
                <h3 className="text-base font-bold">V7 Isolation Forest</h3>
                <span
                  className={`rounded-full px-2 py-0.5 font-mono text-[10px] font-bold uppercase ${
                    !v7Enabled
                      ? 'bg-slate-500/20 spu-text-muted'
                      : v7Meta.stale
                      ? 'bg-amber-500/15 text-amber-400'
                      : v7Meta.connected
                      ? 'bg-emerald-500/15 text-emerald-400'
                      : 'bg-rose-500/15 text-rose-400'
                  }`}
                >
                  {!v7Enabled
                    ? 'DISABLED'
                    : v7Meta.stale
                    ? `STALE (${v7Meta.age_seconds ?? '?'}s)`
                    : safeText(v7Meta.status) || (v7Meta.connected ? 'connected' : 'not_configured')}
                </span>
              </div>
              
              {Boolean(safeText(v7Meta.last_error)) && (
                <p className="mt-1 text-[11px] text-amber-400">
                  Connection note: {safeText(v7Meta.last_error)}
                </p>
              )}
            </div>
          </div>

          <div className="flex flex-wrap items-center gap-2">
            <div className="text-right text-[11px] spu-text-secondary mr-2">
              <div>Last successful V7 pull</div>
              <strong className="font-mono">{formatTimestamp(v7Meta.last_success_utc)}</strong>
            </div>
            <button
              type="button"
              disabled={busyModel === 'v7' || !v7Enabled}
              onClick={handleRefreshV7}
              className="inline-flex items-center gap-1.5 rounded-lg border spu-border px-2.5 py-1.5 text-xs font-semibold hover:border-[var(--accent-cyan)] disabled:opacity-50"
            >
              <RefreshCw className="h-3.5 w-3.5" />
              Refresh
            </button>
            {isAdmin && (
              <button
                type="button"
                disabled={busyModel === 'v7'}
                onClick={() => handleToggleV7(!v7Enabled)}
                className={`inline-flex items-center gap-1.5 rounded-lg px-2.5 py-1.5 text-xs font-semibold transition ${
                  v7Enabled
                    ? 'bg-rose-500/15 text-rose-300 hover:bg-rose-500/25'
                    : 'bg-emerald-500/15 text-emerald-300 hover:bg-emerald-500/25'
                }`}
              >
                <Power className="h-3.5 w-3.5" />
                {v7Enabled ? 'Disable V7 Integration' : 'Enable V7 Integration'}
              </button>
            )}
          </div>
        </div>

        {!v7Enabled && (
          <div className="rounded-lg border border-amber-500/30 bg-amber-500/10 px-3 py-2 text-xs text-amber-300">
            Dashboard V7 consumption is disabled. Any displayed values are cached/stale observations only; the independent cluster-side V7 scoring runner continues undisturbed.
          </div>
        )}

        <div className="grid grid-cols-1 gap-3 sm:grid-cols-2 lg:grid-cols-4">
          {nodes.map((n) => {
            const modelKey = LSTM_NODE_MAP[n.node_id] || n.node_id;
            const liveV7 = v7NodesMap[modelKey] || n.v7_detection || {};
            const hasScore = typeof liveV7.anomaly_score === 'number';
            const isAnom = Boolean(liveV7.is_anomaly);
            return (
              <div
                key={n.node_id}
                onClick={() => onSelectNode?.(n.node_id)}
                className={`cursor-pointer rounded-xl p-3.5 transition spu-subcard ${
                  activeNode?.node_id === n.node_id ? 'border-[var(--accent-cyan)]' : ''
                }`}
              >
                <div className="flex items-center justify-between">
                  <span className="text-sm font-bold">{n.display_name || n.node_id}</span>
                  <span
                    className={`rounded px-2 py-0.5 font-mono text-[10px] font-bold uppercase ${
                      isAnom
                        ? 'bg-amber-500/20 text-amber-400'
                        : hasScore
                        ? 'bg-emerald-500/15 text-emerald-400'
                        : 'bg-slate-500/15 spu-text-muted'
                    }`}
                  >
                    {hasScore ? (safeText(liveV7.classification) || (isAnom ? 'ANOMALY' : 'NORMAL')) : safeText(liveV7.status, 'pending')}
                  </span>
                </div>
                <div className="mt-2 space-y-1 font-mono text-xs spu-text-secondary">
                  <div>
                    Score: <strong className="text-[var(--text-primary)]">{hasScore ? liveV7.anomaly_score.toFixed(4) : '--'}</strong> | Thr:{' '}
                    <strong>{typeof liveV7.threshold === 'number' ? liveV7.threshold.toFixed(4) : '--'}</strong>
                  </div>
                  <div className="text-[10px] spu-text-muted">
                    Model: {liveV7.model_version || v7Meta.model_version || 'v7'} · {liveV7.feature_count || v7Meta.feature_count || 28}f
                  </div>
                  <div className="text-[10px] spu-text-muted truncate">
                    Updated: {formatTimestamp(liveV7.timestamp_utc)}
                  </div>
                </div>
              </div>
            );
          })}
        </div>

        {/* V7 Score Trend Chart for Selected Node */}
        {v7ChartData.length > 0 && (
          <div className="spu-subcard p-4">
            <div className="mb-2 flex items-center justify-between text-xs">
              <span className="font-semibold">
                V7 Score vs Node Threshold — {activeNode?.display_name || activeModelNodeKey}
              </span>
              <span className="font-mono spu-text-muted">{v7ChartData.length} buffered observations</span>
            </div>
            <div className="h-44 w-full">
              <ResponsiveContainer width="100%" height="100%">
                <ComposedChart data={v7ChartData}>
                  <CartesianGrid stroke={chartTheme.grid} strokeDasharray="3 3" />
                  <XAxis dataKey="time" tick={{ fill: chartTheme.axis, fontSize: 10 }} />
                  <YAxis tick={{ fill: chartTheme.axis, fontSize: 10 }} domain={['auto', 'auto']} />
                  <Tooltip contentStyle={chartTheme.tooltipStyle} />
                  <Legend wrapperStyle={{ fontSize: '11px' }} />
                  <Line type="monotone" dataKey="score" name="Anomaly Score" stroke="#22d3ee" dot={false} strokeWidth={2} />
                  <Line type="monotone" dataKey="threshold" name="Node Threshold" stroke="#f59e0b" dot={false} strokeDasharray="4 4" />
                </ComposedChart>
              </ResponsiveContainer>
            </div>
          </div>
        )}

       
      </section>

      {/* Section 2: Real Cluster LSTM V8 Service */}
      {lstmMeta.enabled === false && (
        <div className="rounded-lg border border-amber-500/30 bg-amber-500/10 px-4 py-2.5 text-xs text-amber-300">
          LSTM V8 polling is disabled in the dashboard. Any forecasts or warnings shown below represent cached historical state and will not raise new alerts until re-enabled.
        </div>
      )}
      <LSTMV8Section
        snapshot={snapshot}
        selectedNodeId={activeNode?.node_id}
        onSelectNode={onSelectNode}
        lstmOverride={lstmDetail}
        isAdmin={isAdmin}
        busyAction={busyModel === 'lstm'}
        onToggleEnabled={handleToggleLstm}
        onRefresh={handleRefreshLstm}
      />

      {/* Section 3: Model Comparison & Evaluation */}
      <section className="spu-card space-y-4 p-5">
        <div className="flex flex-wrap items-center justify-between gap-3 border-b pb-3 spu-border">
          <div className="flex items-center gap-2.5">
            <BarChart3 className="h-5 w-5 text-[var(--accent-cyan)]" />
            <div>
              <h3 className="text-base font-bold">Model Comparison & Evaluation</h3>
              
            </div>
          </div>
          {onNavigate && (
            <button
              type="button"
              onClick={() => onNavigate('experiments')}
              className="inline-flex items-center gap-1.5 rounded-lg bg-cyan-500/15 px-3 py-1.5 text-xs font-semibold text-[var(--accent-cyan)] hover:bg-cyan-500/25"
            >
              <FlaskConical className="h-3.5 w-3.5" />
              Open Experiments & Evaluation
            </button>
          )}
        </div>

        

        {/* Detector Scorecard Table */}
        <div className="overflow-x-auto">
          <table className="w-full text-left text-xs">
            <thead>
              <tr className="border-b spu-border spu-text-muted font-mono uppercase text-[10px]">
                <th className="py-2 pr-3">Detector</th>
                <th className="py-2 px-3">Detection Coverage</th>
                <th className="py-2 px-3">Detected / Missed</th>
                <th className="py-2 px-3">Mean Lead/Delay</th>
                <th className="py-2 px-3">False Positive Rate</th>
                <th className="py-2 px-3">Event F1</th>
                <th className="py-2 pl-3">Alert Burden (Unlabelled Count)</th>
              </tr>
            </thead>
            <tbody className="divide-y spu-border font-mono">
              {[
                { key: 'v7', label: 'V7 Isolation Forest' },
                { key: 'lstm_v8', label: 'LSTM V8 Forecaster' },
                { key: 'telemetry', label: 'Telemetry Threshold Baseline' },
              ].map(({ key, label }) => {
                const st = detectorEval[key] || {};
                const burden = runtimeBurden[key] || {};
                return (
                  <tr key={key}>
                    <td className="py-2.5 pr-3 font-sans font-semibold text-[var(--text-primary)]">{label}</td>
                    <td className="py-2.5 px-3">
                      {st.detection_coverage_pct != null ? `${st.detection_coverage_pct}%` : 'Needs labelled faults'}
                    </td>
                    <td className="py-2.5 px-3">
                      {st.positive_events > 0 ? `${st.detected_events} hit / ${st.missed_events} missed` : '--'}
                    </td>
                    <td className="py-2.5 px-3">
                      {st.mean_detection_delay_min != null ? `${st.mean_detection_delay_min} min` : '--'}
                    </td>
                    <td className="py-2.5 px-3">
                      {st.false_positive_rate_pct != null ? `${st.false_positive_rate_pct}% (${st.false_positive_windows}/${st.benign_windows})` : 'Needs benign windows'}
                    </td>
                    <td className="py-2.5 px-3">
                      {st.event_f1 != null ? st.event_f1 : '--'}
                    </td>
                    <td className="py-2.5 pl-3 spu-text-secondary">
                      {burden.total_episodes ?? 0} episodes ({burden.open_episodes ?? 0} open)
                    </td>
                  </tr>
                );
              })}
            </tbody>
          </table>
        </div>

        {workloadBreakdown.length > 0 && (
          <div className="spu-subcard p-3">
            <div className="mb-2 text-xs font-semibold">Performance by Workload Condition</div>
            <div className="grid grid-cols-1 gap-2 md:grid-cols-3 text-xs font-mono">
              {workloadBreakdown.map((wb) => (
                <div key={wb.workload_condition} className="rounded border spu-border p-2.5">
                  <div className="font-sans font-bold uppercase text-[11px]">{wb.workload_condition}</div>
                  <div className="mt-1 spu-text-secondary">
                    Faults: {wb.positive_events} · Benign: {wb.benign_windows}
                  </div>
                  <div className="mt-1">
                    Hits — V7: {wb.v7_detected} | LSTM: {wb.lstm_v8_detected} | Thresh: {wb.telemetry_detected}
                  </div>
                </div>
              ))}
            </div>
          </div>
        )}
      </section>
    </div>
  );
}
