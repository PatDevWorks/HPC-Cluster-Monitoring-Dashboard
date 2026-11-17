import React, { useEffect, useState } from 'react';
import {
  Activity,
  ChevronDown,
  ChevronRight,
  BarChart3,
  Bell,
  BrainCircuit,
  Briefcase,
  FileSpreadsheet,
  FileTerminal,
  Home,
  Network,
  Settings,
  Terminal,
  FlaskConical, Sparkles, Users,
} from 'lucide-react';
import SpuLogo from './SpuLogo.jsx';

export const NAV_ITEMS = [
  { id: 'overview', label: 'Dashboard Overview', icon: Home },
  { id: 'topology', label: 'Cluster Topology', icon: Network },
  { id: 'monitoring', label: 'Live Telemetry', icon: Activity },
  { id: 'logs', label: 'Node Logs & Diagnostics', icon: FileTerminal },
  { id: 'predictions', label: 'Models Centre', icon: BrainCircuit },
  { id: 'intelligence', label: 'AI Assistant', icon: Sparkles },
  { id: 'alerts', label: 'Incident Management', icon: Bell, showAlertBadge: true },
  { id: 'jobs', label: 'Workload Intelligence', icon: Briefcase },
  { id: 'terminal', label: 'Operations Terminal', icon: Terminal, adminOnly: true },
  { id: 'experiments', label: 'Model Evaluation', icon: FlaskConical },
  { id: 'analytics', label: 'Performance Analytics', icon: BarChart3 },
  { id: 'reports', label: 'Reports', icon: FileSpreadsheet },
  { id: 'settings', label: 'System Configuration', icon: Settings, adminOnly: true },
  { id: 'users', label: 'User Management', icon: Users, adminOnly: true },
];

export const NAV_GROUPS = [
  { id: 'overview', label: 'Overview', icon: Home, items: ['overview'] },
  { id: 'infrastructure', label: 'Infrastructure', icon: Network, items: ['topology', 'monitoring', 'logs'] },
  { id: 'intelligence', label: 'Intelligence', icon: BrainCircuit, items: ['predictions', 'intelligence', 'alerts', 'jobs'] },
  { id: 'operations', label: 'Operations', icon: Terminal, items: ['terminal'] },
  { id: 'analytics', label: 'Analytics', icon: BarChart3, items: ['experiments', 'analytics', 'reports'] },
  { id: 'administration', label: 'Administration', icon: Settings, adminOnly: true, items: ['settings', 'users'] },
];

function formatSidebarTimestamp(isoStr) {
  if (!isoStr) return '--';
  try {
    const d = new Date(isoStr);
    if (Number.isNaN(d.getTime())) return isoStr;
    return d.toLocaleString('en-GB', {
      day: '2-digit',
      month: 'short',
      year: 'numeric',
      hour: '2-digit',
      minute: '2-digit',
      second: '2-digit',
      hour12: false,
    }).replace(',', ' •');
  } catch {
    return isoStr;
  }
}

