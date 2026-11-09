import React, { useState } from 'react';
import {
  BellRing,
  CheckCircle,
  Layers,
  ScrollText,
  ShieldOff,
  VolumeX,
} from 'lucide-react';

export default function OperationsTabsPanel({
  episodes,
  slurmJobs,
  systemLogs,
  onAlertAction,
  onDrainNode,
  onSelectNode,
}) {
  const [activeTab, setActiveTab] = useState('alerts');

  const activeAlertCount = (episodes || []).filter(
    (e) => e.status === 'active' || e.status === 'acknowledged'
  ).length;

  return (
    <div className="flex flex-col rounded-2xl border border-slate-800/90 bg-slate-900/60 p-4">
      {/* Tab Bar */}
      <div className="flex flex-wrap items-center gap-2 border-b border-slate-800/80 pb-3">
        <button
          onClick={() => setActiveTab('alerts')}
          className={`inline-flex items-center gap-1.5 rounded-lg px-3 py-1.5 text-xs font-semibold transition ${
            activeTab === 'alerts'
              ? 'bg-rose-500/20 text-rose-200 ring-1 ring-rose-500/40'
              : 'text-slate-400 hover:bg-slate-800 hover:text-slate-200'
          }`}
        >
          <BellRing className="h-3.5 w-3.5" />
          Priority Alert Triage
          <span className="rounded-full bg-slate-800 px-1.5 py-0.5 text-[10px] text-slate-200">
            {activeAlertCount}
          </span>
        </button>

        <button
          onClick={() => setActiveTab('slurm')}
          className={`inline-flex items-center gap-1.5 rounded-lg px-3 py-1.5 text-xs font-semibold transition ${
            activeTab === 'slurm'
              ? 'bg-indigo-500/20 text-indigo-200 ring-1 ring-indigo-500/40'
              : 'text-slate-400 hover:bg-slate-800 hover:text-slate-200'
          }`}
        >
          <Layers className="h-3.5 w-3.5" />
          Slurm Jobs &amp; Blast Radius
          <span className="rounded-full bg-slate-800 px-1.5 py-0.5 text-[10px] text-slate-200">
            {(slurmJobs || []).length}
          </span>
        </button>

        <button
          onClick={() => setActiveTab('logs')}
          className={`inline-flex items-center gap-1.5 rounded-lg px-3 py-1.5 text-xs font-semibold transition ${
            activeTab === 'logs'
              ? 'bg-cyan-500/20 text-cyan-200 ring-1 ring-cyan-500/40'
              : 'text-slate-400 hover:bg-slate-800 hover:text-slate-200'
          }`}
        >
          <ScrollText className="h-3.5 w-3.5" />
          Kernel &amp; Scheduler Logs
        </button>
      </div>

      {/* Tab Content */}
      <div className="mt-3 max-h-[430px] flex-1 overflow-y-auto pr-1">
        {activeTab === 'alerts' && (
          <div className="space-y-2.5">
            {(!episodes || episodes.length === 0) ? (
              <div className="rounded-xl border border-slate-800/80 bg-slate-950/50 p-6 text-center text-xs text-slate-400">
                Zero active alert episodes. Persistence gating (2-of-2 &amp; 3-of-3) is actively
                suppressing isolated telemetry noise.
              </div>
            ) : (
              episodes.map((ep) => {
                const badgeColor =
                  ep.priority === 'P1'
                    ? 'bg-rose-500 text-white'
                    : ep.priority === 'P2'
                    ? 'bg-amber-500 text-slate-950'
                    : 'bg-sky-500/30 text-sky-200';

                return (
                  <div
                    key={ep.id}
                    onClick={() => onSelectNode(ep.node_id)}
                    className={`cursor-pointer rounded-xl border p-3 transition ${
                      ep.status === 'resolved'
                        ? 'border-slate-800/60 bg-slate-950/30 opacity-60'
                        : ep.priority === 'P1'
                        ? 'border-rose-500/50 bg-rose-950/20'
                        : 'border-slate-800 bg-slate-950/70'
                    }`}
                  >
                    <div className="flex flex-wrap items-center justify-between gap-2">
                      <div className="flex items-center gap-2">
                        <span className={`rounded px-1.5 py-0.5 text-[10px] font-bold ${badgeColor}`}>
                          {ep.priority}
                        </span>
                        <span className="text-xs font-bold text-white">{ep.title}</span>
                      </div>
                      <div className="flex items-center gap-2 text-[10px] text-slate-400">
                        <span className="uppercase">{ep.status}</span>
                        <span>•</span>
                        <span>{ep.alert_points} pts</span>
                        <span>•</span>
                        <span>Peak {(ep.max_failure_prob * 100).toFixed(1)}%</span>
                      </div>
                    </div>

                    <p className="mt-1.5 text-[11px] leading-relaxed text-slate-300">
                      {ep.summary}
                    </p>

                    {ep.status !== 'resolved' && (
                      <div
                        className="mt-2.5 flex flex-wrap items-center justify-between gap-2 border-t border-slate-800/80 pt-2"
                        onClick={(e) => e.stopPropagation()}
                      >
                        <span className="font-mono text-[10px] text-slate-400">
                          Started {ep.start_utc?.slice(11, 19)}Z
                        </span>
                        <div className="flex items-center gap-1.5">
                          {ep.status === 'active' && (
                            <button
                              onClick={() => onAlertAction(ep.id, 'acknowledge')}
                              className="inline-flex items-center gap-1 rounded bg-slate-800 px-2 py-1 text-[10px] font-medium text-slate-200 hover:bg-slate-700"
                            >
                              <CheckCircle className="h-3 w-3 text-emerald-400" />
                              Ack
                            </button>
                          )}
                          <button
                            onClick={() => onAlertAction(ep.id, 'silence')}
                            className="inline-flex items-center gap-1 rounded bg-slate-800 px-2 py-1 text-[10px] font-medium text-slate-200 hover:bg-slate-700"
                          >
                            <VolumeX className="h-3 w-3 text-amber-300" />
                            Silence 30m
                          </button>
                          <button
                            onClick={() => onAlertAction(ep.id, 'resolve')}
                            className="rounded bg-slate-800 px-2 py-1 text-[10px] font-medium text-slate-300 hover:bg-slate-700"
                          >
                            Resolve
                          </button>
                          <button
                            onClick={() =>
                              onDrainNode(ep.node_id, `Episode #${ep.id} (${ep.fault_class})`)
                            }
                            className="inline-flex items-center gap-1 rounded bg-amber-500/20 px-2 py-1 text-[10px] font-semibold text-amber-200 ring-1 ring-amber-500/40 hover:bg-amber-500/30"
                          >
                            <ShieldOff className="h-3 w-3" />
                            Drain
                          </button>
                        </div>
                      </div>
                    )}
                  </div>
                );
              })
            )}
          </div>
        )}

        {activeTab === 'slurm' && (
          <div className="space-y-2.5">
            {(slurmJobs || []).map((job) => {
              const riskColor =
                job.blast_status === 'CRITICAL_RISK'
                  ? 'border-rose-500/60 bg-rose-950/20'
                  : job.blast_status === 'WARNING_RISK'
                  ? 'border-amber-500/50 bg-amber-950/15'
                  : 'border-slate-800 bg-slate-950/70';

              return (
                <div key={job.job_id} className={`rounded-xl border p-3 ${riskColor}`}>
                  <div className="flex flex-wrap items-center justify-between gap-2">
                    <div>
                      <span className="font-mono text-xs font-bold text-cyan-300">
                        Job #{job.job_id}
                      </span>{' '}
                      <span className="text-xs font-semibold text-white">{job.name}</span>
                    </div>
                    <span
                      className={`rounded px-2 py-0.5 text-[10px] font-bold ${
                        job.blast_status === 'CRITICAL_RISK'
                          ? 'bg-rose-500 text-white'
                          : job.blast_status === 'WARNING_RISK'
                          ? 'bg-amber-500 text-slate-950'
                          : 'bg-emerald-500/20 text-emerald-300'
                      }`}
                    >
                      {job.blast_status === 'HEALTHY' ? 'PROTECTED / OK' : job.blast_status}
                    </span>
                  </div>

                  <div className="mt-1.5 flex flex-wrap items-center gap-3 text-[11px] text-slate-400">
                    <span>User: {job.user}</span>
                    <span>•</span>
                    <span>State: {job.state}</span>
                    <span>•</span>
                    <span>{job.cpus} Cores ({job.mpi_ranks} MPI ranks)</span>
                    <span>•</span>
                    <span>Elapsed: {job.elapsed_hours}h</span>
                  </div>

                  <div className="mt-2 flex flex-wrap items-center gap-1.5">
                    {(job.nodes || []).map((nid) => {
                      const flagged = (job.at_risk_nodes || []).includes(nid);
                      const draining = (job.draining_nodes || []).includes(nid);
                      return (
                        <span
                          key={nid}
                          onClick={() => onSelectNode(nid)}
                          className={`cursor-pointer rounded px-2 py-0.5 font-mono text-[10px] font-semibold ${
                            draining
                              ? 'bg-amber-500/25 text-amber-200 ring-1 ring-amber-500/40'
                              : flagged
                              ? 'bg-rose-500/30 text-rose-200 ring-1 ring-rose-500/50'
                              : 'bg-slate-800 text-slate-300'
                          }`}
                        >
                          {nid} {draining ? '(DRAINING)' : flagged ? '(!)' : ''}
                        </span>
                      );
                    })}
                  </div>
                </div>
              );
            })}
          </div>
        )}

        {activeTab === 'logs' && (
          <div className="space-y-1.5 font-mono text-[11px]">
            {(systemLogs || []).map((log) => (
              <div
                key={log.id}
                className="rounded-lg border border-slate-800/80 bg-slate-950/80 px-2.5 py-2"
              >
                <div className="flex items-center justify-between text-[10px] text-slate-400">
                  <span>
                    <strong
                      className={
                        log.severity === 'CRITICAL'
                          ? 'text-rose-400'
                          : log.severity === 'WARNING'
                          ? 'text-amber-300'
                          : 'text-cyan-300'
                      }
                    >
                      [{log.severity}]
                    </strong>{' '}
                    {log.node_id} • {log.source}
                  </span>
                  <span>{log.timestamp_utc?.slice(11, 19)}Z</span>
                </div>
                <div className="mt-0.5 text-slate-200">{log.message}</div>
              </div>
            ))}
          </div>
        )}
      </div>
    </div>
  );
}
