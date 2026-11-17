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

  setFirstLoginPassword: (password) =>
    request('/api/auth/first-login/password', {
      method: 'POST',
      body: JSON.stringify({ password }),
    }),

  getFirstLoginStatus: () =>
    request('/api/auth/first-login/status'),

  resendFirstLoginOtp: () =>
    request('/api/auth/first-login/resend-otp', { method: 'POST' }),

  reissueTemporaryPassword: (user_id) =>
    request('/api/auth/temporary-password/reissue', {
      method: 'POST',
      body: JSON.stringify({ user_id }),
    }),

  getMe: () =>
    request('/api/auth/me'),

  updateProfile: (full_name) =>
    request('/api/auth/profile', {
      method: 'PATCH',
      body: JSON.stringify({ full_name }),
    }),

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

  submitJob: (script) =>
    request('/api/slurm/submit', { method: 'POST', body: JSON.stringify({ script }) }),

  resubmitJob: (job_id) =>
    request(`/api/slurm/jobs/${encodeURIComponent(job_id)}/resubmit`, { method: 'POST' }),

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

  getAlerts: (params = {}) => {
    const q = new URLSearchParams();
    Object.entries(params).forEach(([k, v]) => {
      if (v) q.set(k, String(v));
    });
    const qs = q.toString();
    return request(`/api/alerts${qs ? `?${qs}` : ''}`);
  },

  alertAction: (episode_id, action, note = null) =>
    request(`/api/alerts/${episode_id}/action`, {
      method: 'POST',
      body: JSON.stringify({
        action,
        ...(note ? { note } : {}),
      }),
    }),

  // Monitoring Export

  getMonitoringExportUrl: (rangeKey = '1h', nodeId = null) => {
    const q = new URLSearchParams({ range_key: rangeKey });
    if (nodeId) q.set('node_id', nodeId);
    return `${API_BASE}/api/monitoring/export?${q.toString()}`;
  },

  // AI Models — V7 Isolation Forest, LSTM V8 & Evaluation

  getModelRegistry: () => request('/api/models/registry'),
  getModelSummary: () => request('/api/models/summary'),
  getModelHealth: () => request('/api/models/health'),
  getModelObservations: (filters = {}) => {
    const q = new URLSearchParams();
    Object.entries(filters).forEach(([key, value]) => {
      if (value !== null && value !== undefined && value !== '') q.set(key, String(value));
    });
    return request(`/api/models/observations${q.size ? `?${q.toString()}` : ''}`);
  },
  getModelRetention: () => request('/api/models/retention'),
  updateModelRetention: (retention_days) => request('/api/models/retention', {
    method: 'PUT',
    body: JSON.stringify({ retention_days }),
  }),
  registerModel: (model) => request('/api/models/registry', {
    method: 'POST',
    body: JSON.stringify(model),
  }),

  getModelsStatus: () =>
    request('/api/models/status'),

  getV7Scores: () =>
    request('/api/models/v7/scores'),

  toggleV7Integration: (enabled) =>
    request('/api/models/v7/toggle', {
      method: 'POST',
      body: JSON.stringify({ enabled: Boolean(enabled) }),
    }),

  refreshV7Scores: () =>
    request('/api/models/v7/refresh', { method: 'POST' }),

  getLstmV8State: () =>
    request('/api/models/lstm-v8/state'),

  toggleLstmV8Integration: (enabled) =>
    request('/api/models/lstm-v8/toggle', {
      method: 'POST',
      body: JSON.stringify({ enabled: Boolean(enabled) }),
    }),

  refreshLstmV8State: () =>
    request('/api/models/lstm-v8/refresh', { method: 'POST' }),

  getModelsEvaluation: () =>
    request('/api/models/evaluation'),

  // Experiments & Evaluation

  getExperiments: (category = null) => {
    const qs = category ? `?category=${encodeURIComponent(category)}` : '';
    return request(`/api/experiments${qs}`);
  },

  createExperiment: (payload) =>
    request('/api/experiments', {
      method: 'POST',
      body: JSON.stringify(payload),
    }),

  updateExperiment: (id, payload) =>
    request(`/api/experiments/${id}`, {
      method: 'PUT',
      body: JSON.stringify(payload),
    }),

  deleteExperiment: (id) =>
    request(`/api/experiments/${id}`, { method: 'DELETE' }),

  // AI Intelligence Centre (Gemini LLM) & AI Reports

  getAiHistory: (sessionId = 'default', limit = 80) =>
    request(`/api/ai/history?session_id=${encodeURIComponent(sessionId)}&limit=${limit}`),

  getAiConversations: (search = '') => {
    const query = search ? `?search=${encodeURIComponent(search)}` : '';
    return request(`/api/ai/conversations${query}`);
  },

  createAiConversation: (provider = 'gemini', title = 'New conversation') =>
    request('/api/ai/conversations', {
      method: 'POST',
      body: JSON.stringify({ provider, title }),
    }),

  updateAiConversation: (sessionId, payload) =>
    request(`/api/ai/conversations/${encodeURIComponent(sessionId)}`, {
      method: 'PATCH',
      body: JSON.stringify(payload),
    }),

  clearAiConversation: (sessionId) =>
    request(`/api/ai/conversations/${encodeURIComponent(sessionId)}/messages`, { method: 'DELETE' }),

  deleteAiConversation: (sessionId) =>
    request(`/api/ai/conversations/${encodeURIComponent(sessionId)}`, { method: 'DELETE' }),

  aiChat: (question, sessionId = 'default', rangeMinutes = 60, provider = 'gemini') =>
    request('/api/ai/chat', {
      method: 'POST',
      body: JSON.stringify({
        question,
        session_id: sessionId,
        range_minutes: rangeMinutes,
        provider,
      }),
    }),

  aiInvestigateIncident: (payload) =>
    request('/api/ai/investigate-incident', {
      method: 'POST',
      body: JSON.stringify(payload),
    }),

  aiQueryAnalytics: (question, rangeKey = '24h', sessionId = 'default', provider = 'gemini') =>
    request('/api/ai/query-analytics', {
      method: 'POST',
      body: JSON.stringify({
        question,
        range_key: rangeKey,
        session_id: sessionId,
        provider,
      }),
    }),

  getAiProviders: () => request('/api/ai/providers'),

  testAiProvider: (provider) =>
    request(`/api/ai/providers/${encodeURIComponent(provider)}/test`, { method: 'POST' }),

  testGeminiConnection: () =>
    request('/api/ai/test', { method: 'POST' }),

  generateAiReport: (reportType = 'cluster_summary', rangeMinutes = 60) =>
    request('/api/reports/ai/generate', {
      method: 'POST',
      body: JSON.stringify({ report_type: reportType, range_minutes: rangeMinutes }),
    }),

  getAiReportArchive: (limit = 50) =>
    request(`/api/reports/ai/archive?limit=${limit}`),

  getAiReportStatus: (reportId) =>
    request(`/api/reports/ai/status/${reportId}`),

  getAiReportDetails: (reportId) =>
    request(`/api/reports/ai/${reportId}`),

  // Settings, Security, Terminal Audit & Backups

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

  getTerminalAudit: (limit = 100) =>
    request(`/api/terminal/audit?limit=${limit}`),

  getAdminUsers: () =>
    request('/api/admin/users'),

  updateAdminUser: (userId, payload) =>
    request(`/api/admin/users/${userId}`, {
      method: 'PATCH',
      body: JSON.stringify(payload),
    }),

  getAdminAuditLogs: () =>
    request('/api/admin/audit-logs'),

  getDatabaseBackupUrl: () =>
    `${API_BASE}/api/admin/backup/database`,

  getSettingsBackupUrl: () =>
    `${API_BASE}/api/admin/backup/settings`,
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
