import React, { useMemo, useState } from 'react';
import {
  Briefcase,
  PlayCircle,
  ShieldOff,
  XCircle,
} from 'lucide-react';
import {
  Bar,
  BarChart,
  CartesianGrid,
  Legend,
  ResponsiveContainer,
  Tooltip,
  XAxis,
  YAxis,
} from 'recharts';
import { useTheme } from '../context/ThemeContext.jsx';

export default function JobManagementPage({
  snapshot,
  onInspectNode,
  onRequestDrain,
  onRequestResume,
  onRequestCancelJob,
}) {
  const { chartTheme } = useTheme();
  const [stateFilter, setStateFilter] = useState('ALL');

  const jobs = snapshot?.slurm_jobs || [];
  const nodes = (snapshot?.nodes || []).filter((n) => n.role !== 'management');
  const auditLogs = snapshot?.slurm_audit || [];

  const counts = useMemo(() => {
    const c = { RUNNING: 0, PENDING: 0, COMPLETED: 0, FAILED: 0, cores: 0 };
    for (const j of jobs) {
      const st = String(j.state || '').toUpperCase();
      if (st === 'RUNNING') {
        c.RUNNING += 1;
        c.cores += Number(j.cpus || 0);
      } else if (st === 'PENDING') {
        c.PENDING += 1;
      } else if (st === 'COMPLETED') {
        c.COMPLETED += 1;
      } else {
        c.FAILED += 1;
      }
    }
    return c;
  }, [jobs]);

  const filteredJobs = useMemo(() => {
    if (stateFilter === 'ALL') return jobs;
    if (stateFilter === 'FAILED') {
      return jobs.filter((j) =>
        ['FAILED', 'CANCELLED', 'TIMEOUT', 'NODE_FAIL'].includes(
          String(j.state || '').toUpperCase()
        )
      );
    }
    return jobs.filter((j) => String(j.state || '').toUpperCase() === stateFilter);
  }, [jobs, stateFilter]);

  // Workload distribution across compute nodes
  const workloadByNode = useMemo(() => {
    return nodes.map((n) => {
      const runningOnNode = jobs.filter(
        (j) => j.state === 'RUNNING' && (j.nodes || []).includes(n.node_id)
      );
      const estCores = runningOnNode.reduce(
        (acc, j) => acc + Math.round((j.cpus || 0) / Math.max((j.nodes || []).length, 1)),
        0
      );
      return {
        node: n.display_name || n.node_id,
        allocated_cores: Math.min(n.cpu_cores || 24, estCores),
        total_cores: n.cpu_cores || 24,
        cpu_util: n.cpu_utilization_percent ?? 0,
      };
    });
  }, [nodes, jobs]);

  return (
    <div className="space-y-5">
      {/* Header */}
      <div className="flex flex-wrap items-center justify-between gap-3">
        <div className="flex items-center gap-3">
          <div className="flex h-10 w-10 items-center justify-center rounded-xl bg-cyan-500/15 text-[var(--accent-cyan)]">
            <Briefcase className="h-5 w-5" />
          </div>
          <div>
            <h2 className="text-xl font-bold tracking-tight">Job Management</h2>
            <p className="text-xs spu-text-secondary">
              Slurm workload scheduler queue, resource allocation &amp; confirmed node controls • Source:{' '}
              <span className="font-mono">{snapshot?.slurm_source || 'slurm'}</span>
            </p>
          </div>
        </div>
      </div>

      {/* Summary KPIs */}
      <section className="grid grid-cols-2 gap-3.5 sm:grid-cols-5">
        {[
          { id: 'RUNNING', label: 'Running Jobs', val: counts.RUNNING, color: 'text-emerald-400' },
          { id: 'PENDING', label: 'Pending Queue', val: counts.PENDING, color: 'text-amber-400' },
          { id: 'COMPLETED', label: 'Completed', val: counts.COMPLETED, color: 'text-[var(--accent-cyan)]' },
          { id: 'FAILED', label: 'Failed / Cancelled', val: counts.FAILED, color: 'text-rose-400' },
          { id: 'ALL', label: 'Active Allocated Cores', val: counts.cores, color: 'text-indigo-400' },
        ].map((item) => (
          <button
            key={item.label}
            onClick={() => setStateFilter(item.id)}
            className={`spu-card p-3.5 text-left transition ${
              stateFilter === item.id ? 'ring-2 ring-[var(--accent-cyan)]' : ''
            }`}
          >
            <div className="text-xs spu-text-secondary">{item.label}</div>
            <div className={`mt-1 text-2xl font-extrabold ${item.color}`}>{item.val}</div>
          </button>
        ))}
      </section>

      {/* Slurm Queue & History Table */}
      <section className="spu-card p-5">
        <div className="mb-3 flex flex-wrap items-center justify-between gap-2">
          <h3 className="text-sm font-bold">Slurm Jobs &amp; Queue Allocation</h3>
          <div className="spu-subcard inline-flex p-1 text-xs">
            {['ALL', 'RUNNING', 'PENDING', 'COMPLETED', 'FAILED'].map((st) => (
              <button
                key={st}
                onClick={() => setStateFilter(st)}
                className={`rounded-md px-2.5 py-1 font-semibold transition ${
                  stateFilter === st
                    ? 'bg-[var(--accent-cyan-strong)] text-white'
                    : 'spu-text-secondary hover:text-[var(--text-primary)]'
                }`}
              >
                {st}
              </button>
            ))}
          </div>
        </div>

        <div className="overflow-x-auto">
          <table className="w-full text-left text-xs">
            <thead>
              <tr className="border-b spu-border spu-text-secondary">
                <th className="py-2.5 pr-3">Job ID</th>
                <th className="py-2.5 pr-3">Job Name</th>
                <th className="py-2.5 pr-3">Owner</th>
                <th className="py-2.5 pr-3">Queue</th>
                <th className="py-2.5 pr-3">State</th>
                <th className="py-2.5 pr-3">Duration</th>
                <th className="py-2.5 pr-3">CPUs / Mem</th>
                <th className="py-2.5 pr-3">Allocated Nodes</th>
                <th className="py-2.5 pr-3">AI Node Risk</th>
                <th className="py-2.5 text-right">Actions</th>
              </tr>
            </thead>
            <tbody className="divide-y spu-border">
              {filteredJobs.length === 0 ? (
                <tr>
                  <td colSpan={10} className="py-8 text-center spu-text-secondary">
                    No Slurm jobs match the selected filter ({stateFilter}).
                  </td>
                </tr>
              ) : (
                filteredJobs.map((job) => {
                  const st = String(job.state || '').toUpperCase();
                  return (
                    <tr key={job.job_id} className="hover:bg-[var(--bg-hover)]">
                      <td className="py-2.5 pr-3 font-mono font-bold text-[var(--accent-cyan)]">
                        #{job.job_id}
                      </td>
                      <td className="py-2.5 pr-3 font-semibold">{job.name}</td>
                      <td className="py-2.5 pr-3 font-mono spu-text-secondary">{job.user}</td>
                      <td className="py-2.5 pr-3">{job.partition}</td>
                      <td className="py-2.5 pr-3">
                        <span
                          className={`rounded px-2 py-0.5 text-[10px] font-bold ${
                            st === 'RUNNING'
                              ? 'bg-emerald-500/15 text-emerald-400'
                              : st === 'PENDING'
                              ? 'bg-amber-500/15 text-amber-400'
                              : st === 'COMPLETED'
                              ? 'bg-cyan-500/15 text-[var(--accent-cyan)]'
                              : 'bg-rose-500/15 text-rose-400'
                          }`}
                        >
                          {st}
                        </span>
                      </td>
                      <td className="py-2.5 pr-3 font-mono">
                        {job.duration || `${job.elapsed_hours || 0}h`}
                      </td>
                      <td className="py-2.5 pr-3 font-mono">
                        {job.cpus}c {job.memory_req ? `• ${job.memory_req}` : ''}
                      </td>
                      <td className="py-2.5 pr-3">
                        <div className="flex flex-wrap gap-1">
                          {(job.nodes || []).map((nid) => (
                            <button
                              key={nid}
                              onClick={() => onInspectNode(nid)}
                              className="rounded px-1.5 py-0.5 font-mono text-[10px] spu-subcard hover:border-[var(--accent-cyan)]"
                            >
                              {nid}
                            </button>
                          ))}
                        </div>
                      </td>
                      <td className="py-2.5 pr-3 font-mono">
                        <span
                          className={
                            job.blast_status === 'CRITICAL_RISK'
                              ? 'text-rose-400 font-bold'
                              : job.blast_status === 'WARNING_RISK'
                              ? 'text-amber-400 font-semibold'
                              : 'text-emerald-400'
                          }
                        >
                          {((job.max_node_failure_prob || 0) * 100).toFixed(1)}%
                        </span>
                      </td>
                      <td className="py-2.5 text-right">
                        {(st === 'RUNNING' || st === 'PENDING') && (
                          <button
                            onClick={() => onRequestCancelJob(job)}
                            className="inline-flex items-center gap-1 rounded bg-rose-500/15 px-2 py-1 text-[10.5px] font-semibold text-rose-400 hover:bg-rose-500/25"
                          >
                            <XCircle className="h-3 w-3" /> Cancel
                          </button>
                        )}
                      </td>
                    </tr>
                  );
                })
              )}
            </tbody>
          </table>
        </div>
      </section>

      {/* Bottom Row: Workload Distribution + Node Scheduler Controls & Audit */}
      <section className="grid grid-cols-1 gap-4 lg:grid-cols-12">
        {/* Workload Distribution Chart */}
        <div className="spu-card p-5 lg:col-span-6">
          <h3 className="mb-3 text-sm font-bold">
            Workload &amp; CPU Distribution Across Compute Nodes
          </h3>
          <div className="h-60">
            <ResponsiveContainer width="100%" height="100%">
              <BarChart data={workloadByNode}>
                <CartesianGrid strokeDasharray="3 3" stroke={chartTheme.grid} />
                <XAxis dataKey="node" tick={{ fill: chartTheme.axis, fontSize: 11 }} />
                <YAxis tick={{ fill: chartTheme.axis, fontSize: 11 }} />
                <Tooltip contentStyle={chartTheme.tooltipStyle} />
                <Legend wrapperStyle={{ fontSize: '11px' }} />
                <Bar
                  dataKey="allocated_cores"
                  name="Allocated Cores"
                  fill={chartTheme.cyan}
                  radius={[4, 4, 0, 0]}
                />
                <Bar
                  dataKey="cpu_util"
                  name="Observed CPU %"
                  fill={chartTheme.purple}
                  radius={[4, 4, 0, 0]}
                />
              </BarChart>
            </ResponsiveContainer>
          </div>
        </div>

        {/* Safe Administrative Controls & Audit Trail */}
        <div className="spu-card p-5 lg:col-span-6">
          <h3 className="mb-3 text-sm font-bold">
            Compute Node Slurm Controls &amp; Administrative Audit Log
          </h3>

          <div className="grid grid-cols-1 gap-2 sm:grid-cols-3 mb-4">
            {nodes.slice(0, 6).map((n) => {
              const drained = String(n.slurm_state || '').includes('DRAIN');
              return (
                <div
                  key={n.node_id}
                  className="flex items-center justify-between rounded-xl p-2.5 spu-subcard text-xs"
                >
                  <div>
                    <div className="font-bold">{n.display_name || n.node_id}</div>
                    <div className="font-mono text-[10px] spu-text-muted">{n.slurm_state}</div>
                  </div>
                  {drained ? (
                    <button
                      onClick={() => onRequestResume(n)}
                      className="inline-flex items-center gap-1 rounded bg-emerald-500/20 px-2 py-1 text-[11px] font-semibold text-emerald-400"
                    >
                      <PlayCircle className="h-3.5 w-3.5" /> Resume
                    </button>
                  ) : (
                    <button
                      onClick={() => onRequestDrain(n)}
                      className="inline-flex items-center gap-1 rounded bg-amber-500/20 px-2 py-1 text-[11px] font-semibold text-amber-400"
                    >
                      <ShieldOff className="h-3.5 w-3.5" /> Drain
                    </button>
                  )}
                </div>
              );
            })}
          </div>

          <div className="max-h-40 space-y-1.5 overflow-y-auto text-xs">
            {auditLogs.length === 0 ? (
              <p className="spu-text-muted text-xs">No administrative actions recorded yet.</p>
            ) : (
              auditLogs.slice(0, 12).map((a) => (
                <div
                  key={a.id}
                  className="flex items-center justify-between rounded-lg px-2.5 py-1.5 spu-subcard font-mono text-[11px]"
                >
                  <span>
                    <strong className="text-[var(--accent-cyan)]">{a.action}</strong> • {a.node_id} —{' '}
                    <span className="spu-text-secondary">{a.reason}</span>
                  </span>
                  <span className="spu-text-muted shrink-0 ml-2">
                    {a.timestamp_utc?.slice(11, 19)}Z
                  </span>
                </div>
              ))
            )}
          </div>
        </div>
      </section>
    </div>
  );
}
