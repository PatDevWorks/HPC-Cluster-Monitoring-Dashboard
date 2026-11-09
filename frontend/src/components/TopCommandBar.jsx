import React, { useState } from 'react';
import {
  Activity,
  Cpu,
  Database,
  Flame,
  Pause,
  Play,
  Radio,
  RefreshCw,
  Server,
  Info,
} from 'lucide-react';

export default function TopCommandBar({
  snapshot,
  wsConnected,
  onSwitchMode,
  onReloadModels,
  onTogglePause,
  onOpenFaultLab,
  busyAction,
}) {
  const [promUrl, setPromUrl] = useState('http://localhost:9090');
  const [showModelModal, setShowModelModal] = useState(false);

  const mode = snapshot?.mode || 'live_cluster_sim';
  const modelStatus = snapshot?.model_status || {};
  const isPklActive =
    modelStatus.engine_mode === 'production_pkl_full' ||
    modelStatus.engine_mode === 'hybrid_pkl';
  const presets = snapshot?.replay_presets || [];
  const activeFaultCount = Object.keys(snapshot?.active_fault_injections || {}).length;

  return (
    <>
      <header className="sticky top-0 z-30 border-b border-slate-800/80 bg-slate-950/90 backdrop-blur-md">
        <div className="mx-auto flex max-w-[1600px] flex-wrap items-center justify-between gap-3 px-4 py-3">
          {/* Brand & Live Stream Pulse */}
          <div className="flex items-center gap-3">
            <div className="flex h-10 w-10 items-center justify-center rounded-xl bg-gradient-to-br from-cyan-500/20 to-blue-600/20 ring-1 ring-cyan-500/40">
              <Server className="h-5 w-5 text-cyan-400" />
            </div>
            <div>
              <div className="flex items-center gap-2">
                <h1 className="text-base font-bold tracking-tight text-white sm:text-lg">
                  Sol Plaatje A — HPC Predictive AIOps
                </h1>
                {snapshot?.is_synthetic && (
                  <span className="rounded-md bg-amber-500/20 px-2 py-0.5 text-[11px] font-semibold uppercase tracking-wider text-amber-300 ring-1 ring-amber-500/40">
                    Synthetic Dataset
                  </span>
                )}
              </div>
              <div className="flex items-center gap-2 text-xs text-slate-400">
                <span className="inline-flex items-center gap-1.5">
                  <span
                    className={`h-2 w-2 rounded-full ${
                      wsConnected && !snapshot?.paused
                        ? 'animate-pulse bg-emerald-400'
                        : 'bg-amber-400'
                    }`}
                  />
                  {wsConnected
                    ? snapshot?.paused
                      ? 'Stream Paused'
                      : 'Real-Time Stream'
                    : 'Reconnecting...'}
                </span>
                <span>•</span>
                <span className="font-mono text-[11px] text-slate-300">
                  {snapshot?.timestamp_utc || '--'}
                </span>
                {snapshot?.replay_progress && (
                  <>
                    <span>•</span>
                    <span className="font-mono text-[11px] text-cyan-400">
                      Frame {snapshot.replay_progress}
                    </span>
                  </>
                )}
              </div>
            </div>
          </div>

          {/* Pipeline Source Mode Switcher */}
          <div className="flex flex-wrap items-center gap-2">
            <div className="inline-flex rounded-lg bg-slate-900 p-1 ring-1 ring-slate-800">
              <button
                onClick={() => onSwitchMode('live_cluster_sim')}
                disabled={busyAction}
                className={`inline-flex items-center gap-1.5 rounded-md px-2.5 py-1.5 text-xs font-medium transition ${
                  mode === 'live_cluster_sim'
                    ? 'bg-cyan-500/20 text-cyan-300 ring-1 ring-cyan-500/40'
                    : 'text-slate-400 hover:text-slate-200'
                }`}
              >
                <Activity className="h-3.5 w-3.5" />
                4-Node Cluster Stream
              </button>
              <button
                onClick={() => onSwitchMode('live_prometheus', promUrl)}
                disabled={busyAction}
                className={`inline-flex items-center gap-1.5 rounded-md px-2.5 py-1.5 text-xs font-medium transition ${
                  mode === 'live_prometheus'
                    ? 'bg-emerald-500/20 text-emerald-300 ring-1 ring-emerald-500/40'
                    : 'text-slate-400 hover:text-slate-200'
                }`}
              >
                <Radio className="h-3.5 w-3.5" />
                Live Prometheus (:9090)
              </button>
              <button
                onClick={() =>
                  onSwitchMode('scc_dataset_replay', null, snapshot?.preset_id || 'sep03_mem_disk')
                }
                disabled={busyAction}
                className={`inline-flex items-center gap-1.5 rounded-md px-2.5 py-1.5 text-xs font-medium transition ${
                  mode === 'scc_dataset_replay'
                    ? 'bg-purple-500/20 text-purple-300 ring-1 ring-purple-500/40'
                    : 'text-slate-400 hover:text-slate-200'
                }`}
              >
                <Database className="h-3.5 w-3.5" />
                12-Node SCC Replay
              </button>
            </div>

            {mode === 'live_prometheus' && (
              <form
                onSubmit={(e) => {
                  e.preventDefault();
                  onSwitchMode('live_prometheus', promUrl);
                }}
                className="flex items-center gap-1"
              >
                <input
                  type="text"
                  value={promUrl}
                  onChange={(e) => setPromUrl(e.target.value)}
                  placeholder="http://localhost:9090"
                  className="w-44 rounded-lg border border-slate-700 bg-slate-900 px-2.5 py-1.5 font-mono text-xs text-slate-200 focus:border-cyan-500 focus:outline-none"
                />
                <button
                  type="submit"
                  className="rounded-lg bg-slate-800 px-2.5 py-1.5 text-xs font-medium text-slate-200 hover:bg-slate-700"
                >
                  Connect
                </button>
              </form>
            )}

            {mode === 'scc_dataset_replay' && presets.length > 0 && (
              <select
                value={snapshot?.preset_id || 'sep03_mem_disk'}
                onChange={(e) => onSwitchMode('scc_dataset_replay', null, e.target.value)}
                className="max-w-xs rounded-lg border border-purple-500/40 bg-slate-900 px-2.5 py-1.5 text-xs text-purple-200 focus:outline-none"
              >
                {presets.map((p) => (
                  <option key={p.id} value={p.id}>
                    {p.label}
                  </option>
                ))}
              </select>
            )}
          </div>

          {/* Hot-Swap ML Model Adapter Status + Controls */}
          <div className="flex items-center gap-2">
            <div
              onClick={() => setShowModelModal(true)}
              title="Click to inspect hot-swappable backend/models/ adapter status"
              className={`flex cursor-pointer items-center gap-2 rounded-lg px-2.5 py-1.5 text-xs font-medium ring-1 transition ${
                isPklActive
                  ? 'bg-emerald-500/15 text-emerald-300 ring-emerald-500/40 hover:bg-emerald-500/25'
                  : 'bg-amber-500/10 text-amber-300 ring-amber-500/30 hover:bg-amber-500/20'
              }`}
            >
              <Cpu className="h-3.5 w-3.5" />
              <span className="hidden xl:inline">
                {modelStatus.engine_label || 'Statistical Placeholder'}
              </span>
              <span className="xl:hidden">
                {isPklActive ? '.pkl Active' : 'Placeholder ML'}
              </span>
              <Info className="h-3.5 w-3.5 opacity-70" />
            </div>

            <button
              onClick={onReloadModels}
              disabled={busyAction}
              title="Hot-reload .pkl models from backend/models/ without restarting"
              className="inline-flex items-center gap-1.5 rounded-lg bg-slate-800/90 px-2.5 py-1.5 text-xs font-medium text-slate-200 ring-1 ring-slate-700 transition hover:bg-slate-700"
            >
              <RefreshCw className={`h-3.5 w-3.5 ${busyAction ? 'animate-spin' : ''}`} />
              <span className="hidden sm:inline">Reload .pkl</span>
            </button>

            <button
              onClick={onTogglePause}
              className="inline-flex items-center gap-1 rounded-lg bg-slate-800/90 px-2.5 py-1.5 text-xs font-medium text-slate-200 ring-1 ring-slate-700 transition hover:bg-slate-700"
            >
              {snapshot?.paused ? (
                <>
                  <Play className="h-3.5 w-3.5 text-emerald-400" />
                  Resume
                </>
              ) : (
                <>
                  <Pause className="h-3.5 w-3.5 text-amber-400" />
                  Pause
                </>
              )}
            </button>

            {mode !== 'scc_dataset_replay' && (
              <button
                onClick={onOpenFaultLab}
                className={`inline-flex items-center gap-1.5 rounded-lg px-3 py-1.5 text-xs font-semibold transition ${
                  activeFaultCount > 0
                    ? 'bg-rose-500/25 text-rose-200 ring-1 ring-rose-500/60 hover:bg-rose-500/35'
                    : 'bg-indigo-500/20 text-indigo-200 ring-1 ring-indigo-500/40 hover:bg-indigo-500/30'
                }`}
              >
                <Flame className="h-3.5 w-3.5 text-rose-400" />
                Fault Demo Lab
                {activeFaultCount > 0 && (
                  <span className="rounded-full bg-rose-500 px-1.5 py-0.2 text-[10px] font-bold text-white">
                    {activeFaultCount}
                  </span>
                )}
              </button>
            )}
          </div>
        </div>

        {/* Optional Banner for Prometheus Warning or Dataset Replay Context */}
        {(snapshot?.source_warning || snapshot?.preset_description) && (
          <div className="border-t border-slate-800/80 bg-slate-900/80 px-4 py-1.5 text-center text-xs text-slate-300">
            {snapshot.source_warning ? (
              <span className="text-amber-300">{snapshot.source_warning}</span>
            ) : (
              <span>
                <strong className="text-purple-300">Scenario Context:</strong>{' '}
                {snapshot.preset_description}
              </span>
            )}
          </div>
        )}
      </header>

      {/* Hot-Swap Model Adapter Inspector Modal */}
      {showModelModal && (
        <div className="fixed inset-0 z-50 flex items-center justify-center bg-black/70 p-4 backdrop-blur-sm">
          <div className="w-full max-w-lg rounded-2xl border border-slate-800 bg-slate-900 p-5 shadow-2xl">
            <div className="flex items-center justify-between border-b border-slate-800 pb-3">
              <h3 className="text-base font-semibold text-white">
                Hot-Swap ML Model Adapter Status
              </h3>
              <button
                onClick={() => setShowModelModal(false)}
                className="rounded-lg px-2 py-1 text-xs text-slate-400 hover:bg-slate-800 hover:text-white"
              >
                Close
              </button>
            </div>
            <div className="mt-4 space-y-3 text-xs text-slate-300">
              <p className="leading-relaxed text-slate-400">
                Drop trained <code className="text-cyan-300">.pkl</code> files from Phase 1 into{' '}
                <code className="rounded bg-slate-950 px-1.5 py-0.5 text-cyan-300">
                  {modelStatus.models_directory}
                </code>{' '}
                and click <strong>Reload .pkl</strong>. Any missing model automatically uses the
                calibrated statistical &amp; rolling-slope placeholder engine.
              </p>
              <div className="rounded-xl border border-slate-800 bg-slate-950 p-3">
                <div className="mb-2 font-semibold text-slate-200">Detector Slot Matrix</div>
                <div className="grid grid-cols-2 gap-2">
                  {Object.entries(modelStatus.detectors || {}).map(([name, state]) => (
                    <div
                      key={name}
                      className="flex items-center justify-between rounded-lg border border-slate-800/80 bg-slate-900/70 px-2.5 py-1.5"
                    >
                      <span className="font-mono text-[11px] text-slate-300">{name}</span>
                      <span
                        className={`rounded px-1.5 py-0.5 text-[10px] font-semibold uppercase ${
                          state === 'pkl'
                            ? 'bg-emerald-500/20 text-emerald-300'
                            : 'bg-amber-500/20 text-amber-300'
                        }`}
                      >
                        {state}
                      </span>
                    </div>
                  ))}
                </div>
              </div>
              <div className="flex justify-end gap-2 pt-2">
                <button
                  onClick={() => {
                    onReloadModels();
                    setShowModelModal(false);
                  }}
                  className="inline-flex items-center gap-1.5 rounded-lg bg-cyan-600 px-3 py-1.5 text-xs font-semibold text-white hover:bg-cyan-500"
                >
                  <RefreshCw className="h-3.5 w-3.5" />
                  Scan &amp; Reload Models Now
                </button>
              </div>
            </div>
          </div>
        </div>
      )}
    </>
  );
}