export default function Sidebar({
  activePage,
  onNavigate,
  collapsed,
  mobileOpen,
  onCloseMobile,
  snapshot,
  wsConnected,
  user,
}) {
  const [expandedGroups, setExpandedGroups] = useState({
    overview: true,
    infrastructure: true,
    intelligence: true,
    operations: false,
    analytics: false,
    administration: false,
  });
  const kpis = snapshot?.kpis || {};
  const nodesOnline = kpis.nodes_online ?? 0;
  const nodesTotal = kpis.nodes_total ?? 4;
  const clusterStatus = kpis.cluster_status || 'healthy';
  const statusLabel = kpis.cluster_status_label || 'Healthy';
  const activeAlerts = kpis.active_episodes_total || 0;

  const radius = 28;
  const circumference = 2 * Math.PI * radius;
  const availPct = nodesTotal > 0 ? Math.round((nodesOnline / nodesTotal) * 100) : 0;
  const dashOffset = circumference - (availPct / 100) * circumference;

  const ringColor =
    clusterStatus === 'healthy'
      ? '#10b981'
      : clusterStatus === 'warning'
      ? '#f59e0b'
      : '#ef4444';

  const isAdmin = ['admin', 'super_admin'].includes(user?.role);
  useEffect(() => {
    const activeGroup = NAV_GROUPS.find((group) => group.items.includes(activePage));
    if (activeGroup) setExpandedGroups((current) => ({ ...current, [activeGroup.id]: true }));
  }, [activePage]);

  const sidebarContent = (
    <aside
      style={{
        backgroundColor: 'var(--bg-sidebar)',
        borderRight: '1px solid var(--border-subtle)',
      }}
      className={`flex h-screen flex-col justify-between transition-all duration-200 ${
        collapsed ? 'w-[74px]' : 'w-[252px]'
      }`}
    >
      {/* Top University Branding */}
      <div className="flex min-h-0 flex-1 flex-col">
        <div
          onClick={() => onNavigate('overview')}
          style={{ borderBottom: '1px solid var(--border-subtle)' }}
          className="shrink-0 cursor-pointer px-3 py-4"
        >
          <SpuLogo collapsed={collapsed} />
        </div>

        {/* Navigation Links */}
        <nav className="mt-2 flex-1 space-y-2 overflow-y-auto px-2.5 pb-3" aria-label="Main navigation">
          {NAV_GROUPS.filter((group) => !group.adminOnly || isAdmin).map((group) => {
            const GroupIcon = group.icon;
            const items = group.items.map((id) => NAV_ITEMS.find((item) => item.id === id)).filter((item) => item && (!item.adminOnly || isAdmin));
            if (!items.length) return null;
            const expanded = expandedGroups[group.id];
            return <div key={group.id}>
              <button type="button" onClick={() => setExpandedGroups((old) => ({ ...old, [group.id]: !old[group.id] }))} title={collapsed ? group.label : undefined} aria-expanded={Boolean(expanded)} className="flex w-full items-center gap-2 rounded-lg px-3 py-2 text-left text-[10px] font-bold uppercase tracking-wider spu-text-muted hover:bg-[var(--bg-hover)]">
                <GroupIcon className="h-3.5 w-3.5 shrink-0" />
                {!collapsed && <><span className="flex-1">{group.label}</span>{expanded ? <ChevronDown className="h-3.5 w-3.5" /> : <ChevronRight className="h-3.5 w-3.5" />}</>}
              </button>
              {expanded && <div className="mt-0.5 space-y-0.5">{items.map((item) => {
                const Icon = item.icon;
                const isActive = activePage === item.id;
                return <button key={item.id} type="button" onClick={() => { onNavigate(item.id); if (onCloseMobile) onCloseMobile(); }} title={collapsed ? item.label : undefined} aria-current={isActive ? 'page' : undefined} style={isActive ? { background: 'var(--bg-active-nav)', color: 'var(--accent-cyan)', borderLeft: '3px solid var(--accent-cyan)' } : { borderLeft: '3px solid transparent' }} className={`group flex w-full items-center justify-between rounded-lg px-3 py-2.5 text-left text-[12px] font-medium transition-colors ${isActive ? 'font-semibold' : 'spu-text-secondary hover:bg-[var(--bg-hover)] hover:text-[var(--text-primary)]'}`}>
                  <span className="flex items-center gap-3 truncate"><Icon className={`h-4 w-4 shrink-0 ${isActive ? 'text-[var(--accent-cyan)]' : 'opacity-80 group-hover:opacity-100'}`} />{!collapsed && <span className="truncate">{item.label}</span>}</span>
                  {item.showAlertBadge && activeAlerts > 0 && <span className={`inline-flex items-center justify-center rounded-full bg-rose-500 font-bold text-white ${collapsed ? 'h-4 min-w-[16px] px-1 text-[9px]' : 'h-5 min-w-[20px] px-1.5 text-[10px]'}`}>{activeAlerts}</span>}
                </button>;
              })}</div>}
            </div>;
          })}
        </nav>
      </div>

      {/* Bottom Cluster Health Score Ring + Live Clock */}
      <div
        style={{ borderTop: '1px solid var(--border-subtle)' }}
        className="px-3 py-3.5"
      >
        {!collapsed ? (
          <div className="flex flex-col items-center">
            <div className="text-[11px] font-medium spu-text-secondary">
              Cluster Health Score
            </div>
            <div className="relative my-2 flex items-center justify-center">
              <svg className="h-18 w-18 -rotate-90 transform" viewBox="0 0 72 72">
                <circle
                  cx="36"
                  cy="36"
                  r={radius}
                  stroke="var(--border-strong)"
                  strokeWidth="6"
                  fill="transparent"
                  opacity="0.45"
                />
                <circle
                  cx="36"
                  cy="36"
                  r={radius}
                  stroke={ringColor}
                  strokeWidth="6"
                  strokeDasharray={circumference}
                  strokeDashoffset={dashOffset}
                  strokeLinecap="round"
                  fill="transparent"
                  className="transition-all duration-500"
                />
              </svg>
              <span className="absolute text-sm font-bold">{nodesOnline}/{nodesTotal}</span>
            </div>

            <div className="inline-flex items-center gap-1.5 text-xs font-semibold" style={{ color: ringColor }}>
              <span className="h-2 w-2 rounded-full" style={{ backgroundColor: ringColor }} />
              {statusLabel}
            </div>

            <div
              style={{ borderTop: '1px solid var(--border-subtle)' }}
              className="mt-3 w-full pt-2.5 text-[11px]"
            >
              <div className="spu-text-muted">Last Updated</div>
              <div className="mt-0.5 font-mono text-[10.5px] spu-text-secondary">
                {formatSidebarTimestamp(snapshot?.timestamp_utc)}
              </div>
              <div className="mt-1.5 flex items-center gap-1.5 font-medium">
                <span
                  className={`h-2 w-2 rounded-full ${
                    wsConnected && !snapshot?.paused
                      ? 'animate-pulse bg-emerald-500'
                      : 'bg-amber-500'
                  }`}
                />
                <span className="text-xs">
                  {wsConnected ? (snapshot?.paused ? 'Paused' : 'Live') : 'Reconnecting'}
                </span>
              </div>
            </div>
          </div>
        ) : (
          <div className="flex flex-col items-center gap-2" title={`Cluster Status: ${statusLabel} (${nodesOnline}/${nodesTotal} Online)`}>
            <div
              className="flex h-10 w-10 items-center justify-center rounded-full border-2 text-xs font-bold"
              style={{ borderColor: ringColor, color: ringColor }}
            >
              {nodesOnline}/{nodesTotal}
            </div>
            <span
              className={`h-2.5 w-2.5 rounded-full ${
                wsConnected && !snapshot?.paused ? 'bg-emerald-500' : 'bg-amber-500'
              }`}
            />
          </div>
        )}
      </div>
    </aside>
  );

  return (
    <>
      {/* Desktop Permanent Sidebar */}
      <div className="hidden lg:block shrink-0">{sidebarContent}</div>

      {/* Mobile Drawer Overlay */}
      {mobileOpen && (
        <div className="fixed inset-0 z-50 flex lg:hidden">
          <div className="relative z-10">{sidebarContent}</div>
          <div
            className="flex-1 bg-black/60 backdrop-blur-xs"
            onClick={onCloseMobile}
          />
        </div>
      )}
    </>
  );
}
