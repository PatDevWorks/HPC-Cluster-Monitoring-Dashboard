import React, { useEffect, useMemo, useState } from 'react';
import { api, createLiveSocket } from './api.js';
import Sidebar from './components/Sidebar.jsx';
import HeaderBar from './components/HeaderBar.jsx';
import ConfirmModal from './components/ConfirmModal.jsx';
import FaultInjectionDrawer from './components/FaultInjectionDrawer.jsx';

import OverviewPage from './pages/OverviewPage.jsx';
import TopologyPage from './pages/TopologyPage.jsx';
import LiveMonitoringPage from './pages/LiveMonitoringPage.jsx';
import AiPredictionsPage from './pages/AiPredictionsPage.jsx';
import JobManagementPage from './pages/JobManagementPage.jsx';
import NodeLogsPage from './pages/NodeLogsPage.jsx';
import NodeTerminalPage from './pages/NodeTerminalPage.jsx';
import AlertsIncidentsPage from './pages/AlertsIncidentsPage.jsx';
import PerformanceAnalyticsPage from './pages/PerformanceAnalyticsPage.jsx';
import ReportsPage from './pages/ReportsPage.jsx';
import SettingsPage from './pages/SettingsPage.jsx';

export default function App() {
  const [snapshot, setSnapshot] = useState(null);
  const [wsConnected, setWsConnected] = useState(false);
  const [activePage, setActivePage] = useState('overview');
  const [sidebarCollapsed, setSidebarCollapsed] = useState(() => {
    try {
      return localStorage.getItem('spu_sidebar_collapsed') === '1';
    } catch {
      return false;
    }
  });
  const [mobileMenuOpen, setMobileMenuOpen] = useState(false);
  const [selectedNodeId, setSelectedNodeId] = useState('head-node');
  const [faultDrawerOpen, setFaultDrawerOpen] = useState(false);
  const [busyAction, setBusyAction] = useState(false);
  const [toast, setToast] = useState(null);
  const [confirmState, setConfirmState] = useState({ open: false });

  const showToast = (msg) => {
    setToast(msg);
    setTimeout(() => setToast(null), 3600);
  };

  useEffect(() => {
    api
      .getState()
      .then((data) => {
        setSnapshot(data);
        if (data?.nodes?.length > 0) {
          setSelectedNodeId(data.nodes[0].node_id);
        }
      })
      .catch(() => {});

    const cleanup = createLiveSocket(
      (liveData) => setSnapshot(liveData),
      (status) => setWsConnected(status)
    );
    return cleanup;
  }, []);

  useEffect(() => {
    if (!snapshot?.nodes?.length) return;
    const exists = snapshot.nodes.some((n) => n.node_id === selectedNodeId);
    if (!exists) {
      setSelectedNodeId(snapshot.nodes[0].node_id);
    }
  }, [snapshot?.mode, snapshot?.nodes, selectedNodeId]);

  const computeNodes = useMemo(
    () => (snapshot?.nodes || []).filter((n) => n.role !== 'management'),
    [snapshot?.nodes]
  );

  const toggleSidebarCollapse = () => {
    setSidebarCollapsed((prev) => {
      const next = !prev;
      try {
        localStorage.setItem('spu_sidebar_collapsed', next ? '1' : '0');
      } catch {
        // ignore
      }
      return next;
    });
  };

  const handleManualRefresh = async () => {
    setBusyAction(true);
    try {
      const data = await api.refreshState();
      setSnapshot(data);
      showToast('Cluster telemetry refreshed');
    } catch (err) {
      showToast(`Refresh failed: ${err.message}`);
    } finally {
      setBusyAction(false);
    }
  };

  const handleSwitchMode = async (mode, promUrl = null, presetId = null) => {
    setBusyAction(true);
    try {
      const data = await api.switchMode(mode, promUrl, presetId);
      setSnapshot(data);
      showToast(`Switched data pipeline to ${data.mode_label || mode}`);
    } catch (err) {
      showToast(`Mode switch failed: ${err.message}`);
    } finally {
      setBusyAction(false);
    }
  };

  const handleReloadModels = async () => {
    setBusyAction(true);
    try {
      const status = await api.reloadModels();
      showToast(
        `Model Registry Reloaded: ${status.engine_label} (${status.loaded_files.length} artifacts)`
      );
    } catch (err) {
      showToast(`Model reload failed: ${err.message}`);
    } finally {
      setBusyAction(false);
    }
  };

  const handleTogglePause = async () => {
    try {
      await api.togglePause();
    } catch (err) {
      showToast(`Stream toggle error: ${err.message}`);
    }
  };

  // Safe Confirmed Administrative Actions
  const promptDrainNode = (nodeObj = null) => {
    if (nodeObj) {
      setConfirmState({
        open: true,
        title: `Drain ${nodeObj.display_name || nodeObj.node_id} via Slurm`,
        description: `This marks ${nodeObj.node_id} (${nodeObj.ip}) as DRAIN in Slurm so no new compute jobs are scheduled onto it while running jobs finish safely.`,
        confirmLabel: 'Confirm Slurm Drain',
        variant: 'warning',
        requireReason: true,
        defaultReason: `Proactive maintenance / AI risk mitigation`,
        onConfirm: async ({ reason }) => {
          setConfirmState({ open: false });
          try {
            const res = await api.drainNode(nodeObj.node_id, reason);
            showToast(
              `Drained ${nodeObj.node_id} (${res.executed_mode}) — Protected ${res.jobs_protected} job(s)`
            );
          } catch (err) {
            showToast(`Drain error: ${err.message}`);
          }
        },
      });
    } else {
      setConfirmState({
        open: true,
        title: 'Drain Compute Node via Slurm',
        description:
          'Select a compute node to gracefully drain from the active Slurm scheduling pool.',
        confirmLabel: 'Confirm Slurm Drain',
        variant: 'warning',
        requireReason: true,
        defaultReason: 'Operator initiated node drain',
        nodePickerOptions: computeNodes,
        onConfirm: async ({ reason, nodeId }) => {
          setConfirmState({ open: false });
          if (!nodeId) return;
          try {
            const res = await api.drainNode(nodeId, reason);
            showToast(`Drained ${nodeId} (${res.executed_mode})`);
          } catch (err) {
            showToast(`Drain error: ${err.message}`);
          }
        },
      });
    }
  };

  const promptResumeNode = (nodeObj) => {
    setConfirmState({
      open: true,
      title: `Resume ${nodeObj.display_name || nodeObj.node_id} in Slurm`,
      description: `Return ${nodeObj.node_id} (${nodeObj.ip}) to active Slurm job scheduling?`,
      confirmLabel: 'Resume Node',
      variant: 'warning',
      requireReason: false,
      onConfirm: async () => {
        setConfirmState({ open: false });
        try {
          await api.resumeNode(nodeObj.node_id);
          showToast(`Resumed ${nodeObj.node_id} in Slurm pool`);
        } catch (err) {
          showToast(`Resume error: ${err.message}`);
        }
      },
    });
  };

  const promptCancelJob = (job) => {
    setConfirmState({
      open: true,
      title: `Cancel Slurm Job #${job.job_id} (${job.name})`,
      description: `Are you sure you want to terminate job #${job.job_id} owned by '${job.user}'? This action is logged in the administrative audit trail.`,
      confirmLabel: 'Cancel Slurm Job',
      variant: 'danger',
      requireReason: true,
      defaultReason: 'Cancelled by cluster administrator',
      onConfirm: async ({ reason }) => {
        setConfirmState({ open: false });
        try {
          await api.cancelJob(job.job_id, reason);
          showToast(`Cancelled Slurm job #${job.job_id}`);
        } catch (err) {
          showToast(`Job cancel failed: ${err.message}`);
        }
      },
    });
  };

  const handleAlertAction = async (episodeId, action) => {
    try {
      await api.alertAction(episodeId, action);
      showToast(`Incident #${episodeId}: ${action} applied`);
    } catch (err) {
      showToast(`Alert update failed: ${err.message}`);
    }
  };

  const handleInjectFault = async (nodeId, faultType) => {
    try {
      await api.injectFault(nodeId, faultType);
      setSelectedNodeId(nodeId);
      showToast(`Injected '${faultType}' on ${nodeId}`);
    } catch (err) {
      showToast(`Fault inject failed: ${err.message}`);
    }
  };

  const handleClearFaults = async (nodeId = null) => {
    try {
      await api.clearFaults(nodeId);
      showToast('Cleared injected faults');
    } catch (err) {
      showToast(`Clear failed: ${err.message}`);
    }
  };

  const navigateToNodeMonitoring = (nodeId) => {
    setSelectedNodeId(nodeId);
    setActivePage('monitoring');
  };

  const navigateToNodeLogs = (nodeId) => {
    setSelectedNodeId(nodeId);
    setActivePage('logs');
  };

  const navigateToNodeTerminal = (nodeId) => {
    setSelectedNodeId(nodeId);
    setActivePage('terminal');
  };

  return (
    <div className="flex h-screen overflow-hidden">
      <Sidebar
        activePage={activePage}
        onNavigate={setActivePage}
        collapsed={sidebarCollapsed}
        mobileOpen={mobileMenuOpen}
        onCloseMobile={() => setMobileMenuOpen(false)}
        snapshot={snapshot}
        wsConnected={wsConnected}
      />

      <div className="flex flex-1 flex-col overflow-hidden">
        <HeaderBar
          snapshot={snapshot}
          wsConnected={wsConnected}
          onToggleSidebar={toggleSidebarCollapse}
          onOpenMobileSidebar={() => setMobileMenuOpen(true)}
          onNavigate={setActivePage}
          onTogglePause={handleTogglePause}
          onOpenFaultLab={() => setFaultDrawerOpen(true)}
        />

        {toast && (
          <div className="fixed bottom-5 right-5 z-50 rounded-xl border border-cyan-500/50 bg-[var(--bg-card)] px-4 py-2.5 text-xs font-semibold shadow-xl">
            {toast}
          </div>
        )}

        <main className="flex-1 overflow-y-auto px-4 py-5 sm:px-6">
          <div className="mx-auto max-w-[1520px]">
            {!snapshot ? (
              <div className="flex h-[65vh] flex-col items-center justify-center gap-3 spu-text-secondary">
                <div className="h-8 w-8 animate-spin rounded-full border-2 border-[var(--accent-cyan)] border-t-transparent" />
                <p className="text-sm">
                  Connecting to Sol Plaatje A Dev Cluster Dashboard Backend...
                </p>
              </div>
            ) : (
              <>
                {activePage === 'overview' && (
                  <OverviewPage
                    snapshot={snapshot}
                    onNavigate={setActivePage}
                    onInspectNode={navigateToNodeMonitoring}
                    onOpenQuickDrain={() => promptDrainNode(null)}
                    onRefresh={handleManualRefresh}
                    refreshing={busyAction}
                  />
                )}

                {activePage === 'topology' && (
                  <TopologyPage
                    snapshot={snapshot}
                    onInspectMonitoring={navigateToNodeMonitoring}
                    onInspectLogs={navigateToNodeLogs}
                    onOpenTerminal={navigateToNodeTerminal}
                    onRequestDrain={(n) => promptDrainNode(n)}
                    onRequestResume={(n) => promptResumeNode(n)}
                  />
                )}

                {activePage === 'monitoring' && (
                  <LiveMonitoringPage
                    snapshot={snapshot}
                    selectedNodeId={selectedNodeId}
                    onSelectNode={setSelectedNodeId}
                  />
                )}

                {activePage === 'predictions' && (
                  <AiPredictionsPage
                    snapshot={snapshot}
                    selectedNodeId={selectedNodeId}
                    onSelectNode={setSelectedNodeId}
                    onReloadModels={handleReloadModels}
                    onOpenFaultLab={() => setFaultDrawerOpen(true)}
                    busyAction={busyAction}
                  />
                )}

                {activePage === 'jobs' && (
                  <JobManagementPage
                    snapshot={snapshot}
                    onInspectNode={navigateToNodeMonitoring}
                    onRequestDrain={(n) => promptDrainNode(n)}
                    onRequestResume={(n) => promptResumeNode(n)}
                    onRequestCancelJob={promptCancelJob}
                  />
                )}

                {activePage === 'logs' && (
                  <NodeLogsPage
                    snapshot={snapshot}
                    selectedNodeId={selectedNodeId}
                    onSelectNode={setSelectedNodeId}
                    onOpenTerminal={navigateToNodeTerminal}
                    showToast={showToast}
                  />
                )}

                {activePage === 'terminal' && (
                  <NodeTerminalPage
                    snapshot={snapshot}
                    selectedNodeId={selectedNodeId}
                    onSelectNode={setSelectedNodeId}
                    onNavigate={setActivePage}
                    showToast={showToast}
                  />
                )}

                {activePage === 'alerts' && (
                  <AlertsIncidentsPage
                    snapshot={snapshot}
                    onAlertAction={handleAlertAction}
                    onInspectMonitoring={navigateToNodeMonitoring}
                    onInspectLogs={navigateToNodeLogs}
                    onRequestDrainNodeId={(nid) => {
                      const target = (snapshot.nodes || []).find((x) => x.node_id === nid);
                      promptDrainNode(target || { node_id: nid, display_name: nid, ip: '' });
                    }}
                  />
                )}

                {activePage === 'analytics' && (
                  <PerformanceAnalyticsPage snapshot={snapshot} />
                )}

                {activePage === 'reports' && <ReportsPage snapshot={snapshot} />}

                {activePage === 'settings' && (
                  <SettingsPage
                    snapshot={snapshot}
                    wsConnected={wsConnected}
                    onSwitchMode={handleSwitchMode}
                    onReloadModels={handleReloadModels}
                    showToast={showToast}
                  />
                )}
              </>
            )}
          </div>
        </main>
      </div>

      <ConfirmModal
        open={confirmState.open}
        title={confirmState.title}
        description={confirmState.description}
        confirmLabel={confirmState.confirmLabel}
        variant={confirmState.variant}
        requireReason={confirmState.requireReason}
        defaultReason={confirmState.defaultReason}
        nodePickerOptions={confirmState.nodePickerOptions}
        onConfirm={confirmState.onConfirm}
        onCancel={() => setConfirmState({ open: false })}
      />

      <FaultInjectionDrawer
        open={faultDrawerOpen}
        onClose={() => setFaultDrawerOpen(false)}
        computeNodes={computeNodes}
        activeFaults={snapshot?.active_fault_injections || {}}
        onInject={handleInjectFault}
        onClear={handleClearFaults}
      />
    </div>
  );
}
