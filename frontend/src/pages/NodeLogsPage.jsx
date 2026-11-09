import React, { useEffect, useState } from 'react';
import {
  Archive,
  Download,
  FileTerminal,
  FolderArchive,
  RefreshCw,
  Search,
  ShieldCheck,
  Terminal,
} from 'lucide-react';
import { api } from '../api.js';

const DEFAULT_CATEGORIES = [
  { id: 'system', label: 'System Logs (journalctl)' },
  { id: 'kernel', label: 'Kernel Logs (dmesg / journal -k)' },
  { id: 'auth', label: 'Authentication Logs' },
  { id: 'slurmctld', label: 'Slurm Controller (slurmctld)' },
  { id: 'slurmd', label: 'Slurm Compute Daemon (slurmd)' },
  { id: 'node_exporter', label: 'Node Exporter' },
  { id: 'monitoring', label: 'Monitoring Services' },
];

export default function NodeLogsPage({
  snapshot,
  selectedNodeId,
  onSelectNode,
  onOpenTerminal,
  showToast,
}) {
  const nodes = snapshot?.nodes || [];
  const activeNodeId =
    nodes.find((n) => n.node_id === selectedNodeId)?.node_id ||
    nodes[0]?.node_id ||
    'head-node';

  const [category, setCategory] = useState('system');
  const [selectedZipCats, setSelectedZipCats] = useState(['system', 'kernel', 'slurmd']);
  const [keyword, setKeyword] = useState('');
  const [severity, setSeverity] = useState('ALL');
  const [since, setSince] = useState('');
  const [until, setUntil] = useState('');
  const [lines, setLines] = useState(200);
  const [logPayload, setLogPayload] = useState(null);
  const [loading, setLoading] = useState(false);
  const [zipBusy, setZipBusy] = useState(false);

  const loadLogs = async () => {
    setLoading(true);
    try {
      const res = await api.getNodeLogs({
        nodeId: activeNodeId,
        category,
        lines,
        keyword,
        severity,
        since,
        until,
      });
      setLogPayload(res);
    } catch (err) {
      showToast(`Log retrieval failed: ${err.message}`);
    } finally {
      setLoading(false);
    }
  };

  useEffect(() => {
    loadLogs();
  }, [activeNodeId, category, severity, lines]);

  const toggleZipCategory = (catId) => {
    setSelectedZipCats((prev) =>
      prev.includes(catId) ? prev.filter((c) => c !== catId) : [...prev, catId]
    );
  };

  const handleDownloadSelectedZip = async () => {
    if (selectedZipCats.length === 0) {
      showToast('Select at least one log category for ZIP export');
      return;
    }
    setZipBusy(true);
    try {
      await api.downloadSelectedLogsZip({
        nodeId: activeNodeId,
        categories: selectedZipCats,
        lines: 350,
        keyword,
        severity,
      });
      showToast(`Downloaded ${selectedZipCats.length} log categories as ZIP`);
    } catch (err) {
      showToast(`ZIP export failed: ${err.message}`);
    } finally {
      setZipBusy(false);
    }
  };

  const entries = logPayload?.entries || [];

  return (
    <div className="space-y-5">
      {/* Header + Bundle Actions */}
      <div className="flex flex-wrap items-center justify-between gap-3">
        <div className="flex items-center gap-3">
          <div className="flex h-10 w-10 items-center justify-center rounded-xl bg-cyan-500/15 text-[var(--accent-cyan)]">
            <FileTerminal className="h-5 w-5" />
          </div>
          <div>
            <h2 className="text-xl font-bold tracking-tight">
              Node Logs &amp; Diagnostics
            </h2>
            <p className="text-xs spu-text-secondary">
              Restricted SSH log inspection, keyword/severity filtering &amp; sanitized diagnostic bundles
            </p>
          </div>
        </div>

        {/* Node & Cluster Diagnostic Bundle Downloads */}
        <div className="flex flex-wrap items-center gap-2">
          {onOpenTerminal && (
            <button
              onClick={() => onOpenTerminal(activeNodeId)}
              className="spu-btn-secondary inline-flex items-center gap-1.5"
            >
              <Terminal className="h-3.5 w-3.5 text-[var(--accent-cyan)]" />
              Instance Terminal
            </button>
          )}
          <a
            href={api.getNodeDiagnosticBundleUrl(activeNodeId)}
            className="spu-btn-secondary inline-flex items-center gap-1.5"
          >
            <Archive className="h-3.5 w-3.5 text-[var(--accent-cyan)]" />
            Node Diagnostic Bundle (.zip)
          </a>

          <a
            href={api.getClusterDiagnosticBundleUrl()}
            className="spu-btn-primary inline-flex items-center gap-1.5"
          >
            <FolderArchive className="h-3.5 w-3.5" />
            Cluster Diagnostic Bundle (.zip)
          </a>
        </div>
      </div>

      {/* Node Selector Tabs */}
      <div className="flex flex-wrap gap-2">
        {nodes.map((n) => (
          <button
            key={n.node_id}
            onClick={() => onSelectNode(n.node_id)}
            className={`inline-flex items-center gap-2 rounded-xl border px-3.5 py-2 text-xs font-semibold transition ${
              n.node_id === activeNodeId
                ? 'border-[var(--accent-cyan)] bg-cyan-500/12 text-[var(--accent-cyan)]'
                : 'spu-card spu-text-secondary hover:text-[var(--text-primary)]'
            }`}
          >
            <span
              className={`h-2 w-2 rounded-full ${
                n.up === 1 ? 'bg-emerald-400' : 'bg-rose-500'
              }`}
            />
            {n.display_name || n.node_id}
            <span className="font-mono text-[10px] opacity-75">{n.ip}</span>
          </button>
        ))}
      </div>

      {/* Category Picker + Filter Controls */}
      <div className="spu-card p-4 space-y-4">
        {/* Category Pills */}
        <div className="flex flex-wrap gap-1.5">
          {DEFAULT_CATEGORIES.map((cat) => (
            <button
              key={cat.id}
              onClick={() => setCategory(cat.id)}
              className={`rounded-lg px-3 py-1.5 text-xs font-semibold transition ${
                category === cat.id
                  ? 'bg-[var(--accent-cyan-strong)] text-white'
                  : 'spu-subcard spu-text-secondary hover:text-[var(--text-primary)]'
              }`}
            >
              {cat.label}
            </button>
          ))}
        </div>

        {/* Search, Severity, Date/Time Filters */}
        <form
          onSubmit={(e) => {
            e.preventDefault();
            loadLogs();
          }}
          className="grid grid-cols-1 gap-2.5 sm:grid-cols-2 lg:grid-cols-6"
        >
          <div className="relative lg:col-span-2">
            <Search className="pointer-events-none absolute left-3 top-2.5 h-3.5 w-3.5 spu-text-muted" />
            <input
              type="text"
              value={keyword}
              onChange={(e) => setKeyword(e.target.value)}
              placeholder="Search keyword (e.g. error, oom, rank, ssh)..."
              className="spu-input w-full pl-8"
            />
          </div>

          <select
            value={severity}
            onChange={(e) => setSeverity(e.target.value)}
            className="spu-input"
          >
            <option value="ALL">All Severities</option>
            <option value="ERROR">Critical / Error</option>
            <option value="WARNING">Warning</option>
            <option value="INFO">Informational</option>
          </select>

          <input
            type="datetime-local"
            value={since}
            onChange={(e) => setSince(e.target.value)}
            title="Start date/time filter"
            className="spu-input text-xs"
          />

          <input
            type="datetime-local"
            value={until}
            onChange={(e) => setUntil(e.target.value)}
            title="End date/time filter"
            className="spu-input text-xs"
          />

          <div className="flex items-center gap-2">
            <select
              value={lines}
              onChange={(e) => setLines(Number(e.target.value))}
              className="spu-input flex-1"
            >
              <option value={100}>100 lines</option>
              <option value={200}>200 lines</option>
              <option value={500}>500 lines</option>
            </select>
            <button
              type="submit"
              disabled={loading}
              className="spu-btn-primary inline-flex items-center gap-1.5"
            >
              <RefreshCw className={`h-3.5 w-3.5 ${loading ? 'animate-spin' : ''}`} />
              Query
            </button>
          </div>
        </form>

        {/* Individual & Multi-Log ZIP Export Bar */}
        <div className="flex flex-wrap items-center justify-between gap-3 border-t pt-3 spu-border text-xs">
          <div className="flex flex-wrap items-center gap-2">
            <span className="font-semibold spu-text-secondary">
              Multi-Log ZIP Selection:
            </span>
            {DEFAULT_CATEGORIES.map((c) => (
              <label
                key={c.id}
                className="inline-flex cursor-pointer items-center gap-1 rounded px-2 py-1 spu-subcard"
              >
                <input
                  type="checkbox"
                  checked={selectedZipCats.includes(c.id)}
                  onChange={() => toggleZipCategory(c.id)}
                />
                <span>{c.id}</span>
              </label>
            ))}
          </div>

          <div className="flex items-center gap-2">
            <a
              href={api.getSingleLogDownloadUrl({
                nodeId: activeNodeId,
                category,
                lines,
                keyword,
                severity,
              })}
              className="spu-btn-secondary inline-flex items-center gap-1.5"
            >
              <Download className="h-3.5 w-3.5" />
              Download .log
            </a>

            <button
              onClick={handleDownloadSelectedZip}
              disabled={zipBusy}
              className="spu-btn-secondary inline-flex items-center gap-1.5"
            >
              <Archive className="h-3.5 w-3.5 text-[var(--accent-cyan)]" />
              {zipBusy ? 'Packaging...' : `Download Selected (${selectedZipCats.length}) .zip`}
            </button>
          </div>
        </div>
      </div>

      {/* Log Stream Output Viewer */}
      <div className="spu-card p-4">
        <div className="mb-2.5 flex flex-wrap items-center justify-between gap-2 text-xs">
          <div className="flex items-center gap-2">
            <ShieldCheck className="h-4 w-4 text-emerald-400" />
            <span>
              Source Mode:{' '}
              <strong className="font-mono">
                {logPayload?.source_mode || 'loading'}
              </strong>{' '}
              • {entries.length} sanitized entries
            </span>
          </div>
          {logPayload?.notice && (
            <span className="text-[11px] spu-text-muted">{logPayload.notice}</span>
          )}
        </div>

        <div
          style={{ backgroundColor: 'var(--bg-log)' }}
          className="max-h-[460px] overflow-y-auto rounded-xl border p-3 font-mono text-[11.5px] spu-border space-y-1"
        >
          {entries.length === 0 ? (
            <div className="py-10 text-center spu-text-secondary font-sans text-xs">
              No log entries match your current filter criteria on {activeNodeId}.
            </div>
          ) : (
            entries.map((entry) => (
              <div
                key={entry.id}
                className="flex flex-wrap items-start gap-2 rounded px-2 py-1 hover:bg-[var(--bg-hover)]"
              >
                <span className="shrink-0 spu-text-muted">
                  {entry.timestamp?.slice(0, 19).replace('T', ' ')}
                </span>
                <span
                  className={`shrink-0 rounded px-1.5 py-0.2 text-[10px] font-bold ${
                    entry.severity === 'ERROR'
                      ? 'bg-rose-500/20 text-rose-400'
                      : entry.severity === 'WARNING'
                      ? 'bg-amber-500/20 text-amber-400'
                      : 'bg-cyan-500/15 text-[var(--accent-cyan)]'
                  }`}
                >
                  {entry.severity}
                </span>
                <span className="shrink-0 spu-text-secondary">[{entry.source}]</span>
                <span className="break-all">{entry.message}</span>
              </div>
            ))
          )}
        </div>
      </div>
    </div>
  );
}
