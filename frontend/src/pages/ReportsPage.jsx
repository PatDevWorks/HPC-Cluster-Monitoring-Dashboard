import React, { useEffect, useState } from 'react';
import {
  Download,
  FileSpreadsheet,
  FileText,
  FolderArchive,
  RefreshCw,
} from 'lucide-react';
import { api } from '../api.js';

const REPORT_TEMPLATES = [
  {
    id: 'cluster_summary',
    label: 'Executive Cluster Health Summary',
    desc: 'Node availability, Slurm states, CPU/memory utilisation and current 1h AI failure risk.',
  },
  {
    id: 'ai_predictions',
    label: 'AI Failure Predictions & Consensus Audit',
    desc: 'Per-node 1h/6h failure probabilities, 4-model anomaly consensus votes and classifications.',
  },
  {
    id: 'performance_history',
    label: 'Historical Performance & Telemetry Log',
    desc: 'Chronological cluster & node telemetry records over the selected time window.',
  },
  {
    id: 'slurm_workload',
    label: 'Slurm Workload & Admin Audit Trail',
    desc: 'Active/historical Slurm jobs combined with recorded administrative actions.',
  },
  {
    id: 'alerts_incidents',
    label: 'Alerts & Incident History Report',
    desc: 'All critical, warning and watch episodes with timestamps, fault classes and status.',
  },
];

export default function ReportsPage({ snapshot }) {
  const [reportType, setReportType] = useState('cluster_summary');
  const [rangeMinutes, setRangeMinutes] = useState(60);
  const [preview, setPreview] = useState(null);
  const [loading, setLoading] = useState(false);

  const loadPreview = async () => {
    setLoading(true);
    try {
      const res = await api.previewReport(reportType, rangeMinutes);
      setPreview(res);
    } catch {
      setPreview(null);
    } finally {
      setLoading(false);
    }
  };

  useEffect(() => {
    loadPreview();
  }, [reportType, rangeMinutes, snapshot?.mode]);

  return (
    <div className="space-y-5">
      {/* Header */}
      <div className="flex flex-wrap items-center justify-between gap-3">
        <div className="flex items-center gap-3">
          <div className="flex h-10 w-10 items-center justify-center rounded-xl bg-cyan-500/15 text-[var(--accent-cyan)]">
            <FileSpreadsheet className="h-5 w-5" />
          </div>
          <div>
            <h2 className="text-xl font-bold tracking-tight">Reports</h2>
            <p className="text-xs spu-text-secondary">
              Exportable CSV, PDF &amp; sanitized cluster diagnostic reports
            </p>
          </div>
        </div>

        <div className="flex flex-wrap items-center gap-2">
          <select
            value={rangeMinutes}
            onChange={(e) => setRangeMinutes(Number(e.target.value))}
            className="spu-input text-xs"
          >
            <option value={15}>Last 15 Minutes</option>
            <option value={60}>Last 1 Hour</option>
            <option value={360}>Last 6 Hours</option>
            <option value={1440}>Last 24 Hours</option>
          </select>

          <a
            href={api.getReportExportUrl(reportType, 'csv', rangeMinutes)}
            className="spu-btn-secondary inline-flex items-center gap-1.5"
          >
            <Download className="h-3.5 w-3.5 text-[var(--accent-cyan)]" />
            Download CSV
          </a>

          <a
            href={api.getReportExportUrl(reportType, 'pdf', rangeMinutes)}
            className="spu-btn-primary inline-flex items-center gap-1.5"
          >
            <FileText className="h-3.5 w-3.5" />
            Download PDF
          </a>

          <a
            href={api.getClusterDiagnosticBundleUrl()}
            className="spu-btn-secondary inline-flex items-center gap-1.5"
          >
            <FolderArchive className="h-3.5 w-3.5 text-emerald-400" />
            Full Diagnostic ZIP
          </a>
        </div>
      </div>

      {/* Report Template Selector */}
      <section className="grid grid-cols-1 gap-3 sm:grid-cols-2 xl:grid-cols-5">
        {REPORT_TEMPLATES.map((tpl) => {
          const active = reportType === tpl.id;
          return (
            <button
              key={tpl.id}
              onClick={() => setReportType(tpl.id)}
              className={`spu-card p-3.5 text-left transition ${
                active
                  ? 'ring-2 ring-[var(--accent-cyan)]'
                  : 'hover:border-[var(--accent-cyan)]'
              }`}
            >
              <div className="text-xs font-bold">{tpl.label}</div>
              <p className="mt-1 text-[11px] leading-snug spu-text-secondary">
                {tpl.desc}
              </p>
            </button>
          );
        })}
      </section>

      {/* Live Executive Preview Table */}
      <section className="spu-card p-5">
        <div className="mb-3 flex flex-wrap items-center justify-between gap-2 border-b pb-3 spu-border">
          <div>
            <h3 className="text-sm font-bold">
              {preview?.title || 'Generating Report Preview...'}
            </h3>
            <p className="text-xs spu-text-secondary">
              Generated UTC: <span className="font-mono">{preview?.generated_utc || '--'}</span> •{' '}
              {(preview?.rows || []).length} record(s)
            </p>
          </div>
          <button
            onClick={loadPreview}
            disabled={loading}
            className="spu-btn-secondary inline-flex items-center gap-1.5"
          >
            <RefreshCw className={`h-3.5 w-3.5 ${loading ? 'animate-spin' : ''}`} />
            Refresh Preview
          </button>
        </div>

        <div className="overflow-x-auto max-h-[440px]">
          <table className="w-full text-left text-xs">
            <thead>
              <tr className="border-b spu-border spu-text-secondary">
                {(preview?.columns || []).map((col) => (
                  <th key={col} className="py-2.5 pr-4 font-semibold">
                    {col}
                  </th>
                ))}
              </tr>
            </thead>
            <tbody className="divide-y spu-border font-mono text-[11.5px]">
              {(preview?.rows || []).length === 0 ? (
                <tr>
                  <td
                    colSpan={(preview?.columns || []).length || 1}
                    className="py-8 text-center font-sans spu-text-secondary"
                  >
                    No records available for this report window.
                  </td>
                </tr>
              ) : (
                preview.rows.slice(0, 100).map((row, idx) => (
                  <tr key={idx} className="hover:bg-[var(--bg-hover)]">
                    {row.map((cell, cIdx) => (
                      <td key={cIdx} className="py-2 pr-4">
                        {cell}
                      </td>
                    ))}
                  </tr>
                ))
              )}
            </tbody>
          </table>
        </div>
      </section>
    </div>
  );
}
