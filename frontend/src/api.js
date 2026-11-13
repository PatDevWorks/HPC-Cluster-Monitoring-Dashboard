const API_BASE = import.meta.env.VITE_API_BASE || '';

// ---------------------------------------------------------------------------
// HTTP Helpers — Cookie-based Authentication
// ---------------------------------------------------------------------------

function buildAuthHeaders(extra = {}) {
  return {
    'Content-Type': 'application/json',
    ...extra,
  };
}

async function request(path, options = {}) {
  const res = await fetch(`${API_BASE}${path}`, {
    ...options,
    credentials: 'include',
    headers: buildAuthHeaders(options.headers || {}),
  });

  if (!res.ok) {
    const text = await res.text();

    let msg = text || `HTTP ${res.status}`;

    try {
      const parsed = JSON.parse(text);
      if (parsed?.detail) msg = parsed.detail;
    } catch {
      // Keep raw response text.
    }

    throw new Error(msg);
  }

  return res.json();
}

// ---------------------------------------------------------------------------
// API
// ---------------------------------------------------------------------------

export const api = {
  // Authentication — Login, OTP, Registration and Sessions

  login: (email, password) =>
    request('/api/auth/login', {
      method: 'POST',
      body: JSON.stringify({ email, password }),
    }),

  verifyOtp: (email, code) =>
    request('/api/auth/verify-otp', {
      method: 'POST',
      body: JSON.stringify({ email, code }),
    }),

  getMe: () =>
    request('/api/auth/me'),

  logout: () =>
    request('/api/auth/logout', {
      method: 'POST',
    }),

  register: (token, full_name, password) =>
    request('/api/auth/register', {
      method: 'POST',
      body: JSON.stringify({
        token,
        full_name,
        password,
      }),
    }),

  verifyEmail: (email, code) =>
    request('/api/auth/verify-email', {
      method: 'POST',
      body: JSON.stringify({ email, code }),
    }),

  resendVerification: (email) =>
    request('/api/auth/resend-verification', {
      method: 'POST',
      body: JSON.stringify({ email }),
    }),

  createInvitation: (email, role, validity_hours = 48) =>
    request('/api/auth/invitations', {
      method: 'POST',
      body: JSON.stringify({
        email,
        role,
        validity_hours,
      }),
    }),

  // Core Pipeline & Cluster State

  getState: () =>
    request('/api/state'),

  refreshState: () =>
    request('/api/state/refresh', {
      method: 'POST',
    }),

  reloadModels: () =>
    request('/api/models/reload', {
      method: 'POST',
    }),

  switchMode: (mode, prometheus_url = null, preset_id = null) =>
    request('/api/mode', {
      method: 'POST',
      body: JSON.stringify({
        mode,
        prometheus_url,
        preset_id,
      }),
    }),

  togglePause: () =>
    request('/api/stream/pause', {
      method: 'POST',
    }),

  // Live Monitoring & Historical Range Queries

  getMonitoringHistory: (rangeKey = '1h', nodeId = null) => {
    const q = new URLSearchParams({
      range_key: rangeKey,
    });

    if (nodeId) q.set('node_id', nodeId);

    return request(`/api/monitoring/history?${q.toString()}`);
  },

  // Slurm & Workload Controls

  drainNode: (node_id, reason) =>
    request('/api/slurm/drain', {
      method: 'POST',
      body: JSON.stringify({
        node_id,
        reason,
      }),
    }),

  resumeNode: (node_id) =>
    request('/api/slurm/resume', {
      method: 'POST',
      body: JSON.stringify({
        node_id,
      }),
    }),

  cancelJob: (job_id, reason) =>
    request('/api/slurm/cancel', {
      method: 'POST',
      body: JSON.stringify({
        job_id,
        reason,
      }),
    }),

  getSlurmAudit: () =>
    request('/api/slurm/audit'),

  // Node Logs

  getNodeLogs: ({
    nodeId,
    category,
    lines = 200,
    keyword = '',
    severity = 'ALL',
    since = '',
    until = '',
  }) => {
    const q = new URLSearchParams({
      node_id: nodeId,
      category,
      lines: String(lines),
    });

    if (keyword) q.set('keyword', keyword);
    if (severity && severity !== 'ALL') q.set('severity', severity);
    if (since) q.set('since', since);
    if (until) q.set('until', until);

    return request(`/api/logs?${q.toString()}`);
  },

  getSingleLogDownloadUrl: ({
    nodeId,
    category,
    lines = 500,
    keyword = '',
    severity = 'ALL',
  }) => {
    const q = new URLSearchParams({
      node_id: nodeId,
      category,
      lines: String(lines),
    });

    if (keyword) q.set('keyword', keyword);
    if (severity && severity !== 'ALL') q.set('severity', severity);

    return `${API_BASE}/api/logs/download?${q.toString()}`;
  },

  downloadSelectedLogsZip: async ({
    nodeId,
    categories,
    lines = 300,
    keyword = '',
    severity = '',
  }) => {
    const res = await fetch(`${API_BASE}/api/logs/download-zip`, {
      method: 'POST',
      credentials: 'include',
      headers: buildAuthHeaders(),
      body: JSON.stringify({
        node_id: nodeId,
        categories,
        lines,
        keyword: keyword || null,
        severity:
          severity && severity !== 'ALL'
            ? severity
            : null,
      }),
    });

    if (!res.ok) {
      const text = await res.text();

      let msg = text || `HTTP ${res.status}`;

      try {
        const parsed = JSON.parse(text);
        if (parsed?.detail) msg = parsed.detail;
      } catch {
        // Keep raw response text.
      }

      throw new Error(msg);
    }

    const blob = await res.blob();

    const cd = res.headers.get('Content-Disposition') || '';
    const match = cd.match(/filename="([^"]+)"/);

    const filename = match
      ? match[1]
      : `${nodeId}_selected_logs.zip`;

    const url = URL.createObjectURL(blob);

    const a = document.createElement('a');
    a.href = url;
    a.download = filename;

    document.body.appendChild(a);
    a.click();
    a.remove();

    URL.revokeObjectURL(url);
  },

  // Diagnostic Bundles

  getNodeDiagnosticBundleUrl: (nodeId) =>
    `${API_BASE}/api/diagnostics/node/${encodeURIComponent(nodeId)}`,

  getClusterDiagnosticBundleUrl: () =>
    `${API_BASE}/api/diagnostics/cluster`,

  // Audited Instance Terminal Console

  getTerminalPresets: () =>
    request('/api/terminal/presets'),

  execTerminalCommand: (node_id, command, confirmed = false) =>
    request('/api/terminal/exec', {
      method: 'POST',
      body: JSON.stringify({
        node_id,
        command,
        confirmed,
      }),
    }),

  // Performance Analytics & Reports

  getAnalyticsSummary: (rangeKey = '1h') =>
    request(
      `/api/analytics/summary?range_key=${encodeURIComponent(rangeKey)}`
    ),

  previewReport: (
    reportType = 'cluster_summary',
    rangeMinutes = 60
  ) =>
    request(
      `/api/reports/preview?report_type=${encodeURIComponent(reportType)}&range_minutes=${rangeMinutes}`
    ),

  getReportExportUrl: (
    reportType = 'cluster_summary',
    format = 'csv',
    rangeMinutes = 60
  ) =>
    `${API_BASE}/api/reports/export?report_type=${encodeURIComponent(
      reportType
    )}&format=${encodeURIComponent(
      format
    )}&range_minutes=${rangeMinutes}`,

  // Fault Injection Demo Lab & Alert Triage

  injectFault: (node_id, fault_type) =>
    request('/api/fault-inject', {
      method: 'POST',
      body: JSON.stringify({
        node_id,
        fault_type,
      }),
    }),

  clearFaults: (node_id = null) =>
    request('/api/fault-clear', {
      method: 'POST',
      body: JSON.stringify({
        node_id,
      }),
    }),

  alertAction: (episode_id, action) =>
    request(`/api/alerts/${episode_id}/action`, {
      method: 'POST',
      body: JSON.stringify({
        action,
      }),
    }),

  // Settings & Service Health

  getSettings: () =>
    request('/api/settings'),

  updateSettings: (payload) =>
    request('/api/settings', {
      method: 'PUT',
      body: JSON.stringify(payload),
    }),

  testPrometheus: (prometheus_url) =>
    request('/api/settings/test-prometheus', {
      method: 'POST',
      body: JSON.stringify({
        prometheus_url,
      }),
    }),
};

// ---------------------------------------------------------------------------
// Live WebSocket — Authenticated Session Cookie
// ---------------------------------------------------------------------------

export function createLiveSocket(onMessage, onStatusChange) {
  let ws = null;
  let retryTimer = null;
  let closedByApp = false;

  const connect = () => {
    if (closedByApp) return;

    const proto =
      window.location.protocol === 'https:'
        ? 'wss:'
        : 'ws:';

    const wsUrl =
      import.meta.env.VITE_WS_URL ||
      `${proto}//${window.location.host}/ws/live`;

    ws = new WebSocket(wsUrl);

    ws.onopen = () => {
      onStatusChange(true);
    };

    ws.onmessage = (ev) => {
      try {
        const data = JSON.parse(ev.data);
        onMessage(data);
      } catch {
        // Ignore malformed WebSocket messages.
      }
    };

    ws.onclose = () => {
      onStatusChange(false);

      if (!closedByApp) {
        retryTimer = setTimeout(connect, 2500);
      }
    };

    ws.onerror = () => {
      ws.close();
    };
  };

  connect();

  return () => {
    closedByApp = true;

    if (retryTimer) {
      clearTimeout(retryTimer);
    }

    if (ws) {
      ws.close();
    }
  };
}