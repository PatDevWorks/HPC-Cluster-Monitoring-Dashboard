import React, { useEffect, useRef, useState } from 'react';
import {
  Bell,
  Flame,
  LogOut,
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
import { useTheme } from '../context/ThemeContext.jsx';
import { api } from '../api.js';

export default function HeaderBar({
  snapshot,
  wsConnected,
  onToggleSidebar,
  onOpenMobileSidebar,
  onNavigate,
  onTogglePause,
  onOpenFaultLab,
  user,
  onUserUpdated,
  onLogout,
}) {
  const { preference, setPreference } = useTheme();
  const [notifOpen, setNotifOpen] = useState(false);
  const [profileOpen, setProfileOpen] = useState(false);
  const [editingName, setEditingName] = useState(false);
  const [nameDraft, setNameDraft] = useState(user?.full_name || '');
  const [profileSaving, setProfileSaving] = useState(false);
  const [profileMessage, setProfileMessage] = useState('');

  const notifRef = useRef(null);
  const profileRef = useRef(null);

  const role = user?.role || 'viewer';
  const isAdmin = role === 'admin' || role === 'super_admin';
  const roleLabel =
    role === 'super_admin'
      ? 'Super Administrator'
      : role === 'admin'
        ? 'Administrator'
        : 'Viewer';

  useEffect(() => {
    const close = (e) => {
      if (notifRef.current && !notifRef.current.contains(e.target)) {
        setNotifOpen(false);
      }

      if (profileRef.current && !profileRef.current.contains(e.target)) {
        setProfileOpen(false);
      }
    };

    document.addEventListener('mousedown', close);
    return () => document.removeEventListener('mousedown', close);
  }, []);

  const episodes = snapshot?.alert_episodes || [];

  const activeAlerts = episodes.filter(
    (e) => e.status === 'active' || e.status === 'acknowledged'
  );

  const activeFaultCount = Object.keys(
    snapshot?.active_fault_injections || {}
  ).length;

  const displayName = user?.full_name || user?.email || 'Authenticated User';
  const initials = displayName
    .split(/[\s@._-]+/)
    .filter(Boolean)
    .slice(0, 2)
    .map((part) => part[0].toUpperCase())
    .join('');

  const saveProfileName = async (event) => {
    event.preventDefault();
    setProfileSaving(true);
    setProfileMessage('');
    try {
      const result = await api.updateProfile(nameDraft);
      onUserUpdated?.(result.user);
      setNameDraft(result.user.full_name);
      setEditingName(false);
      setProfileMessage('Name saved.');
    } catch (error) {
      setProfileMessage(error.message || 'Could not save your name.');
    } finally {
      setProfileSaving(false);
    }
  };

  // Telemetry connection status
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

        {/* Left: Sidebar Toggle + Platform Identity */}
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
                HPC Predictive Monitoring Dashboard
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

           
          </div>
        </div>

        {/* Right: Theme + Notifications + User Profile */}
        <div className="flex items-center gap-2.5">

          {/* Theme Switcher */}
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

          {/* Notifications */}
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
              <div className="spu-card absolute right-0 z-50 mt-2 w-80 p-3.5">
                <div className="flex items-center justify-between border-b pb-2 spu-border">
                  <span className="text-xs font-bold">
                    Active Cluster Notifications
                  </span>

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

          {/* Authenticated User Profile */}
          <div className="relative" ref={profileRef}>
            <button
              onClick={() => setProfileOpen((v) => !v)}
              title="Account and session information"
              aria-label="Open account menu"
              className="flex h-9 w-9 items-center justify-center rounded-full bg-indigo-500/85 text-xs font-bold text-white ring-1 ring-indigo-400/50 transition hover:bg-indigo-500"
            >
              {initials || 'SPU'}
            </button>

            {profileOpen && (
              <div className="spu-card absolute right-0 z-50 mt-2 w-72 p-2.5 text-xs">

                {/* Account Information */}
                <div className="border-b px-2.5 py-2 spu-border">
                  <div className="font-bold">
                    {displayName}
                  </div>

                  {user?.full_name && user?.email && (
                    <div className="mt-0.5 break-all text-[11px] spu-text-muted">
                      {user.email}
                    </div>
                  )}

                  <form onSubmit={saveProfileName} className="mt-2">
                    <label htmlFor="account-display-name" className="mb-1 block text-[11px] font-semibold spu-text-muted">
                      Account name
                    </label>
                    <div className="flex gap-1.5">
                      <input
                        id="account-display-name"
                        value={nameDraft}
                        onChange={(event) => setNameDraft(event.target.value)}
                        maxLength={120}
                        disabled={!editingName || profileSaving}
                        placeholder="Add your name"
                        className="min-w-0 flex-1 rounded-md border px-2 py-1.5 text-xs spu-border"
                      />
                      {editingName ? (
                        <>
                          <button type="submit" disabled={profileSaving || !nameDraft.trim()} className="rounded-md bg-cyan-600 px-2 py-1 text-[11px] font-semibold text-white disabled:opacity-50">
                            {profileSaving ? 'Saving' : 'Save'}
                          </button>
                          <button type="button" onClick={() => { setNameDraft(user?.full_name || ''); setEditingName(false); setProfileMessage(''); }} className="rounded-md border px-2 py-1 text-[11px] spu-border">
                            Cancel
                          </button>
                        </>
                      ) : (
                        <button type="button" onClick={() => { setNameDraft(user?.full_name || ''); setEditingName(true); setProfileMessage(''); }} className="rounded-md border px-2 py-1 text-[11px] font-semibold spu-border">
                          Edit
                        </button>
                      )}
                    </div>
                    {profileMessage && <p className="mt-1 text-[11px] spu-text-muted">{profileMessage}</p>}
                  </form>

                  <div className="mt-2 flex items-center justify-between">
                    <span className="font-semibold">
                      Sol Plaatje University
                    </span>

                    <span
                      className={`rounded-full px-2 py-0.5 text-[10px] font-semibold ${
                        isAdmin
                          ? 'bg-cyan-500/15 text-[var(--accent-cyan)]'
                          : 'bg-slate-500/20 spu-text-secondary'
                      }`}
                    >
                      {roleLabel}
                    </span>
                  </div>

                  <div className="mt-1 flex items-center gap-1.5 text-[11px] spu-text-muted">
                    <span
                      className={`h-1.5 w-1.5 rounded-full ${
                        wsConnected ? 'bg-emerald-400' : 'bg-amber-400'
                      }`}
                    />
                    {wsConnected
                      ? 'WebSocket Stream Connected'
                      : 'Stream Reconnecting'}
                  </div>

                  <div className="mt-2 flex items-center gap-1.5 text-[10px] spu-text-muted">
                    <Shield className="h-3 w-3" />
                    Permissions assigned by server
                  </div>
                </div>

                {/* System Controls */}
                <div className="mt-1 space-y-1">

                  {/* Admin-only operational controls */}
                  {isAdmin && (
                    <>
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
                    </>
                  )}

                  {/* Settings */}
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

                  {/* Logout */}
                  {onLogout && (
                    <>
                      <div className="my-1 border-t spu-border" />

                      <button
                        onClick={() => {
                          setProfileOpen(false);
                          onLogout();
                        }}
                        className="flex w-full items-center gap-2 rounded-lg px-2.5 py-2 text-left font-semibold text-rose-400 transition hover:bg-rose-500/10"
                      >
                        <LogOut className="h-3.5 w-3.5" />
                        Sign Out
                      </button>
                    </>
                  )}
                </div>
              </div>
            )}
          </div>
        </div>
      </div>

      {/* Telemetry Warning */}
      {snapshot?.source_warning && (
        <div className="border-t border-amber-500/30 bg-amber-500/10 px-4 py-1.5 text-center text-xs text-amber-400">
          {snapshot.source_warning}
        </div>
      )}
    </header>
  );
}
