import React, { useMemo, useState } from 'react';
import {
  Activity,
  Bell,
  CheckCircle2,
  FileTerminal,
  ShieldOff,
  VolumeX,
  Filter, Sparkles,
} from 'lucide-react';

export default function AlertsIncidentsPage({
  snapshot,
  onAlertAction,
  onInspectMonitoring,
  onInspectLogs,
  onRequestDrainNodeId,
  onInvestigateIncident,
}) {
  const [severityFilter, setSeverityFilter] = useState('ALL');
  const [statusFilter, setStatusFilter] = useState('OPEN');
  const [sourceFilter, setSourceFilter] = useState('ALL');
  const [selectedEpId, setSelectedEpId] = useState(null);
  const [actionNote, setActionNote] = useState('');

  const episodes = snapshot?.alert_episodes || [];

  const counts = useMemo(() => {
    return {
      critical: episodes.filter((e) => e.priority === 'P1' && e.status !== 'resolved').length,
      warning: episodes.filter((e) => e.priority === 'P2' && e.status !== 'resolved').length,
      info: episodes.filter((e) => e.priority === 'P3' && e.status !== 'resolved').length,
      resolved: episodes.filter((e) => e.status === 'resolved').length,
    };
  }, [episodes]);

  const filtered = useMemo(() => {
    return episodes.filter((ep) => {
      if (severityFilter !== 'ALL' && ep.priority !== severityFilter) return false;
      if (statusFilter === 'OPEN' && ep.status === 'resolved') return false;
      if (statusFilter === 'RESOLVED' && ep.status !== 'resolved') return false;
      if (sourceFilter !== 'ALL' && (ep.alert_source || 'telemetry') !== sourceFilter) return false;
      return true;
    });
  }, [episodes, severityFilter, statusFilter, sourceFilter]);

  const selectedEpisode = useMemo(() => {
    return filtered.find((e) => e.id === selectedEpId) || filtered[0] || null;
  }, [filtered, selectedEpId]);

  return (
    <div className="space-y-5">
      {/* Header */}
      <div className="flex flex-wrap items-center justify-between gap-3">
        <div className="flex items-center gap-3">
          <div className="flex h-10 w-10 items-center justify-center rounded-xl bg-rose-500/15 text-rose-400">
            <Bell className="h-5 w-5" />
          </div>
          <div>
            <h2 className="text-xl font-bold tracking-tight">Alerts &amp; Incidents</h2>
            
          </div>
        </div>

        <div className="spu-subcard inline-flex p-1 text-xs">
          {[
            { id: 'OPEN', label: 'Active & Acknowledged' },
            { id: 'ALL', label: 'All History' },
            { id: 'RESOLVED', label: 'Resolved' },
          ].map((s) => (
            <button
              key={s.id}
              onClick={() => setStatusFilter(s.id)}
              className={`rounded-md px-3 py-1 font-semibold transition ${
                statusFilter === s.id
                  ? 'bg-[var(--accent-cyan-strong)] text-white'
                  : 'spu-text-secondary hover:text-[var(--text-primary)]'
              }`}
            >
              {s.label}
            </button>
          ))}
        </div>
      </div>

      {/* Severity Filter Cards */}
      <section className="grid grid-cols-2 gap-3.5 sm:grid-cols-4">
        {[
          { id: 'ALL', label: 'All Open Incidents', count: counts.critical + counts.warning + counts.info, color: '' },
          { id: 'P1', label: 'Critical (P1)', count: counts.critical, color: 'text-rose-400' },
          { id: 'P2', label: 'Warning (P2)', count: counts.warning, color: 'text-amber-400' },
          { id: 'P3', label: 'Informational / Watch (P3)', count: counts.info, color: 'text-sky-400' },
        ].map((card) => (
          <button
            key={card.id}
            onClick={() => setSeverityFilter(card.id)}
            className={`spu-card p-3.5 text-left transition ${
              severityFilter === card.id ? 'ring-2 ring-[var(--accent-cyan)]' : ''
            }`}
          >
            <div className="text-xs spu-text-secondary">{card.label}</div>
            <div className={`mt-1 text-2xl font-extrabold ${card.color}`}>{card.count}</div>
          </button>
        ))}
      </section>

      {/* Detection Source Filter */}
      <div className="flex flex-wrap items-center gap-2 text-xs">
        <span className="spu-text-muted font-semibold inline-flex items-center gap-1">
          <Filter className="h-3.5 w-3.5" /> Source:
        </span>
        {[
          { id: 'ALL', label: 'All Sources' },
          { id: 'telemetry', label: 'Telemetry Thresholds' },
          { id: 'v7', label: 'V7 Isolation Forest' },
          { id: 'lstm_v8', label: 'LSTM V8' },
        ].map((s) => (
          <button
            key={s.id}
            type="button"
            onClick={() => setSourceFilter(s.id)}
            className={`rounded-lg px-2.5 py-1 font-semibold transition ${
              sourceFilter === s.id
                ? 'bg-cyan-500/20 text-[var(--accent-cyan)] border border-cyan-500/40'
                : 'spu-subcard spu-text-secondary hover:text-[var(--text-primary)]'
            }`}
          >
            {s.label}
          </button>
        ))}
      </div>

      {/* Master-Detail Incident Layout */}
      <section className="grid grid-cols-1 gap-4 lg:grid-cols-12">
        {/* Left: Incident Feed */}
        <div className="spu-card p-4 lg:col-span-7 space-y-2.5 max-h-[540px] overflow-y-auto">
          {filtered.length === 0 ? (
            <div className="flex flex-col items-center justify-center py-14 text-center">
              <CheckCircle2 className="h-10 w-10 text-emerald-400 mb-2" />
              <div className="text-sm font-bold">No matching incidents</div>
              
            </div>
          ) : (
            filtered.map((ep) => {
              const active = selectedEpisode?.id === ep.id;
              return (
                <div
                  key={ep.id}
                  onClick={() => setSelectedEpId(ep.id)}
                  className={`cursor-pointer rounded-xl border p-3.5 transition spu-subcard ${
                    active ? 'border-[var(--accent-cyan)]' : 'hover:border-[var(--border-strong)]'
                  }`}
                >
                  <div className="flex flex-wrap items-center justify-between gap-2">
                    <div className="flex items-center gap-2">
                      <span
                        className={`rounded px-2 py-0.5 text-[10px] font-bold uppercase ${
                          ep.priority === 'P1'
                            ? 'bg-rose-500 text-white'
                            : ep.priority === 'P2'
                            ? 'bg-amber-500 text-slate-950'
                            : 'bg-sky-500/20 text-sky-400'
                        }`}
                      >
                        {ep.severity || ep.priority}
                      </span>
                      <span className="text-xs font-bold">{ep.title}</span>
                    </div>
                    <span className="rounded px-2 py-0.5 font-mono text-[10px] uppercase spu-card">
                      {ep.status}
                    </span>
                  </div>

                  <p className="mt-1.5 text-xs spu-text-secondary">{ep.summary}</p>

                  <div className="mt-2 flex flex-wrap items-center justify-between text-[11px] spu-text-muted font-mono">
                    <span>
                      Node: {ep.node_id} • Source: {ep.alert_source || 'telemetry'} • Event: {ep.event_type || ep.fault_class}
                    </span>
                    <span>Updated: {ep.last_seen_utc?.slice(0, 19).replace('T', ' ')}Z</span>
                  </div>
                </div>
              );
            })
          )}
        </div>

        {/* Right: Incident Inspector & Actions */}
        <div className="spu-card p-5 lg:col-span-5">
          {selectedEpisode ? (
            <div className="space-y-4">
              <div className="border-b pb-3 spu-border">
                <div className="text-[11px] font-mono spu-text-muted">
                  Incident #{selectedEpisode.id} • Started {selectedEpisode.start_utc}
                </div>
                <h3 className="mt-1 text-base font-bold">{selectedEpisode.title}</h3>
              </div>

              <div className="grid grid-cols-3 gap-2 text-xs">
                <div className="spu-subcard p-2.5">
                  <span className="block text-[10px] spu-text-muted">Source</span>
                  <strong className="font-mono text-sm uppercase text-[var(--accent-cyan)]">
                    {selectedEpisode.alert_source || 'telemetry'}
                  </strong>
                </div>
                <div className="spu-subcard p-2.5">
                  <span className="block text-[10px] spu-text-muted">Severity</span>
                  <strong className="font-mono text-sm uppercase">
                    {selectedEpisode.severity || selectedEpisode.priority}
                  </strong>
                </div>
                <div className="spu-subcard p-2.5">
                  <span className="block text-[10px] spu-text-muted">Observations</span>
                  <strong className="font-mono text-sm">
                    {selectedEpisode.alert_points} pts
                  </strong>
                </div>
              </div>

              {/* Associated Evidence Drivers */}
              {(selectedEpisode.evidence || []).length > 0 && (
                <div>
                  <div className="text-xs font-bold mb-1.5">Supporting Telemetry / Model Evidence</div>
                  <div className="space-y-1.5">
                    {selectedEpisode.evidence.map((ev, idx) => (
                      <div
                        key={`${ev.source}-${ev.metric}-${idx}`}
                        className="rounded-lg px-2.5 py-2 text-xs spu-subcard"
                      >
                        <div className="flex items-center justify-between">
                          <span className="font-mono font-semibold">
                            [{ev.source}] {ev.metric}
                          </span>
                          <span className="font-mono text-[var(--accent-cyan)]">
                            {ev.value ?? '--'} {ev.threshold != null ? `(thr ${ev.threshold})` : ''}
                          </span>
                        </div>
                        {ev.summary && (
                          <div className="mt-1 text-[11px] spu-text-secondary">{ev.summary}</div>
                        )}
                      </div>
                    ))}
                  </div>
                </div>
              )}

              <div>
                <div className="text-xs font-bold mb-1">Recommended Diagnostic Check</div>
                <pre
                  style={{ backgroundColor: 'var(--bg-log)' }}
                  className="overflow-x-auto rounded-lg border p-2.5 font-mono text-[11px] text-amber-400 spu-border"
                >
                  {selectedEpisode.recommended_checks || selectedEpisode.playbook_cmd}
                </pre>
              </div>

              {(selectedEpisode.acknowledged_by || selectedEpisode.resolution_note) && (
                <div className="rounded-lg border spu-border p-2.5 text-xs spu-subcard space-y-1">
                  {selectedEpisode.acknowledged_by && (
                    <div>
                      <span className="spu-text-muted">Handled by:</span>{' '}
                      <strong className="font-mono">{selectedEpisode.acknowledged_by}</strong>
                    </div>
                  )}
                  {selectedEpisode.resolution_note && (
                    <div>
                      <span className="spu-text-muted">Note:</span>{' '}
                      <span>{selectedEpisode.resolution_note}</span>
                    </div>
                  )}
                </div>
              )}

              {/* Drilldown Links */}
              <div className="grid grid-cols-2 gap-2">
                <button
                  onClick={() => onInspectMonitoring(selectedEpisode.node_id)}
                  className="spu-btn-secondary inline-flex items-center justify-center gap-1.5"
                >
                  <Activity className="h-3.5 w-3.5 text-[var(--accent-cyan)]" />
                  Inspect Metrics
                </button>
                <button
                  onClick={() => onInspectLogs(selectedEpisode.node_id)}
                  className="spu-btn-secondary inline-flex items-center justify-center gap-1.5"
                >
                  <FileTerminal className="h-3.5 w-3.5 text-[var(--accent-cyan)]" />
                  Inspect Logs
                </button>
                {onInvestigateIncident && (
                  <button
                    onClick={() => onInvestigateIncident(selectedEpisode)}
                    className="spu-btn-primary col-span-2 inline-flex items-center justify-center gap-1.5"
                  >
                    <Sparkles className="h-3.5 w-3.5" />
                    Investigate Incident with Gemini AI
                  </button>
                )}
              </div>

              {/* Incident Workflow Controls */}
              {selectedEpisode.status !== 'resolved' && (
                <div className="space-y-2.5 border-t pt-3 spu-border">
                  <input
                    type="text"
                    value={actionNote}
                    onChange={(e) => setActionNote(e.target.value)}
                    placeholder="Optional investigation / resolution note..."
                    className="spu-input w-full text-xs"
                  />
                  <div className="flex flex-wrap gap-2">
                    {selectedEpisode.status === 'active' && (
                      <button
                        onClick={() => {
                          onAlertAction(selectedEpisode.id, 'acknowledge', actionNote.trim() || null);
                          setActionNote('');
                        }}
                        className="spu-btn-primary inline-flex items-center gap-1.5"
                      >
                        <CheckCircle2 className="h-3.5 w-3.5" /> Acknowledge
                      </button>
                    )}
                    <button
                      onClick={() => {
                        onAlertAction(selectedEpisode.id, 'silence', actionNote.trim() || null);
                        setActionNote('');
                      }}
                      className="spu-btn-secondary inline-flex items-center gap-1.5"
                    >
                      <VolumeX className="h-3.5 w-3.5 text-amber-400" /> Silence 30m
                    </button>
                    <button
                      onClick={() => {
                        onAlertAction(selectedEpisode.id, 'resolve', actionNote.trim() || null);
                        setActionNote('');
                      }}
                      className="spu-btn-secondary inline-flex items-center gap-1.5"
                    >
                      Resolve
                    </button>
                    <button
                      onClick={() => onRequestDrainNodeId(selectedEpisode.node_id)}
                      className="rounded-lg bg-amber-500/20 px-3 py-1.5 text-xs font-semibold text-amber-400 border border-amber-500/40 inline-flex items-center gap-1.5"
                    >
                      <ShieldOff className="h-3.5 w-3.5" /> Drain Node
                    </button>
                  </div>
                </div>
              )}
            </div>
          ) : (
            <div className="py-12 text-center text-xs spu-text-secondary">
              Select an incident from the list to inspect associated metrics, logs, and remediation controls.
            </div>
          )}
        </div>
      </section>
    </div>
  );
}
