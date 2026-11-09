import React, { useEffect, useState } from 'react';
import {
  CheckCircle2,
  Cpu,
  Monitor,
  Moon,
  Radio,
  RefreshCw,
  Save,
  Server,
  Settings,
  ShieldCheck,
  Sun,
  XCircle,
} from 'lucide-react';
import { api } from '../api.js';
import { useTheme } from '../context/ThemeContext.jsx';

export default function SettingsPage({
  snapshot,
  wsConnected,
  onSwitchMode,
  onReloadModels,
  showToast,
}) {
  const { preference, setPreference } = useTheme();
  const [settingsData, setSettingsData] = useState(null);
  const [promUrl, setPromUrl] = useState('http://localhost:9090');
  const [grafanaUrl, setGrafanaUrl] = useState('http://localhost:3000');
  const [refreshSec, setRefreshSec] = useState(3.0);
  const [sshHost, setSshHost] = useState('');
  const [sshUser, setSshUser] = useState('ubuntu');
  const [sshPort, setSshPort] = useState(22);
  const [policy, setPolicy] = useState({
    p1_critical_prob: 0.4,
    p2_warning_prob: 0.18,
    p3_watch_prob: 0.015,
    scratch_critical_percent: 90,
    memory_warning_percent: 88,
    memory_critical_percent: 95,
    temp_warning_celsius: 78,
    temp_critical_celsius: 86,
    cooldown_minutes: 30,
  });
  const [promProbeResult, setPromProbeResult] = useState(null);
  const [saving, setSaving] = useState(false);

  const loadSettings = async () => {
    try {
      const res = await api.getSettings();
      setSettingsData(res);
      const s = res.settings || {};
      if (s.prometheus_url) setPromUrl(s.prometheus_url);
      if (s.grafana_url) setGrafanaUrl(s.grafana_url);
      if (s.refresh_interval_sec) setRefreshSec(Number(s.refresh_interval_sec));
      if (s.ssh_host !== undefined) setSshHost(s.ssh_host);
      if (s.ssh_user) setSshUser(s.ssh_user);
      if (s.ssh_port) setSshPort(Number(s.ssh_port));
      if (s.alert_policy) setPolicy((prev) => ({ ...prev, ...s.alert_policy }));
    } catch (err) {
      showToast(`Failed to load settings: ${err.message}`);
    }
  };

  useEffect(() => {
    loadSettings();
  }, []);

  const handleTestProm = async () => {
    try {
      const res = await api.testPrometheus(promUrl);
      setPromProbeResult(res);
      showToast(
        res.reachable
          ? `Prometheus reachable (${res.targets_count} target series discovered)`
          : `Prometheus unreachable: ${res.error}`
      );
    } catch (err) {
      showToast(`Probe error: ${err.message}`);
    }
  };

  const handleSave = async (e) => {
    e.preventDefault();
    setSaving(true);
    try {
      await api.updateSettings({
        prometheus_url: promUrl,
        grafana_url: grafanaUrl,
        refresh_interval_sec: Number(refreshSec),
        ssh_host: sshHost,
        ssh_user: sshUser,
        ssh_port: Number(sshPort),
        alert_policy: policy,
      });
      await loadSettings();
      showToast('Platform settings saved and applied');
    } catch (err) {
      showToast(`Save failed: ${err.message}`);
    } finally {
      setSaving(false);
    }
  };

  const health = settingsData?.service_health || {};
  const appInfo = settingsData?.app_info || {};
  const modelStatus = snapshot?.model_status || {};
  const presets = snapshot?.replay_presets || [];

  return (
    <div className="space-y-5">
      {/* Header */}
      <div className="flex items-center gap-3">
        <div className="flex h-10 w-10 items-center justify-center rounded-xl bg-cyan-500/15 text-[var(--accent-cyan)]">
          <Settings className="h-5 w-5" />
        </div>
        <div>
          <h2 className="text-xl font-bold tracking-tight">Settings</h2>
          <p className="text-xs spu-text-secondary">
            Infrastructure endpoints, refresh intervals, AI registry, alert thresholds &amp; service health
          </p>
        </div>
      </div>

      {/* 1. Service & Backend Connection Health Matrix */}
      <section className="spu-card p-5">
        <h3 className="mb-3 text-sm font-bold">Backend &amp; Infrastructure Service Health</h3>
        <div className="grid grid-cols-1 gap-3 sm:grid-cols-2 lg:grid-cols-5 text-xs">
          {[
            {
              name: 'FastAPI Backend',
              ok: health.backend_api === 'online',
              detail: 'REST + SQLite Active',
            },
            {
              name: 'WebSocket Stream',
              ok: wsConnected,
              detail: `${refreshSec}s cadence`,
            },
            {
              name: 'Prometheus (:9090)',
              ok: Boolean(health.prometheus?.reachable),
              detail: health.prometheus?.reachable
                ? `${health.prometheus.targets_count} series`
                : 'Offline / Tunnel closed',
            },
            {
              name: 'SSH / Linux Bridge',
              ok: Boolean(
                health.ssh_bridge?.local_linux_execution ||
                  health.ssh_bridge?.ssh_gateway_configured
              ),
              detail: health.ssh_bridge?.local_linux_execution
                ? 'Local Linux Head Node'
                : health.ssh_bridge?.ssh_host || 'Not configured',
            },
            {
              name: 'ML Model Engine',
              ok: true,
              detail: modelStatus.engine_label || 'Active',
            },
          ].map((svc) => (
            <div key={svc.name} className="spu-subcard p-3 flex items-start justify-between">
              <div>
                <div className="font-bold">{svc.name}</div>
                <div className="mt-1 text-[11px] spu-text-muted">{svc.detail}</div>
              </div>
              {svc.ok ? (
                <CheckCircle2 className="h-4 w-4 text-emerald-400 shrink-0" />
              ) : (
                <XCircle className="h-4 w-4 text-amber-400 shrink-0" />
              )}
            </div>
          ))}
        </div>
      </section>

      {/* 2. Telemetry Pipeline Mode + Theme Preferences */}
      <section className="grid grid-cols-1 gap-4 lg:grid-cols-2">
        <div className="spu-card p-5 space-y-3">
          <div className="flex items-center gap-2 text-sm font-bold">
            <Radio className="h-4 w-4 text-[var(--accent-cyan)]" />
            Active Telemetry Data Source
          </div>
          <p className="text-xs spu-text-secondary">
            Switch between live Prometheus scraping on your cluster, the 4-node telemetry simulator, or chronological SCC dataset replay.
          </p>
          <div className="flex flex-wrap gap-2">
            {[
              { id: 'live_prometheus', label: 'Live Prometheus (:9090)' },
              { id: 'live_cluster_sim', label: '4-Node Cluster Simulator' },
              { id: 'scc_dataset_replay', label: '12-Node SCC Dataset Replay' },
            ].map((m) => (
              <button
                key={m.id}
                onClick={() => onSwitchMode(m.id, promUrl, snapshot?.preset_id)}
                className={`rounded-lg px-3 py-2 text-xs font-semibold transition ${
                  snapshot?.mode === m.id
                    ? 'bg-[var(--accent-cyan-strong)] text-white'
                    : 'spu-btn-secondary'
                }`}
              >
                {m.label}
              </button>
            ))}
          </div>

          {snapshot?.mode === 'scc_dataset_replay' && presets.length > 0 && (
            <div className="pt-2">
              <label className="block text-xs font-semibold mb-1">Replay Scenario Window</label>
              <select
                value={snapshot?.preset_id || 'sep03_mem_disk'}
                onChange={(e) =>
                  onSwitchMode('scc_dataset_replay', null, e.target.value)
                }
                className="spu-input w-full"
              >
                {presets.map((p) => (
                  <option key={p.id} value={p.id}>
                    {p.label}
                  </option>
                ))}
              </select>
            </div>
          )}
        </div>

        {/* Appearance & Theme */}
        <div className="spu-card p-5 space-y-3">
          <div className="text-sm font-bold">Global Theme Preference</div>
          <p className="text-xs spu-text-secondary">
            Switch instantaneously across all charts, tables, modals and log viewers. Preference is saved persistently.
          </p>
          <div className="grid grid-cols-3 gap-2.5 pt-1">
            {[
              { id: 'dark', label: 'Dark Mode', icon: Moon },
              { id: 'light', label: 'Light Mode', icon: Sun },
              { id: 'system', label: 'System Default', icon: Monitor },
            ].map((t) => {
              const Icon = t.icon;
              const active = preference === t.id;
              return (
                <button
                  key={t.id}
                  onClick={() => setPreference(t.id)}
                  className={`flex flex-col items-center gap-2 rounded-xl border p-3 text-xs font-semibold transition ${
                    active
                      ? 'border-[var(--accent-cyan)] bg-cyan-500/12 text-[var(--accent-cyan)]'
                      : 'spu-subcard spu-text-secondary hover:text-[var(--text-primary)]'
                  }`}
                >
                  <Icon className="h-4 w-4" />
                  {t.label}
                </button>
              );
            })}
          </div>
        </div>
      </section>

      {/* 3. Main Configuration Form (Prometheus, Refresh, SSH Gateway, Thresholds) */}
      <form onSubmit={handleSave} className="spu-card p-5 space-y-5">
        <div className="flex items-center justify-between border-b pb-3 spu-border">
          <h3 className="text-sm font-bold">
            Connection Endpoints, Polling Cadence &amp; Alert Thresholds
          </h3>
          <button
            type="submit"
            disabled={saving}
            className="spu-btn-primary inline-flex items-center gap-1.5"
          >
            <Save className="h-3.5 w-3.5" />
            {saving ? 'Saving...' : 'Save Configuration'}
          </button>
        </div>

        <div className="grid grid-cols-1 gap-4 md:grid-cols-3 text-xs">
          <div>
            <label className="block font-semibold mb-1">Prometheus Server URL</label>
            <div className="flex gap-2">
              <input
                type="text"
                value={promUrl}
                onChange={(e) => setPromUrl(e.target.value)}
                className="spu-input flex-1 font-mono"
              />
              <button
                type="button"
                onClick={handleTestProm}
                className="spu-btn-secondary shrink-0"
              >
                Test
              </button>
            </div>
            {promProbeResult && (
              <p
                className={`mt-1 text-[11px] ${
                  promProbeResult.reachable ? 'text-emerald-400' : 'text-rose-400'
                }`}
              >
                {promProbeResult.reachable
                  ? `Connected (${promProbeResult.targets_count} target series)`
                  : promProbeResult.error}
              </p>
            )}
          </div>

          <div>
            <label className="block font-semibold mb-1">Grafana External URL</label>
            <input
              type="text"
              value={grafanaUrl}
              onChange={(e) => setGrafanaUrl(e.target.value)}
              className="spu-input w-full font-mono"
            />
          </div>

          <div>
            <label className="block font-semibold mb-1">
              Monitoring Refresh Interval (Seconds)
            </label>
            <select
              value={refreshSec}
              onChange={(e) => setRefreshSec(Number(e.target.value))}
              className="spu-input w-full"
            >
              <option value={1.5}>1.5s (Fast Lab View)</option>
              <option value={3}>3.0s (Recommended Balanced)</option>
              <option value={5}>5.0s (Low Overhead)</option>
              <option value={10}>10.0s (Minimal Polling)</option>
              <option value={30}>30.0s (Archival Cadence)</option>
            </select>
          </div>
        </div>

        {/* Non-sensitive SSH Head Node Gateway (For Remote Log & Slurm Queries) */}
        <div className="border-t pt-4 spu-border">
          <div className="flex items-center gap-2 text-xs font-bold mb-1">
            <ShieldCheck className="h-4 w-4 text-emerald-400" />
            Head Node SSH Gateway (Backend-Only Key Auth — Zero Keys Stored in Browser)
          </div>
          <p className="text-[11px] spu-text-secondary mb-3">
            Optional when running on a remote laptop: enter Head Node IP/hostname so the backend can run allowlisted <code className="font-mono">journalctl</code> and <code className="font-mono">squeue/scontrol</code> commands using your local OS SSH key. Leave blank if deployed directly on the Linux Head Node.
          </p>
          <div className="grid grid-cols-1 gap-3 sm:grid-cols-3 text-xs">
            <div>
              <label className="block font-semibold mb-1">Head Node Host / IP</label>
              <input
                type="text"
                value={sshHost}
                onChange={(e) => setSshHost(e.target.value)}
                placeholder="e.g. 196.24.241.73"
                className="spu-input w-full font-mono"
              />
            </div>
            <div>
              <label className="block font-semibold mb-1">SSH Username</label>
              <input
                type="text"
                value={sshUser}
                onChange={(e) => setSshUser(e.target.value)}
                className="spu-input w-full font-mono"
              />
            </div>
            <div>
              <label className="block font-semibold mb-1">SSH Port</label>
              <input
                type="number"
                value={sshPort}
                onChange={(e) => setSshPort(Number(e.target.value))}
                className="spu-input w-full font-mono"
              />
            </div>
          </div>
        </div>

        {/* Alert Thresholds */}
        <div className="border-t pt-4 spu-border">
          <div className="text-xs font-bold mb-3">Alert &amp; AI Risk Threshold Policy</div>
          <div className="grid grid-cols-2 gap-3 sm:grid-cols-4 text-xs">
            {[
              ['p1_critical_prob', 'P1 Failure Prob (0–1)', 0.01],
              ['p2_warning_prob', 'P2 Failure Prob (0–1)', 0.01],
              ['p3_watch_prob', 'P3 Watch Prob (0–1)', 0.005],
              ['scratch_critical_percent', '/scratch Critical (%)', 1],
              ['memory_warning_percent', 'Memory Warning (%)', 1],
              ['memory_critical_percent', 'Memory Critical (%)', 1],
              ['temp_warning_celsius', 'Temp Warning (°C)', 1],
              ['cooldown_minutes', 'Alert Cooldown (min)', 5],
            ].map(([key, label, step]) => (
              <div key={key}>
                <label className="block spu-text-secondary mb-1">{label}</label>
                <input
                  type="number"
                  step={step}
                  value={policy[key] ?? ''}
                  onChange={(e) =>
                    setPolicy((prev) => ({ ...prev, [key]: Number(e.target.value) }))
                  }
                  className="spu-input w-full font-mono"
                />
              </div>
            ))}
          </div>
        </div>
      </form>

      {/* 4. Discovered Nodes & AI Model Slot Inventory */}
      <section className="grid grid-cols-1 gap-4 lg:grid-cols-2">
        <div className="spu-card p-5">
          <div className="flex items-center gap-2 text-sm font-bold mb-3">
            <Server className="h-4 w-4 text-[var(--accent-cyan)]" />
            Discovered Cluster Nodes
          </div>
          <div className="space-y-2 text-xs">
            {(snapshot?.nodes || []).map((n) => (
              <div
                key={n.node_id}
                className="flex items-center justify-between rounded-lg px-3 py-2 spu-subcard"
              >
                <div>
                  <span className="font-bold">{n.display_name || n.node_id}</span>{' '}
                  <span className="spu-text-muted">({n.role})</span>
                </div>
                <span className="font-mono spu-text-secondary">
                  {n.instance} • {n.cpu_cores}c / {n.memory_gib}G
                </span>
              </div>
            ))}
          </div>
        </div>

        <div className="spu-card p-5 flex flex-col justify-between">
          <div>
            <div className="flex items-center justify-between mb-3">
              <div className="flex items-center gap-2 text-sm font-bold">
                <Cpu className="h-4 w-4 text-[var(--accent-cyan)]" />
                AI Model Registry (<code className="font-mono text-xs">backend/models/</code>)
              </div>
              <button
                onClick={onReloadModels}
                className="spu-btn-secondary inline-flex items-center gap-1.5"
              >
                <RefreshCw className="h-3.5 w-3.5" /> Reload .pkl
              </button>
            </div>

            <div className="grid grid-cols-2 gap-2 text-xs">
              {Object.entries(modelStatus.detectors || {}).map(([name, st]) => (
                <div
                  key={name}
                  className="flex items-center justify-between rounded-lg px-2.5 py-2 spu-subcard"
                >
                  <span className="font-mono text-[11px]">{name}</span>
                  <span
                    className={`rounded px-1.5 py-0.5 text-[10px] font-bold uppercase ${
                      st === 'pkl'
                        ? 'bg-emerald-500/20 text-emerald-400'
                        : 'bg-amber-500/15 text-amber-400'
                    }`}
                  >
                    {st}
                  </span>
                </div>
              ))}
            </div>
          </div>

          <div className="mt-4 border-t pt-3 spu-border text-[11px] spu-text-muted">
            {appInfo.name} v{appInfo.version} • {appInfo.organization}
          </div>
        </div>
      </section>
    </div>
  );
}
