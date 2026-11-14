
import React, { useEffect, useMemo, useState } from 'react';
import { api, createLiveSocket } from './api.js';

import Sidebar from './components/Sidebar.jsx';
import HeaderBar from './components/HeaderBar.jsx';
import ConfirmModal from './components/ConfirmModal.jsx';
import ErrorBoundary from './components/ErrorBoundary.jsx';
import FaultInjectionDrawer from './components/FaultInjectionDrawer.jsx';
import AuthPage from './components/AuthPage.jsx';

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
import AiIntelligencePage from './pages/AiIntelligencePage.jsx';
import ExperimentsPage from './pages/ExperimentsPage.jsx';
import UserManagementPage from './pages/UserManagementPage.jsx';

export default function App() {
  // Authentication state
  const [authStatus, setAuthStatus] = useState('checking');
  const [user, setUser] = useState(null);

  // Cluster state
  const [snapshot, setSnapshot] = useState(null);
  const [wsConnected, setWsConnected] = useState(false);

  // Navigation state
  const [activePage, setActivePage] = useState('overview');
  const [investigateEpisodeId, setInvestigateEpisodeId] = useState(null);

  const [sidebarCollapsed, setSidebarCollapsed] = useState(() => {
    try {
      return localStorage.getItem('spu_sidebar_collapsed') === '1';
    } catch {
      return false;
    }
  });

  const [mobileMenuOpen, setMobileMenuOpen] = useState(false);
  const [selectedNodeId, setSelectedNodeId] = useState('head-node');

  // Dashboard interaction state
  const [faultDrawerOpen, setFaultDrawerOpen] = useState(false);
  const [busyAction, setBusyAction] = useState(false);
  const [toast, setToast] = useState(null);
  const [confirmState, setConfirmState] = useState({ open: false });

  const showToast = (msg) => {
    setToast(msg);
    setTimeout(() => setToast(null), 3600);
  };

  // ---------------------------------------------------------
  // 1. CHECK EXISTING AUTHENTICATION SESSION
  // ---------------------------------------------------------

  useEffect(() => {
    let mounted = true;

    const checkSession = async () => {
      try {
        const result = await api.getMe();

        if (!mounted) return;

        if (result?.authenticated && result?.user) {
          setUser(result.user);
          setAuthStatus('authenticated');
        } else {
          setUser(null);
          setAuthStatus('unauthenticated');
        }
      } catch {
        if (mounted) {
          setUser(null);
          setAuthStatus('unauthenticated');
        }
      }
    };

    checkSession();

    return () => {
      mounted = false;
    };
  }, []);

  // ---------------------------------------------------------
  // 2. START CLUSTER TELEMETRY AFTER AUTHENTICATION
  // ---------------------------------------------------------

  useEffect(() => {
    if (!user || authStatus !== 'authenticated') return;

    let mounted = true;

    // Load initial cluster state
    api
      .getState()
      .then((data) => {
        if (!mounted) return;

        setSnapshot(data);

        if (data?.nodes?.length > 0) {
          setSelectedNodeId(data.nodes[0].node_id);
        }
      })
      .catch((err) => {
        if (mounted) {
          showToast(`Cluster connection failed: ${err.message}`);
        }
      });

    // Establish live telemetry connection
    const cleanup = createLiveSocket(
      (liveData) => {
        if (mounted) {
          setSnapshot(liveData);
        }
      },
      (status) => {
        if (mounted) {
          setWsConnected(status);
        }
      }
    );

    return () => {
      mounted = false;

      if (typeof cleanup === 'function') {
        cleanup();
      }

      setWsConnected(false);
    };
  }, [user, authStatus]);

  // ---------------------------------------------------------
  // 3. KEEP SELECTED NODE VALID
  // ---------------------------------------------------------

  useEffect(() => {
    if (!snapshot?.nodes?.length) return;

    const exists = snapshot.nodes.some(
      (node) => node.node_id === selectedNodeId
    );

    if (!exists) {
      setSelectedNodeId(snapshot.nodes[0].node_id);
    }
  }, [snapshot?.mode, snapshot?.nodes, selectedNodeId]);

  // Compute nodes exclude management nodes
  const computeNodes = useMemo(
    () => (snapshot?.nodes || []).filter(
      (node) => node.role !== 'management'
    ),
    [snapshot?.nodes]
  );

  // ---------------------------------------------------------
  // 4. AUTHENTICATION HANDLERS
  // ---------------------------------------------------------

  const handleAuthenticated = (authenticatedUser) => {
    setSnapshot(null);
    setUser(authenticatedUser);
    setAuthStatus('authenticated');
    setActivePage('overview');
  };

  const handleLogout = async () => {
    try {
      await api.logout();
    } catch (err) {
      showToast(`Logout error: ${err.message}`);
    } finally {
      setUser(null);
      setSnapshot(null);
      setWsConnected(false);
      setFaultDrawerOpen(false);
      setConfirmState({ open: false });
      setActivePage('overview');
      setMobileMenuOpen(false);
      setAuthStatus('unauthenticated');
    }
  };

  // ---------------------------------------------------------
  // 5. SIDEBAR HANDLERS
  // ---------------------------------------------------------

  const toggleSidebarCollapse = () => {
    setSidebarCollapsed((prev) => {
      const next = !prev;

      try {
        localStorage.setItem(
          'spu_sidebar_collapsed',
          next ? '1' : '0'
        );
      } catch {
        // Ignore unavailable localStorage
      }

      return next;
    });
  };

  // ---------------------------------------------------------
  // 6. CLUSTER ACTION HANDLERS
  // ---------------------------------------------------------

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

  const handleSwitchMode = async (
    mode,
    promUrl = null,
    presetId = null
  ) => {
    setBusyAction(true);

    try {
      const data = await api.switchMode(mode, promUrl, presetId);
      setSnapshot(data);

      showToast(
        `Switched data pipeline to ${data.mode_label || mode}`
      );
    } catch (err) {
      showToast(`Mode switch failed: ${err.message}`);
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

  // ---------------------------------------------------------
  // 7. SAFE CONFIRMED ADMINISTRATIVE ACTIONS
  // ---------------------------------------------------------

  const promptDrainNode = (nodeObj = null) => {
    if (nodeObj) {
      setConfirmState({
        open: true,
        title: `Drain ${nodeObj.display_name || nodeObj.node_id} via Slurm`,
        description: `This marks ${nodeObj.node_id} (${nodeObj.ip}) as DRAIN in Slurm so no new compute jobs are scheduled onto it while running jobs finish safely.`,
        confirmLabel: 'Confirm Slurm Drain',
        variant: 'warning',
        requireReason: true,
        defaultReason: 'Proactive maintenance / AI risk mitigation',

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

            showToast(
              `Drained ${nodeId} (${res.executed_mode})`
            );
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

  // ---------------------------------------------------------
  // 8. ALERT AND FAULT INJECTION HANDLERS
  // ---------------------------------------------------------

  const handleAlertAction = async (episodeId, action, note = null) => {
    try {
      await api.alertAction(episodeId, action, note);
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

  // ---------------------------------------------------------
  // 9. NODE NAVIGATION HANDLERS
  // ---------------------------------------------------------

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

  // ---------------------------------------------------------
  // 10. RENDER APPLICATION
  // ---------------------------------------------------------

  return (
    <>
      {/* Session verification screen */}
      {authStatus === 'checking' && (
        <div className="flex min-h-screen items-center justify-center bg-[var(--bg-app)]">
          <div className="flex flex-col items-center gap-3">
            <div className="h-8 w-8 animate-spin rounded-full border-2 border-[var(--accent-cyan)] border-t-transparent" />

            <p className="text-sm spu-text-secondary">
              Verifying your dashboard session...
            </p>
          </div>
        </div>
      )}

      {/* Login screen */}
      {authStatus === 'unauthenticated' && (
        <AuthPage onAuthenticated={handleAuthenticated} />
      )}

      {/* Authenticated dashboard */}
      {authStatus === 'authenticated' && user && (
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
              user={user}
              onLogout={handleLogout}
              onToggleSidebar={toggleSidebarCollapse}
              onOpenMobileSidebar={() => setMobileMenuOpen(true)}
              onNavigate={setActivePage}
              onTogglePause={handleTogglePause}
              onOpenFaultLab={() => setFaultDrawerOpen(true)}
            />

            {/* Toast notifications */}
            {toast && (
              <div className="fixed bottom-5 right-5 z-50 rounded-xl border border-cyan-500/50 bg-[var(--bg-card)] px-4 py-2.5 text-xs font-semibold shadow-xl">
                {toast}
              </div>
            )}

            {/* Main dashboard content */}
            <main className="flex-1 overflow-y-auto px-4 py-5 sm:px-6">
              <div className="mx-auto max-w-[1520px]">
                <ErrorBoundary resetKey={activePage} sectionLabel={activePage}>

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
                        onRequestDrain={(node) => promptDrainNode(node)}
                        onRequestResume={(node) => promptResumeNode(node)}
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
                        user={user}
                        selectedNodeId={selectedNodeId}
                        onSelectNode={setSelectedNodeId}
                        onNavigate={setActivePage}
                        showToast={showToast}
                        busyAction={busyAction}
                      />
                    )}

                    {activePage === 'intelligence' && (
                      <AiIntelligencePage
                        snapshot={snapshot}
                        user={user}
                        selectedNodeId={selectedNodeId}
                        initialEpisodeId={investigateEpisodeId}
                        onNavigate={setActivePage}
                        showToast={showToast}
                      />
                    )}

                    {activePage === 'jobs' && (
                      <JobManagementPage
                        snapshot={snapshot}
                        onInspectNode={navigateToNodeMonitoring}
                        onRequestDrain={(node) => promptDrainNode(node)}
                        onRequestResume={(node) => promptResumeNode(node)}
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
                        onInvestigateIncident={(ep) => {
                          setInvestigateEpisodeId(ep?.id || null);
                          setActivePage('intelligence');
                        }}
                        onRequestDrainNodeId={(nodeId) => {
                          const target = (snapshot.nodes || []).find(
                            (node) => node.node_id === nodeId
                          );

                          promptDrainNode(
                            target || {
                              node_id: nodeId,
                              display_name: nodeId,
                              ip: '',
                            }
                          );
                        }}
                      />
                    )}

                    {activePage === 'experiments' && (
                      <ExperimentsPage
                        snapshot={snapshot}
                        user={user}
                        showToast={showToast}
                      />
                    )}

                    {activePage === 'analytics' && (
                      <PerformanceAnalyticsPage
                        snapshot={snapshot}
                        onNavigate={setActivePage}
                      />
                    )}

                    {activePage === 'reports' && (
                      <ReportsPage
                        snapshot={snapshot}
                        user={user}
                        showToast={showToast}
                      />
                    )}

                    {activePage === 'settings' && (
                      <SettingsPage
                        snapshot={snapshot}
                        wsConnected={wsConnected}
                        onSwitchMode={handleSwitchMode}
                        showToast={showToast}
                        user={user}
                      />
                    )}

                    {activePage === 'users' && (
                      <UserManagementPage
                        user={user}
                        showToast={showToast}
                      />
                    )}

                  </>
                )}
                </ErrorBoundary>

              </div>
            </main>
          </div>

          {/* Confirmation modal */}
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

          {/* Fault injection drawer */}
          <FaultInjectionDrawer
            open={faultDrawerOpen}
            onClose={() => setFaultDrawerOpen(false)}
            computeNodes={computeNodes}
            activeFaults={snapshot?.active_fault_injections || {}}
            onInject={handleInjectFault}
            onClear={handleClearFaults}
          />

        </div>
      )}
    </>
  );
}
