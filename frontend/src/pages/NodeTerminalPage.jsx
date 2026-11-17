import React, { useEffect, useMemo, useRef, useState } from 'react';
import {
  Check,
  Copy,
  Download,
  ExternalLink,
  Play,
  Server,
  Settings,
  ShieldAlert,
  ShieldCheck,
  Terminal,
  Trash2,
  Lock, History,
} from 'lucide-react';
import { api } from '../api.js';
import ConfirmModal from '../components/ConfirmModal.jsx';

export default function NodeTerminalPage({
  snapshot,
  selectedNodeId,
  onSelectNode,
  onNavigate,
  showToast,
}) {
  const nodes = snapshot?.nodes || [];
  const activeNode = useMemo(
    () => nodes.find((n) => n.node_id === selectedNodeId) || nodes[0] || null,
    [nodes, selectedNodeId]
  );
  const activeNodeId = activeNode?.node_id || 'head-node';

  const [presetGroups, setPresetGroups] = useState([]);
  const [sessions, setSessions] = useState({});
  const [cmdInput, setCmdInput] = useState('');
  const [cmdHistory, setCmdHistory] = useState([
    'status',
    'uptime',
    'free -h',
    'df -h',
    'sinfo',
    'squeue',
  ]);
  const [historyIdx, setHistoryIdx] = useState(-1);
  const [running, setRunning] = useState(false);
  const [copiedSsh, setCopiedSsh] = useState(false);
  const [pendingConfirm, setPendingConfirm] = useState(null);

  const viewportRef = useRef(null);
  const inputRef = useRef(null);

  useEffect(() => {
    api
      .getTerminalPresets()
      .then((res) => {
        if (res?.preset_groups) setPresetGroups(res.preset_groups);
      })
      .catch(() => {});
  }, []);

  // Initialize welcome banner per instance session
  useEffect(() => {
    if (!activeNode) return;
    setSessions((prev) => {
      if (prev[activeNode.node_id]) return prev;
      const nowTime = new Date().toISOString().slice(11, 19);
      return {
        ...prev,
        [activeNode.node_id]: [
          {
            id: `init-${activeNode.node_id}`,
            type: 'banner',
            timestamp: nowTime,
            output:
              `HPC Predictive Monitoring Dashboard — Instance Console (${activeNode.display_name || activeNode.node_id})\n` +
              `Host IP: ${activeNode.ip} | Role: ${activeNode.role} | Slurm: ${activeNode.slurm_state} | Status: ${activeNode.health_classification || activeNode.health_status || 'Healthy'}\n` +
              `Type 'help' to list permitted diagnostic commands, 'status' for live telemetry, or select a Quick Command.`,
          },
        ],
      };
    });
  }, [activeNode]);

  const activeEntries = sessions[activeNodeId] || [];

  useEffect(() => {
    if (viewportRef.current) {
      viewportRef.current.scrollTop = viewportRef.current.scrollHeight;
    }
  }, [activeEntries, running]);

  const sshStatus = snapshot?.ssh_status || {};
  const sshUser = sshStatus.ssh_user || 'ubuntu';
  const sshHost = sshStatus.ssh_host || '<configure-ssh-host-in-settings>';
  const sshPort = Number(sshStatus.ssh_port || 22);
  const isLiveHostShell = Boolean(
    sshStatus.local_linux_execution || sshStatus.ssh_gateway_configured
  );

  const nativeSshCommand = useMemo(() => {
    if (!activeNode) return '';
    const portFlag = sshPort && sshPort !== 22 ? ` -p ${sshPort}` : '';
    const isHead =
      activeNode.role === 'management' ||
      activeNode.node_id === 'head-node' ||
      activeNode.node_id === 'headnode';
    if (isHead) {
      return `ssh${portFlag} ${sshUser}@${sshHost}`;
    }
    const jumpTarget = sshPort && sshPort !== 22 ? `${sshUser}@${sshHost}:${sshPort}` : `${sshUser}@${sshHost}`;
    return `ssh -J ${jumpTarget} ${sshUser}@${activeNode.ip}`;
  }, [activeNode, sshHost, sshPort, sshUser]);

  const [terminalEnabled, setTerminalEnabled] = useState(true);
  const [auditEntries, setAuditEntries] = useState([]);

  const loadTerminalState = async () => {
    try {
      const [presetRes, auditRes] = await Promise.allSettled([
        api.getTerminalPresets(),
        api.getTerminalAudit(30),
      ]);
      if (presetRes.status === 'fulfilled' && presetRes.value?.enabled !== undefined) {
        setTerminalEnabled(Boolean(presetRes.value.enabled));
      }
      if (auditRes.status === 'fulfilled') {
        setAuditEntries(auditRes.value?.entries || []);
      }
    } catch {
      // keep existing state
    }
  };

  React.useEffect(() => {
    loadTerminalState();
  }, []);

  const appendEntry = (nodeId, entry) => {
    setSessions((prev) => ({
      ...prev,
      [nodeId]: [...(prev[nodeId] || []), { id: `${Date.now()}-${Math.random()}`, ...entry }],
    }));
  };

  const clearActiveSession = () => {
    setSessions((prev) => ({
      ...prev,
      [activeNodeId]: [],
    }));
  };

  const runCommand = async (rawCmd, confirmed = false) => {
    const trimmed = (rawCmd || '').trim();
    if (!trimmed || running) return;

    if (trimmed.toLowerCase() === 'clear' || trimmed.toLowerCase() === 'cls') {
      clearActiveSession();
      setCmdInput('');
      setHistoryIdx(-1);
      return;
    }

    setCmdHistory((prev) => {
      const dedup = [trimmed, ...prev.filter((c) => c !== trimmed)];
      return dedup.slice(0, 40);
    });
    setHistoryIdx(-1);
    setCmdInput('');
    setRunning(true);

    try {
      const res = await api.execTerminalCommand(activeNodeId, trimmed, confirmed);
      if (res?.requires_confirmation) {
        setPendingConfirm({
          nodeId: activeNodeId,
          command: trimmed,
          message: res.confirmation_message,
        });
        setRunning(false);
        return;
      }

      appendEntry(activeNodeId, {
        type: res.ok ? 'result' : 'error',
        command: trimmed,
        output: res.output,
        executionMode: res.execution_mode,
        elapsedMs: res.elapsed_ms,
        timestamp: (res.timestamp_utc || new Date().toISOString()).slice(11, 19),
      });
    } catch (err) {
      appendEntry(activeNodeId, {
        type: 'error',
        command: trimmed,
        output: `[REJECTED] ${err.message}`,
        executionMode: 'policy_guard',
        elapsedMs: 0,
        timestamp: new Date().toISOString().slice(11, 19),
      });
    } finally {
      setRunning(false);
      loadTerminalState();
      setTimeout(() => inputRef.current?.focus(), 20);
    }
  };

  const handleKeyDown = (e) => {
    if (e.ctrlKey && e.key.toLowerCase() === 'l') {
      e.preventDefault();
      clearActiveSession();
      return;
    }
    if (e.key === 'ArrowUp') {
      e.preventDefault();
      if (cmdHistory.length === 0) return;
      const nextIdx = Math.min(historyIdx + 1, cmdHistory.length - 1);
      setHistoryIdx(nextIdx);
      setCmdInput(cmdHistory[nextIdx]);
    } else if (e.key === 'ArrowDown') {
      e.preventDefault();
      if (historyIdx <= 0) {
        setHistoryIdx(-1);
        setCmdInput('');
      } else {
        const nextIdx = historyIdx - 1;
        setHistoryIdx(nextIdx);
        setCmdInput(cmdHistory[nextIdx]);
      }
    }
  };

  const formatTranscriptText = () =>
    activeEntries
      .map((e) =>
        e.type === 'banner'
          ? `# ${e.output}`
          : `[${e.timestamp}] ${sshUser}@${activeNodeId}:~$ ${e.command}\n${e.output}\n`
      )
      .join('\n');

  const handleCopyTranscript = async () => {
    try {
      await navigator.clipboard.writeText(formatTranscriptText());
      if (showToast) showToast(`Copied ${activeNodeId} terminal transcript`);
    } catch {
      if (showToast) showToast('Clipboard copy failed');
    }
  };

  const handleDownloadTranscript = () => {
    const blob = new Blob([formatTranscriptText()], { type: 'text/plain;charset=utf-8' });
    const url = URL.createObjectURL(blob);
    const ts = new Date().toISOString().replace(/[:.]/g, '-').slice(0, 19);
    const a = document.createElement('a');
    a.href = url;
    a.download = `${activeNodeId}_terminal_session_${ts}.log`;
    document.body.appendChild(a);
    a.click();
    a.remove();
    URL.revokeObjectURL(url);
  };

  const handleCopyNativeSsh = async () => {
    try {
      await navigator.clipboard.writeText(nativeSshCommand);
      setCopiedSsh(true);
      setTimeout(() => setCopiedSsh(false), 2000);
      if (showToast) showToast('Copied native OpenSSH command');
    } catch {
      // ignore
    }
  };

  return (
    <div className="space-y-5">
      {/* Page Header */}
      <div className="flex flex-wrap items-center justify-between gap-3">
        <div className="flex items-center gap-3">
          <div className="flex h-10 w-10 items-center justify-center rounded-xl bg-cyan-500/15 text-[var(--accent-cyan)]">
            <Terminal className="h-5 w-5" />
          </div>
          <div>
            <div className="flex flex-wrap items-center gap-2.5">
              <h2 className="text-xl font-bold tracking-tight">Instance Terminal</h2>
              {isLiveHostShell ? (
                <span className="inline-flex items-center gap-1.5 rounded-full bg-emerald-500/15 px-2.5 py-0.5 text-[11px] font-semibold text-emerald-400">
                  <ShieldCheck className="h-3.5 w-3.5" />
                  {sshStatus.local_linux_execution
                    ? 'Live Local Linux Execution'
                    : `Live SSH Gateway (${sshUser}@${sshStatus.ssh_host})`}
                </span>
              ) : (
                <button
                  onClick={() => onNavigate && onNavigate('settings')}
                  className="inline-flex items-center gap-1.5 rounded-full border border-amber-500/40 bg-amber-500/10 px-2.5 py-0.5 text-[11px] font-semibold text-amber-400 hover:bg-amber-500/20"
                >
                  <Settings className="h-3 w-3" />
                  {snapshot?.mode === 'live_prometheus'
                    ? 'SSH Gateway Unconfigured — Set Host in Settings'
                    : 'Telemetry Console Mode — Configure Live SSH in Settings'}
                </button>
              )}
            </div>
            <p className="text-xs spu-text-secondary">
              Audited restricted shell access across Head &amp; Compute instances with command validation &amp; secret redaction
            </p>
          </div>
        </div>

        {/* Transcript Controls */}
        <div className="flex flex-wrap items-center gap-2">
          <button
            onClick={handleCopyTranscript}
            className="spu-btn-secondary inline-flex items-center gap-1.5"
          >
            <Copy className="h-3.5 w-3.5" />
            Copy Output
          </button>
          <button
            onClick={handleDownloadTranscript}
            className="spu-btn-secondary inline-flex items-center gap-1.5"
          >
            <Download className="h-3.5 w-3.5" />
            Export Session (.log)
          </button>
          <button
            onClick={clearActiveSession}
            className="spu-btn-secondary inline-flex items-center gap-1.5"
          >
            <Trash2 className="h-3.5 w-3.5 text-rose-400" />
            Clear
          </button>
        </div>
      </div>

      {/* Instance Session Selector Tabs */}
      <div className="flex flex-wrap items-center justify-between gap-3">
        <div className="flex flex-wrap gap-2">
          {nodes.map((n) => {
            const isSelected = n.node_id === activeNodeId;
            return (
              <button
                key={n.node_id}
                onClick={() => onSelectNode(n.node_id)}
                className={`inline-flex items-center gap-2 rounded-xl border px-3.5 py-2 text-xs font-semibold transition ${
                  isSelected
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
                <span className="rounded bg-[var(--bg-card-alt)] px-1.5 py-0.5 font-mono text-[9.5px]">
                  {n.slurm_state}
                </span>
              </button>
            );
          })}
        </div>

        {/* Native External SSH ProxyJump Helper */}
        {activeNode && (
          <div className="flex items-center gap-2 rounded-xl border px-3 py-1.5 text-[11px] spu-card">
            <ExternalLink className="h-3.5 w-3.5 shrink-0 text-[var(--accent-cyan)]" />
            <span className="hidden sm:inline spu-text-muted">Native TTY:</span>
            <code className="max-w-[260px] truncate font-mono text-[11px] spu-text-secondary md:max-w-[380px]">
              {nativeSshCommand}
            </code>
            <button
              onClick={handleCopyNativeSsh}
              className="rounded-md border px-2 py-0.5 text-[10.5px] font-semibold transition spu-border hover:border-[var(--accent-cyan)] hover:text-[var(--accent-cyan)]"
            >
              {copiedSsh ? (
                <span className="inline-flex items-center gap-1 text-emerald-400">
                  <Check className="h-3 w-3" />
                  Copied
                </span>
              ) : (
                'Copy SSH'
              )}
            </button>
          </div>
        )}
      </div>

      {!terminalEnabled && (
        <div className="flex flex-wrap items-center justify-between gap-3 rounded-xl border border-rose-500/40 bg-rose-500/10 px-4 py-3 text-xs text-rose-300">
          <div className="flex items-center gap-2">
            <Lock className="h-4 w-4 shrink-0" />
            <span>
              Operations Terminal is disabled by policy (<code className="font-mono">restricted_terminal_enabled = false</code>). Command executions return 403 and are logged to the security audit table.
            </span>
          </div>
          {onNavigate && (
            <button
              type="button"
              onClick={() => onNavigate('settings')}
              className="rounded-lg border border-rose-400/50 px-2.5 py-1 font-semibold hover:bg-rose-500/20"
            >
              Enable in System Settings
            </button>
          )}
        </div>
      )}

      {/* Main Console + Quick Command Palette */}
      <div className="grid grid-cols-1 gap-5 lg:grid-cols-12">
        {/* Left/Center: Interactive Console Window */}
        <div className="spu-card flex flex-col overflow-hidden lg:col-span-8 xl:col-span-9">
          {/* Terminal Window Titlebar */}
          <div
            style={{
              backgroundColor: 'var(--bg-card-alt)',
              borderBottom: '1px solid var(--border-subtle)',
            }}
            className="flex items-center justify-between px-4 py-2.5 text-xs"
          >
            <div className="flex items-center gap-2">
              <span className="h-2.5 w-2.5 rounded-full bg-rose-500/80" />
              <span className="h-2.5 w-2.5 rounded-full bg-amber-400/80" />
              <span className="h-2.5 w-2.5 rounded-full bg-emerald-500/80" />
              <span className="ml-2 font-mono font-semibold">
                {sshUser}@{activeNodeId}:~ ({activeNode?.ip || '127.0.0.1'})
              </span>
            </div>
            <div className="flex items-center gap-3 text-[11px] spu-text-muted">
              <span>↑/↓ History</span>
              <span>•</span>
              <span>Ctrl+L Clear</span>
            </div>
          </div>

          {/* Scrollable Output Viewport */}
          <div
            ref={viewportRef}
            onClick={() => inputRef.current?.focus()}
            style={{ backgroundColor: 'var(--bg-log)' }}
            className="h-[470px] cursor-text space-y-3 overflow-y-auto p-4 font-mono text-[12.5px] leading-relaxed"
          >
            {activeEntries.map((entry) => (
              <div key={entry.id} className="space-y-1">
                {entry.type === 'banner' ? (
                  <pre className="whitespace-pre-wrap rounded-lg border border-cyan-500/25 bg-cyan-500/8 p-3 text-[11.5px] text-[var(--accent-cyan)]">
                    {entry.output}
                  </pre>
                ) : (
                  <>
                    <div className="flex flex-wrap items-center justify-between gap-2">
                      <div>
                        <span className="font-semibold text-emerald-400">
                          {sshUser}@{activeNodeId}
                        </span>
                        <span className="spu-text-muted">:</span>
                        <span className="font-semibold text-sky-400">~</span>
                        <span className="spu-text-muted">$ </span>
                        <span className="font-semibold text-[var(--text-primary)]">
                          {entry.command}
                        </span>
                      </div>
                      <span className="text-[10.5px] spu-text-muted">
                        {entry.executionMode} • {entry.elapsedMs}ms • {entry.timestamp}
                      </span>
                    </div>
                    <pre
                      className={`whitespace-pre-wrap pl-1 text-[12px] ${
                        entry.type === 'error'
                          ? 'text-rose-400'
                          : 'spu-text-secondary'
                      }`}
                    >
                      {entry.output}
                    </pre>
                  </>
                )}
              </div>
            ))}

            {running && (
              <div className="flex items-center gap-2 text-xs text-[var(--accent-cyan)]">
                <span className="h-2 w-2 animate-ping rounded-full bg-[var(--accent-cyan)]" />
                Executing command on {activeNodeId}...
              </div>
            )}
          </div>

          {/* Command Prompt Input Form */}
          <form
            onSubmit={(e) => {
              e.preventDefault();
              runCommand(cmdInput, false);
            }}
            style={{
              backgroundColor: 'var(--bg-card-alt)',
              borderTop: '1px solid var(--border-subtle)',
            }}
            className="flex items-center gap-2 px-4 py-3 font-mono text-xs"
          >
            <span className="shrink-0 font-semibold text-emerald-400">
              {sshUser}@{activeNodeId}:~$
            </span>
            <input
              ref={inputRef}
              type="text"
              value={cmdInput}
              onChange={(e) => setCmdInput(e.target.value)}
              onKeyDown={handleKeyDown}
              disabled={running}
              autoFocus
              spellCheck={false}
              autoComplete="off"
              placeholder="Type a diagnostic command (e.g. uptime, free -h, sinfo, dmesg -T | tail -n 20, help)..."
              className="flex-1 bg-transparent text-[13px] outline-none placeholder:opacity-50"
            />
            <button
              type="submit"
              disabled={running || !cmdInput.trim()}
              className="spu-btn-primary inline-flex items-center gap-1.5 disabled:opacity-45"
            >
              <Play className="h-3.5 w-3.5" />
              Run
            </button>
          </form>
        </div>

        {/* Right Column: Quick Commands + Instance Live Status + Policy Notice */}
        <div className="space-y-4 lg:col-span-4 xl:col-span-3">
          {/* Active Instance Live Telemetry Snapshot */}
          {activeNode && (
            <div className="spu-card p-4">
              <div className="flex items-center justify-between border-b pb-2.5 spu-border">
                <div className="flex items-center gap-2">
                  <Server className="h-4 w-4 text-[var(--accent-cyan)]" />
                  <span className="text-xs font-bold">
                    {activeNode.display_name || activeNode.node_id}
                  </span>
                </div>
                <span className="font-mono text-[11px] font-semibold text-emerald-400">
                  {activeNode.health_classification || activeNode.health_status || 'Healthy'}
                </span>
              </div>
              <div className="mt-2.5 grid grid-cols-2 gap-2 text-[11px]">
                <div className="rounded-lg p-2 spu-subcard">
                  <div className="spu-text-muted">CPU / Load1</div>
                  <div className="mt-0.5 font-mono font-bold">
                    {activeNode.cpu_utilization_percent != null
                      ? `${activeNode.cpu_utilization_percent.toFixed(1)}%`
                      : 'Unavailable'}{' '}
                    / {activeNode.load1 ?? '--'}
                  </div>
                </div>
                <div className="rounded-lg p-2 spu-subcard">
                  <div className="spu-text-muted">Memory</div>
                  <div className="mt-0.5 font-mono font-bold">
                    {activeNode.memory_used_percent != null
                      ? `${activeNode.memory_used_percent.toFixed(1)}%`
                      : 'Unavailable'}
                  </div>
                </div>
              </div>
            </div>
          )}

          {/* Quick-Run Diagnostic Command Groups */}
          <div className="spu-card p-4">
            <h3 className="text-xs font-bold uppercase tracking-wider spu-text-muted">
              Quick Diagnostic Commands
            </h3>
            <div className="mt-3 space-y-3.5">
              {presetGroups.map((grp) => (
                <div key={grp.group}>
                  <div className="mb-1.5 text-[11px] font-semibold spu-text-secondary">
                    {grp.group}
                  </div>
                  <div className="flex flex-wrap gap-1.5">
                    {grp.commands.map((item) => (
                      <button
                        key={item.cmd}
                        disabled={running}
                        onClick={() => runCommand(item.cmd, false)}
                        title={item.cmd}
                        className="rounded-lg border px-2.5 py-1 text-[11px] font-medium transition spu-subcard hover:border-[var(--accent-cyan)] hover:text-[var(--accent-cyan)] disabled:opacity-50"
                      >
                        {item.label}
                      </button>
                    ))}
                  </div>
                </div>
              ))}
            </div>
          </div>

          {/* Security Guardrails Card */}
          <div className="spu-card p-4 text-[11.5px] spu-text-secondary">
            <div className="flex items-center gap-2 font-bold text-[var(--text-primary)]">
              <ShieldAlert className="h-4 w-4 text-[var(--accent-cyan)]" />
              Console Guardrails
            </div>
            <p className="mt-1.5 leading-relaxed">
              Commands execute via non-shell argument vectors (`6s` timeout, `512 KB` ceiling) with automatic private-key &amp; token redaction. Disruptive daemon or Slurm mutations require explicit confirmation and are recorded in the audit log.
            </p>
          </div>

          {/* Persistent Execution Audit Trail */}
          <div className="spu-card p-4 text-xs space-y-2">
            <div className="flex items-center justify-between">
              <span className="inline-flex items-center gap-1.5 font-bold">
                <History className="h-3.5 w-3.5 text-[var(--accent-cyan)]" />
                Recent Terminal Audit ({auditEntries.length})
              </span>
              <button
                type="button"
                onClick={loadTerminalState}
                className="text-[11px] text-[var(--accent-cyan)] hover:underline"
              >
                Refresh
              </button>
            </div>
            <div className="max-h-48 space-y-1.5 overflow-y-auto font-mono text-[10.5px]">
              {auditEntries.length === 0 ? (
                <div className="spu-text-muted">No terminal executions recorded yet.</div>
              ) : (
                auditEntries.slice(0, 12).map((row) => (
                  <div key={row.id} className="rounded-lg border spu-border px-2.5 py-1.5 spu-subcard">
                    <div className="flex items-center justify-between gap-2">
                      <span className={row.allowed ? 'text-emerald-400' : 'text-rose-400'}>
                        {row.allowed ? 'ALLOW' : 'BLOCK'} • {row.node_id}
                      </span>
                      <span className="spu-text-muted">{row.timestamp_utc?.slice(11, 19)}Z</span>
                    </div>
                    <div className="truncate font-semibold">{row.command}</div>
                    <div className="spu-text-muted truncate">{row.actor_email || 'admin'} • {row.execution_mode}</div>
                  </div>
                ))
              )}
            </div>
          </div>
        </div>
      </div>

      {/* Confirmation Modal for Disruptive Service / Slurm Commands */}
      <ConfirmModal
        open={Boolean(pendingConfirm)}
        title={`Confirm Command on ${pendingConfirm?.nodeId || activeNodeId}`}
        description={`${pendingConfirm?.message || ''} Command: ${pendingConfirm?.command || ''}`}
        confirmLabel="Execute Command"
        variant="warning"
        requireReason={false}
        onConfirm={() => {
          const item = pendingConfirm;
          setPendingConfirm(null);
          if (item) {
            runCommand(item.command, true);
          }
        }}
        onCancel={() => setPendingConfirm(null)}
      />
    </div>
  );
}
