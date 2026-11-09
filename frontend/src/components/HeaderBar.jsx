import React, { useEffect, useRef, useState } from 'react';
import {
  Bell,
  Flame,
  Menu,
  Monitor,
  Moon,
  Pause,
  Play,
  Radio,
  Settings,
  Shield,
  Sun,
} from 'lucide-react';
import { getAuthContext, setAdminToken, setOperatorRole } from '../api.js';
import { useTheme } from '../context/ThemeContext.jsx';

export default function HeaderBar({
  snapshot,
  wsConnected,
  onToggleSidebar,
  onOpenMobileSidebar,
  onNavigate,
  onTogglePause,
  onOpenFaultLab,
}) {
  const { preference, setPreference } = useTheme();
  const [notifOpen, setNotifOpen] = useState(false);
  const [profileOpen, setProfileOpen] = useState(false);
  const [role, setRoleState] = useState(() => getAuthContext().role);
  const [tokenInput, setTokenInput] = useState(() => getAuthContext().token);
  const notifRef = useRef(null);
  const profileRef = useRef(null);

  useEffect(() => {
    const close = (e) => {
      if (notifRef.current && !notifRef.current.contains(e.target)) setNotifOpen(false);
      if (profileRef.current && !profileRef.current.contains(e.target)) setProfileOpen(false);
    };
    document.addEventListener('mousedown', close);
    return () => document.removeEventListener('mousedown', close);
  }, []);

  const episodes = snapshot?.alert_episodes || [];
  const activeAlerts = episodes.filter(
    (e) => e.status === 'active' || e.status === 'acknowledged'
  );
  const activeFaultCount = Object.keys(snapshot?.active_fault_injections || {}).length;

  // Honest connection provenance badge
  let sourceText = 'Connecting...';
  let sourceDot = 'bg-amber-400';
  if (snapshot) {
    if (snapshot.mode === 'live_prometheus') {
      if (snapshot.prometheus_connected) {
        sourceText = 'Prometheus Live';
        sourceDot = 'bg-emerald-400';
      } else {
        sourceText = 'Prometheus Offline';
        sourceDot = 'bg-rose-500';
      }
    } else if (snapshot.mode === 'scc_dataset_replay') {
      sourceText = 'Synthetic Dataset Replay';
      sourceDot = 'bg-purple-400';
    } else {
      sourceText = 'Cluster Telemetry Sim';
      sourceDot = 'bg-cyan-400';
    }
  }

  return (
    <header
      style={{
        backgroundColor: 'var(--bg-header)',
        borderBottom: '1px solid var(--border-subtle)',
      }}
      className="sticky top-0 z-30 backdrop-blur-md"
    >
      <div className="flex items-center justify-between gap-3 px-4 py-3 sm:px-6">
        {/* Left: Collapse Toggle + Platform Identity */}
        <div className="flex items-center gap-3.5">
          <button
            onClick={() => {
              if (window.innerWidth < 1024) {
                onOpenMobileSidebar();
              } else {
                onToggleSidebar();
              }
            }}
            aria-label="Toggle navigation sidebar"
            className="rounded-lg p-2 spu-text-secondary transition hover:bg-[var(--bg-hover)] hover:text-[var(--text-primary)]"
          >
            <Menu className="h-5 w-5" />
          </button>

          <div>
            <div className="flex flex-wrap items-center gap-2.5">
              <h1 className="text-base font-bold tracking-tight sm:text-lg">
                Sol Plaatje A Dev Cluster Dashboard
              </h1>
              <span
                onClick={() => onNavigate('settings')}
                title="Click to configure telemetry source in Settings"
                className="hidden cursor-pointer items-center gap-1.5 rounded-full border px-2.5 py-0.5 text-[11px] font-medium md:inline-flex spu-subcard spu-text-secondary hover:border-[var(--accent-cyan)]"
              >
                <span className={`h-1.5 w-1.5 rounded-full ${sourceDot}`} />
                {sourceText}
              </span>
            </div>
            <p className="text-[11.5px] spu-text-secondary">
              Monitor • Analyse • Predict • Optimise
            </p>
          </div>
        </div>

        {/* Right: Theme Switcher + Notifications + Operator Menu */}
        <div className="flex items-center gap-2.5">
          {/* Dark / System / Light Theme Switcher Pill */}
          <div
            style={{
              backgroundColor: 'var(--bg-card-alt)',
              border: '1px solid var(--border-strong)',
            }}
            className="inline-flex items-center rounded-full p-1"
            role="group"
            aria-label="Theme switcher"
          >
            {[
              { id: 'dark', label: 'Dark Mode', icon: Moon },
              { id: 'system', label: 'System Default', icon: Monitor },
              { id: 'light', label: 'Light Mode', icon: Sun },
            ].map((opt) => {
              const Icon = opt.icon;
              const active = preference === opt.id;
              return (
                <button
                  key={opt.id}
                  onClick={() => setPreference(opt.id)}
                  title={opt.label}
                  className={`rounded-full p-1.5 transition ${
                    active
                      ? 'bg-[var(--accent-cyan-strong)] text-white shadow-xs'
                      : 'spu-text-secondary hover:text-[var(--text-primary)]'
                  }`}
                >
                  <Icon className="h-3.5 w-3.5" />
                </button>
              );
            })}
          </div>

          {/* Notification Bell Popover */}
          <div className="relative" ref={notifRef}>
            <button
              onClick={() => setNotifOpen((v) => !v)}
              aria-label="Notifications"
              style={{
                backgroundColor: 'var(--bg-card-alt)',
                border: '1px solid var(--border-strong)',
              }}
              className="relative flex h-9 w-9 items-center justify-center rounded-full spu-text-secondary transition hover:border-[var(--accent-cyan)] hover:text-[var(--text-primary)]"
            >
              <Bell className="h-4 w-4" />
              {activeAlerts.length > 0 && (
                <span className="absolute -top-1 -right-1 flex h-4 min-w-[16px] items-center justify-center rounded-full bg-rose-500 px-1 text-[10px] font-bold text-white">
                  {activeAlerts.length}
                </span>
              )}
            </button>

            {notifOpen && (
              <div className="spu-card absolute right-0 mt-2 w-80 p-3.5 z-50">
                <div className="flex items-center justify-between border-b pb-2 spu-border">
                  <span className="text-xs font-bold">Active Cluster Notifications</span>
                  <button
                    onClick={() => {
                      setNotifOpen(false);
                      onNavigate('alerts');
                    }}
                    className="text-[11px] font-semibold text-[var(--accent-cyan)] hover:underline"
                  >
                    Open Incidents →
                  </button>
                </div>
                <div className="mt-2.5 max-h-64 space-y-2 overflow-y-auto">
                  {activeAlerts.length === 0 ? (
                    <div className="py-5 text-center text-xs spu-text-secondary">
                      No active critical or warning alerts.
                    </div>
                  ) : (
                    activeAlerts.slice(0, 5).map((ep) => (
                      <div
                        key={ep.id}
                        onClick={() => {
                          setNotifOpen(false);
                          onNavigate('alerts');
                        }}
                        className="cursor-pointer rounded-lg p-2.5 text-xs transition spu-subcard hover:border-[var(--accent-cyan)]"
                      >
                        <div className="flex items-center justify-between font-semibold">
                          <span>{ep.title}</span>
                          <span className="font-mono text-[10px] spu-text-muted">
                            {ep.last_seen_utc?.slice(11, 19)}
                          </span>
                        </div>
                        <p className="mt-1 line-clamp-2 text-[11px] spu-text-secondary">
                          {ep.summary}
                        </p>
                      </div>
                    ))
                  )}
                </div>
              </div>
            )}
          </div>

          {/* Operator Avatar & Quick System Controls */}
          <div className="relative" ref={profileRef}>
            <button
              onClick={() => setProfileOpen((v) => !v)}
              title="HPC Operator Controls"
              className="flex h-9 w-9 items-center justify-center rounded-full bg-indigo-500/85 text-xs font-bold text-white ring-1 ring-indigo-400/50 transition hover:bg-indigo-500"
            >
              SPU
            </button>

            {profileOpen && (
              <div className="spu-card absolute right-0 mt-2 w-68 p-2.5 z-50 text-xs">
                <div className="border-b px-2.5 py-2 spu-border">
                  <div className="flex items-center justify-between font-bold">
                    <span>Sol Plaatje A</span>
                    <span
                      className={`rounded-full px-2 py-0.5 text-[10px] ${
                        role === 'admin'
                          ? 'bg-cyan-500/15 text-[var(--accent-cyan)]'
                          : 'bg-slate-500/20 spu-text-secondary'
                      }`}
                    >
                      {role === 'admin' ? 'Administrator' : 'Viewer'}
                    </span>
                  </div>
                  <div className="mt-0.5 text-[11px] spu-text-muted">
                    {wsConnected ? 'WebSocket Stream Connected' : 'Stream Reconnecting'}
                  </div>

                  {/* Role-Based Access Switcher */}
                  <div className="mt-2.5 flex items-center gap-1 rounded-lg border p-0.5 spu-border">
                    {[
                      { id: 'admin', label: 'Admin' },
                      { id: 'viewer', label: 'Read-Only' },
                    ].map((r) => (
                      <button
                        key={r.id}
                        onClick={() => {
                          setRoleState(r.id);
                          setOperatorRole(r.id);
                        }}
                        className={`flex-1 rounded-md py-1 text-[11px] font-semibold transition ${
                          role === r.id
                            ? 'bg-[var(--accent-cyan-strong)] text-white'
                            : 'spu-text-secondary hover:text-[var(--text-primary)]'
                        }`}
                      >
                        <Shield className="mr-1 inline h-3 w-3" />
                        {r.label}
                      </button>
                    ))}
                  </div>

                  {snapshot?.admin_token_required && (
                    <div className="mt-2">
                      <label className="block text-[10px] font-semibold spu-text-muted">
                        Server Admin Token
                      </label>
                      <input
                        type="password"
                        value={tokenInput}
                        onChange={(e) => {
                          setTokenInput(e.target.value);
                          setAdminToken(e.target.value);
                        }}
                        placeholder="Enter HPC_ADMIN_TOKEN"
                        className="spu-input mt-1 w-full rounded-md px-2 py-1 text-[11px]"
                      />
                    </div>
                  )}
                </div>
                <div className="mt-1 space-y-1">
                  <button
                    onClick={() => {
                      onTogglePause();
                      setProfileOpen(false);
                    }}
                    className="flex w-full items-center gap-2 rounded-lg px-2.5 py-2 text-left transition hover:bg-[var(--bg-hover)]"
                  >
                    {snapshot?.paused ? (
                      <>
                        <Play className="h-3.5 w-3.5 text-emerald-400" />
                        Resume Live Stream
                      </>
                    ) : (
                      <>
                        <Pause className="h-3.5 w-3.5 text-amber-400" />
                        Pause Live Stream
                      </>
                    )}
                  </button>

                  {snapshot?.mode === 'live_cluster_sim' && (
                    <button
                      onClick={() => {
                        onOpenFaultLab();
                        setProfileOpen(false);
                      }}
                      className="flex w-full items-center justify-between rounded-lg px-2.5 py-2 text-left transition hover:bg-[var(--bg-hover)]"
                    >
                      <span className="flex items-center gap-2">
                        <Flame className="h-3.5 w-3.5 text-rose-400" />
                        Fault Injection Lab
                      </span>
                      {activeFaultCount > 0 && (
                        <span className="rounded-full bg-rose-500 px-1.5 text-[10px] font-bold text-white">
                          {activeFaultCount}
                        </span>
                      )}
                    </button>
                  )}

                  <button
                    onClick={() => {
                      onNavigate('settings');
                      setProfileOpen(false);
                    }}
                    className="flex w-full items-center gap-2 rounded-lg px-2.5 py-2 text-left transition hover:bg-[var(--bg-hover)]"
                  >
                    <Radio className="h-3.5 w-3.5 text-[var(--accent-cyan)]" />
                    Data Source &amp; Prometheus
                  </button>

                  <button
                    onClick={() => {
                      onNavigate('settings');
                      setProfileOpen(false);
                    }}
                    className="flex w-full items-center gap-2 rounded-lg px-2.5 py-2 text-left transition hover:bg-[var(--bg-hover)]"
                  >
                    <Settings className="h-3.5 w-3.5 spu-text-secondary" />
                    Platform Settings
                  </button>
                </div>
              </div>
            )}
          </div>
        </div>
      </div>

      {/* Prominent Disconnection / Synthetic Notice Banner when applicable */}
      {snapshot?.source_warning && (
        <div className="border-t border-amber-500/30 bg-amber-500/10 px-4 py-1.5 text-center text-xs text-amber-400">
          {snapshot.source_warning}
        </div>
      )}
    </header>
  );
}
