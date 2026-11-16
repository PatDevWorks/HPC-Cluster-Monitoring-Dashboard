import React, { useEffect, useState } from 'react';
import {
  Download,
  FileSpreadsheet,
  FileText,
  FolderArchive,
  RefreshCw,
  Sparkles, Copy, CheckCircle2, Clock,
} from 'lucide-react';
import { api } from '../api.js';

const REPORT_TEMPLATES = [
  {
    id: 'cluster_summary',
    label: 'Executive Cluster Health Summary',
    desc: 'Node availability, Slurm states, CPU/memory utilisation and active operational alerts.',
  },
  {
    id: 'ai_predictions',
    label: 'AI Model Status Audit (V7 IF & LSTM V8)',
    desc: 'Per-node V7 Isolation Forest anomaly scores, thresholds, and LSTM V8 temporal warning states reported separately.',
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
  {
    id: 'experiment_evaluation',
    label: 'Experiment & Model Evaluation Report',
    desc: 'Labelled failure-injection experiments, V7 vs LSTM V8 vs telemetry baseline coverage & false alarms.',
  },
];

export default function ReportsPage({ snapshot, user, showToast }) {
  const [reportType, setReportType] = useState('cluster_summary');
  const [rangeMinutes, setRangeMinutes] = useState(60);
  const [preview, setPreview] = useState(null);
  const [loading, setLoading] = useState(false);
  const [aiArchive, setAiArchive] = useState([]);
  const [selectedAiReport, setSelectedAiReport] = useState(null);
  const [generatingAi, setGeneratingAi] = useState(false);

  const loadAiArchive = async () => {
    try {
      const res = await api.getAiReportArchive(15);
      const list = Array.isArray(res) ? res : res?.reports || [];
      setAiArchive(list);
    } catch {
      // Ignore if archive unavailable
    }
  };

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

  useEffect(() => {
    loadAiArchive();
  }, []);

  useEffect(() => {
    const hasPending = aiArchive.some((r) => r.status === 'pending' || r.status === 'generating');
    if (!hasPending) return undefined;
    const timer = setInterval(loadAiArchive, 3000);
    return () => clearInterval(timer);
  }, [aiArchive]);

  const handleGenerateAiReport = async () => {
    setGeneratingAi(true);
    try {
      const res = await api.generateAiReport(reportType, rangeMinutes);
      showToast?.('Started Gemini AI report synthesis in background');
      await loadAiArchive();
      const repId = res?.report_id || res?.id;
      if (repId) {
        setTimeout(async () => {
          await loadAiArchive();
          try {
            const det = await api.getAiReportDetails(repId);
            setSelectedAiReport(det?.report || det);
          } catch {}
        }, 2500);
      }
    } catch (err) {
      showToast?.(`AI report generation error: ${err.message}`);
    } finally {
      setGeneratingAi(false);
    }
  };

  const handleOpenAiReport = async (repId) => {
    try {
      const det = await api.getAiReportDetails(repId);
      setSelectedAiReport(det?.report || det);
    } catch (err) {
      showToast?.(`Could not load AI report #${repId}: ${err.message}`);
    }
  };

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
      <section className="grid grid-cols-1 gap-3 sm:grid-cols-2 lg:grid-cols-3">
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

      {/* Gemini AI Operational & Research Report Generator + Archive */}
      <section className="spu-card p-5 space-y-4">
        <div className="flex flex-wrap items-center justify-between gap-3 border-b pb-3 spu-border">
          <div className="flex items-center gap-2.5">
            <Sparkles className="h-5 w-5 text-[var(--accent-cyan)]" />
            <div>
              <h3 className="text-sm font-bold">Gemini AI Operational &amp; Research Reports</h3>
              <p className="text-xs spu-text-secondary">
                Generate narrative analysis grounded directly in observed Prometheus telemetry, V7 scores, LSTM V8 state &amp; Slurm logs
              </p>
            </div>
          </div>
          <button
            type="button"
            disabled={generatingAi}
            onClick={handleGenerateAiReport}
            className="spu-btn-primary inline-flex items-center gap-1.5 text-xs"
          >
            <Sparkles className="h-3.5 w-3.5" />
            {generatingAi ? 'Submitting...' : `Generate Gemini Report (${reportType})`}
          </button>
        </div>

        <div className="grid grid-cols-1 gap-4 lg:grid-cols-12">
          <div className="space-y-2 lg:col-span-5 max-h-96 overflow-y-auto pr-1">
            {aiArchive.length === 0 ? (
              <div className="rounded-lg border spu-border p-4 text-xs spu-text-muted">
                No Gemini AI reports generated yet. Select a template above and click Generate Gemini Report.
              </div>
            ) : (
              aiArchive.map((item) => (
                <button
                  key={item.id}
                  type="button"
                  onClick={() => handleOpenAiReport(item.id)}
                  className={`w-full rounded-xl border p-3 text-left transition spu-subcard ${
                    selectedAiReport?.id === item.id ? 'border-[var(--accent-cyan)]' : 'hover:border-[var(--accent-cyan)]'
                  }`}
                >
                  <div className="flex items-center justify-between gap-2">
                    <span className="font-semibold text-xs truncate">{item.title || item.report_type}</span>
                    <span
                      className={`rounded px-1.5 py-0.5 font-mono text-[10px] uppercase ${
                        item.status === 'completed'
                          ? 'bg-emerald-500/15 text-emerald-400'
                          : item.status === 'failed'
                          ? 'bg-rose-500/15 text-rose-400'
                          : 'bg-amber-500/15 text-amber-400'
                      }`}
                    >
                      {item.status}
                    </span>
                  </div>
                  <div className="mt-1 flex items-center justify-between text-[10.5px] font-mono spu-text-muted">
                    <span>{item.model || 'gemini'}</span>
                    <span>{item.created_utc?.slice(0, 19).replace('T', ' ')}Z</span>
                  </div>
                </button>
              ))
            )}
          </div>

          <div className="spu-subcard p-4 lg:col-span-7 min-h-[16rem] max-h-96 overflow-y-auto">
            {selectedAiReport ? (
              <div className="space-y-3">
                <div className="flex flex-wrap items-center justify-between gap-2 border-b pb-2 spu-border">
                  <div>
                    <h4 className="text-sm font-bold">{selectedAiReport.title}</h4>
                    <div className="font-mono text-[10.5px] spu-text-muted">
                      Model: {selectedAiReport.model} • Mode: {selectedAiReport.data_mode} • Status: {selectedAiReport.status}
                    </div>
                  </div>
                  {selectedAiReport.report_text && (
                    <button
                      type="button"
                      onClick={() => {
                        navigator.clipboard?.writeText(selectedAiReport.report_text);
                        showToast?.('Copied AI report markdown to clipboard');
                      }}
                      className="spu-btn-secondary inline-flex items-center gap-1 text-xs"
                    >
                      <Copy className="h-3 w-3" /> Copy Markdown
                    </button>
                  )}
                </div>
                <pre className="whitespace-pre-wrap font-sans text-xs leading-relaxed spu-text-secondary">
                  {selectedAiReport.report_text || 'Report is still generating or has no text payload.'}
                </pre>
              </div>
            ) : (
              <div className="flex h-full min-h-[14rem] items-center justify-center text-xs spu-text-muted">
                Select an archived Gemini report on the left to inspect its structured analysis.
              </div>
            )}
          </div>
        </div>
      </section>
    </div>
  );
}
