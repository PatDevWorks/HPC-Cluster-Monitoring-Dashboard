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
  Database, Download, Mail, Sparkles, Terminal,
} from 'lucide-react';
import { api } from '../api.js';
import { useTheme } from '../context/ThemeContext.jsx';

export default function SettingsPage({
  snapshot,
  wsConnected,
  onSwitchMode,
  showToast,
  user,
}) {
  const { preference, setPreference } = useTheme();
  const [settingsData, setSettingsData] = useState(null);
  const [promUrl, setPromUrl] = useState('http://localhost:9090');
  const [grafanaUrl, setGrafanaUrl] = useState('http://localhost:3000');
  const [refreshSec, setRefreshSec] = useState(3.0);
  const [sshHost, setSshHost] = useState('');
  const [sshUser, setSshUser] = useState('ubuntu');
  const [sshPort, setSshPort] = useState(22);
  const [v7Enabled, setV7Enabled] = useState(true);
  const [lstmEnabled, setLstmEnabled] = useState(true);
  const [restrictedTerminalEnabled, setRestrictedTerminalEnabled] = useState(false);
  const [emailAlertsEnabled, setEmailAlertsEnabled] = useState(false);
  const [alertRecipients, setAlertRecipients] = useState('');
  const [geminiProbeResult, setGeminiProbeResult] = useState(null);
  const isSuperAdmin = user?.role === 'super_admin';
  const [policy, setPolicy] = useState({
    cpu_warning_percent: 95,
    iowait_warning_percent: 35,
    memory_warning_percent: 88,
    memory_critical_percent: 95,
    scratch_critical_percent: 90,
    root_critical_percent: 90,
    normalized_load_warning: 1.25,
    net_error_warning_per_sec: 1.0,
    mpi_straggler_warning: 0.45,
    persistence_ticks: 2,
    cooldown_minutes: 30,
    stale_telemetry_seconds: 120,
    enable_v7_alerts: true,
    enable_lstm_alerts: true,
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
      if (s.v7_enabled !== undefined) setV7Enabled(Boolean(s.v7_enabled));
      if (s.lstm_v8_enabled !== undefined) setLstmEnabled(Boolean(s.lstm_v8_enabled));
      if (s.restricted_terminal_enabled !== undefined) {
        setRestrictedTerminalEnabled(Boolean(s.restricted_terminal_enabled));
      }
      if (s.email_alerts_enabled !== undefined) {
        setEmailAlertsEnabled(Boolean(s.email_alerts_enabled));
      }
      if (s.alert_recipient_emails !== undefined) {
        setAlertRecipients(s.alert_recipient_emails || '');
      }
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

  const handleTestGemini = async () => {
    try {
      const res = await api.testGeminiConnection();
      setGeminiProbeResult(res);
      showToast(
        res.ok
          ? `Gemini connected (${res.model})`
          : `Gemini probe failed: ${res.error || 'unconfigured'}`
      );
    } catch (err) {
      setGeminiProbeResult({ ok: false, error: err.message });
      showToast(`Gemini test error: ${err.message}`);
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
        v7_enabled: v7Enabled,
        lstm_v8_enabled: lstmEnabled,
        restricted_terminal_enabled: restrictedTerminalEnabled,
        email_alerts_enabled: emailAlertsEnabled,
        alert_recipient_emails: alertRecipients.trim(),
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
              name: 'V7 Isolation Forest',
              ok: modelStatus.v7_isolation_forest?.status === 'ready' || modelStatus.v7_isolation_forest?.status === 'connected',
              detail: modelStatus.v7_isolation_forest?.status || 'pending',
            },
            {
              name: 'LSTM V8 Forecaster',
              ok: modelStatus.lstm_v8?.status === 'connected',
              detail: modelStatus.lstm_v8?.status || 'connecting',
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
          <div className="text-xs font-bold mb-1">Telemetry &amp; Operational Alert Policy</div>
          <p className="mb-3 text-[11px] spu-text-muted">
            Hardware sensors (CPU temperature, fan speed, power/energy) are not exposed by cluster hwmon interfaces and are omitted.
          </p>
          <div className="grid grid-cols-2 gap-3 sm:grid-cols-4 text-xs">
            {[
              ['cpu_warning_percent', 'CPU Warning (%)', 1],
              ['iowait_warning_percent', 'I/O Wait Warning (%)', 1],
              ['memory_warning_percent', 'Memory Warning (%)', 1],
              ['memory_critical_percent', 'Memory Critical (%)', 1],
              ['scratch_critical_percent', '/scratch Critical (%)', 1],
              ['root_critical_percent', 'Root / Critical (%)', 1],
              ['normalized_load_warning', 'Norm Load Warning (x)', 0.05],
              ['net_error_warning_per_sec', 'Net Errors Warning (/s)', 0.1],
              ['mpi_straggler_warning', 'MPI Asymmetry Thr', 0.05],
              ['persistence_ticks', 'Persistence (ticks)', 1],
              ['cooldown_minutes', 'Alert Cooldown (min)', 5],
              ['stale_telemetry_seconds', 'Stale Threshold (sec)', 10],
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

          <div className="mt-4 flex flex-wrap gap-4 text-xs">
            <label className="inline-flex items-center gap-2 cursor-pointer">
              <input
                type="checkbox"
                checked={v7Enabled}
                onChange={(e) => setV7Enabled(e.target.checked)}
              />
              <span>Enable V7 Isolation Forest dashboard integration</span>
            </label>
            <label className="inline-flex items-center gap-2 cursor-pointer">
              <input
                type="checkbox"
                checked={lstmEnabled}
                onChange={(e) => setLstmEnabled(e.target.checked)}
              />
              <span>Enable LSTM V8 dashboard integration &amp; polling</span>
            </label>
            <label className="inline-flex items-center gap-2 cursor-pointer">
              <input
                type="checkbox"
                checked={restrictedTerminalEnabled}
                onChange={(e) => setRestrictedTerminalEnabled(e.target.checked)}
              />
              <span>Enable Restricted Operations Terminal</span>
            </label>
            <label className="inline-flex items-center gap-2 cursor-pointer">
              <input
                type="checkbox"
                checked={emailAlertsEnabled}
                onChange={(e) => setEmailAlertsEnabled(e.target.checked)}
              />
              <span>Email Admins on P1 Critical Incidents</span>
            </label>
          </div>

          <div className="mt-3 text-xs">
            <label className="block font-semibold mb-1">
              Incident Notification Recipient Emails (comma-separated, backend Brevo delivery)
            </label>
            <input
              type="text"
              value={alertRecipients}
              onChange={(e) => setAlertRecipients(e.target.value)}
              placeholder="ops@cluster.local, admin@institution.edu"
              className="spu-input w-full md:w-2/3 font-mono"
            />
          </div>
        </div>
      </form>

      {/* 4. Discovered Nodes & AI Model Integrations */}
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
                Model &amp; LLM Integrations
              </div>
              <span className="text-[11px] font-mono spu-text-muted">
                Kept Strictly Separate
              </span>
            </div>

            <div className="space-y-2 text-xs">
              <div className="flex items-center justify-between rounded-lg px-3 py-2.5 spu-subcard">
                <div>
                  <div className="font-bold">V7 Isolation Forest</div>
                  <div className="text-[11px] spu-text-muted">
                    28-feature global IF • per-node thresholds • cluster-side scorer
                  </div>
                </div>
                <span className="rounded px-2 py-0.5 font-mono text-[10px] font-bold uppercase bg-cyan-500/15 text-[var(--accent-cyan)]">
                  {modelStatus.v7_isolation_forest?.status || 'pending'}
                </span>
              </div>
              <div className="flex items-center justify-between rounded-lg px-3 py-2.5 spu-subcard">
                <div>
                  <div className="font-bold">LSTM V8 Temporal Forecaster</div>
                  <div className="text-[11px] spu-text-muted">
                    8-feature per-node 60m lookback • 1/15/30/60m forecasts
                  </div>
                </div>
                <span className="rounded px-2 py-0.5 font-mono text-[10px] font-bold uppercase bg-cyan-500/15 text-[var(--accent-cyan)]">
                  {modelStatus.lstm_v8?.status || 'connecting'}
                </span>
              </div>
              <div className="flex flex-wrap items-center justify-between gap-2 rounded-lg px-3 py-2.5 spu-subcard">
                <div>
                  <div className="font-bold">Gemini LLM Intelligence</div>
                  <div className="text-[11px] spu-text-muted">
                    Evidence interpretation &amp; reporting ({health.gemini?.model || 'unconfigured'})
                  </div>
                  {geminiProbeResult && (
                    <div
                      className={`mt-1 text-[11px] font-mono ${
                        geminiProbeResult.ok ? 'text-emerald-400' : 'text-rose-400'
                      }`}
                    >
                      {geminiProbeResult.ok
                        ? `Verified: ${geminiProbeResult.reply || 'OK'}`
                        : geminiProbeResult.error}
                    </div>
                  )}
                </div>
                <div className="flex items-center gap-2">
                  <button
                    type="button"
                    onClick={handleTestGemini}
                    className="spu-btn-secondary py-1 px-2 text-[11px]"
                  >
                    Test Connection
                  </button>
                  <span className="rounded px-2 py-0.5 font-mono text-[10px] font-bold uppercase bg-cyan-500/15 text-[var(--accent-cyan)]">
                    {health.gemini?.configured ? 'configured' : 'not_configured'}
                  </span>
                </div>
              </div>
            </div>

            {/* Backup & Restore Downloads */}
            <div className="mt-4 border-t pt-3 spu-border">
              <div className="flex items-center gap-1.5 text-xs font-bold mb-2">
                <Database className="h-3.5 w-3.5 text-[var(--accent-cyan)]" />
                Configuration &amp; SQLite Backups
              </div>
              <div className="flex flex-wrap gap-2">
                <a
                  href={api.getSettingsBackupUrl()}
                  className="spu-btn-secondary inline-flex items-center gap-1.5 text-xs"
                >
                  <Download className="h-3.5 w-3.5" />
                  Export Settings &amp; Experiments (.json)
                </a>
                {isSuperAdmin && (
                  <a
                    href={api.getDatabaseBackupUrl()}
                    className="spu-btn-secondary inline-flex items-center gap-1.5 text-xs"
                  >
                    <Download className="h-3.5 w-3.5 text-amber-400" />
                    Download Full SQLite DB (.db)
                  </a>
                )}
              </div>
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
