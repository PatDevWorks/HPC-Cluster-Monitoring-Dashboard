import React, { useEffect, useState } from 'react';
import {
  MailPlus,
  KeyRound,
  RefreshCw,
  Shield,
  Users,
} from 'lucide-react';
import { api } from '../api.js';

export default function UserManagementPage({
  user,
  showToast,
}) {
  const [usersData, setUsersData] = useState({ users: [], invitations: [] });
  const [auditLogs, setAuditLogs] = useState({ auth_events: [], slurm_actions: [], terminal_commands: [] });
  const [inviteEmail, setInviteEmail] = useState('');
  const [inviteRole, setInviteRole] = useState('viewer');
  const [loading, setLoading] = useState(false);

  const isAdmin = ['admin', 'super_admin'].includes(user?.role);
  const isSuperAdmin = user?.role === 'super_admin';

  const loadData = async () => {
    if (!isAdmin) return;
    setLoading(true);
    try {
      const [uRes, aRes] = await Promise.all([
        api.getAdminUsers(),
        api.getAdminAuditLogs(),
      ]);
      setUsersData({
        users: uRes.users || [],
        invitations: uRes.invitations || [],
      });
      setAuditLogs(aRes || { auth_events: [], slurm_actions: [], terminal_commands: [] });
    } catch (err) {
      showToast?.(`Could not load user directory: ${err.message}`);
    } finally {
      setLoading(false);
    }
  };

  useEffect(() => {
    loadData();
  }, [user?.role]);

  const handleInvite = async (e) => {
    e.preventDefault();
    if (!inviteEmail.trim()) return;
    try {
      const res = await api.createInvitation(inviteEmail.trim(), inviteRole, Number(inviteHours));
      setInviteEmail('');
      await loadData();
      showToast?.(res?.message || 'Invitation sent');
    } catch (err) {
      showToast?.(`Invitation error: ${err.message}`);
    }
  };

  const handleUpdateUser = async (targetUser, updates) => {
    try {
      await api.updateAdminUser(targetUser.id, updates);
      await loadData();
      showToast?.(`Updated permissions for ${targetUser.email}`);
    } catch (err) {
      showToast?.(`Update failed: ${err.message}`);
    }
  };

  const handleReissueTemporaryPassword = async (targetUser) => {
    try {
      const result = await api.reissueTemporaryPassword(targetUser.id);
      await loadData();
      showToast?.(result?.message || `Temporary password reissued for ${targetUser.email}`);
    } catch (err) {
      showToast?.(`Could not reissue temporary password: ${err.message}`);
    }
  };

  if (!isAdmin) {
    return (
      <div className="spu-card p-6 space-y-3">
        <div className="flex items-center gap-2 text-lg font-bold">
          <Shield className="h-5 w-5 text-[var(--accent-cyan)]" />
          Account &amp; Role Information
        </div>
        <p className="text-xs spu-text-secondary">
          Signed in as <strong className="text-[var(--text-primary)]">{user?.email}</strong> with role{' '}
          <span className="font-mono font-bold text-[var(--accent-cyan)]">{user?.role}</span>.
          User directory management and audit logs require administrator access.
        </p>
      </div>
    );
  }

  return (
    <div className="space-y-6">
      <div className="flex flex-wrap items-center justify-between gap-3">
        <div className="flex items-center gap-3">
          <div className="flex h-10 w-10 items-center justify-center rounded-xl bg-cyan-500/15 text-[var(--accent-cyan)]">
            <Users className="h-5 w-5" />
          </div>
          <div>
            <h2 className="text-xl font-bold tracking-tight">User Management &amp; Access Control</h2>
            
          </div>
        </div>
        <button onClick={loadData} disabled={loading} className="spu-btn-secondary inline-flex items-center gap-1.5 text-xs">
          <RefreshCw className={`h-3.5 w-3.5 ${loading ? 'animate-spin' : ''}`} /> Refresh
        </button>
      </div>

      {/* Invite User (Super Admin Only) */}
      {isSuperAdmin && (
        <form onSubmit={handleInvite} className="spu-card p-5 grid grid-cols-1 gap-3 sm:grid-cols-4 items-end">
          <div className="sm:col-span-2">
            <label className="block text-[11px] font-semibold spu-text-secondary mb-1">
              Invite Team Member Email
            </label>
            <input
              type="email"
              required
              value={inviteEmail}
              onChange={(e) => setInviteEmail(e.target.value)}
              placeholder="colleague@spu.ac.za"
              className="spu-input w-full text-xs"
            />
          </div>
          <div>
            <label className="block text-[11px] font-semibold spu-text-secondary mb-1">Role</label>
            <select
              value={inviteRole}
              onChange={(e) => setInviteRole(e.target.value)}
              className="spu-input w-full text-xs"
            >
              <option value="viewer">Viewer (Read-Only Monitoring)</option>
              <option value="admin">Admin (Operations &amp; Models)</option>
            </select>
          </div>
          <div>
            <button type="submit" className="spu-btn-primary w-full inline-flex items-center justify-center gap-1.5 text-xs">
              <MailPlus className="h-3.5 w-3.5" /> Invite
            </button>
          </div>
        </form>
      )}

      {/* Users Table */}
      <section className="spu-card p-5">
        <h3 className="text-sm font-bold mb-3">Registered Accounts ({usersData.users.length})</h3>
        <div className="overflow-x-auto">
          <table className="w-full text-left text-xs">
            <thead>
              <tr className="border-b spu-border spu-text-secondary">
                <th className="py-2 pr-4">User</th>
                <th className="py-2 pr-4">Email</th>
                <th className="py-2 pr-4">Role</th>
                <th className="py-2 pr-4">Verified</th>
                <th className="py-2 pr-4">Status</th>
                {isSuperAdmin && <th className="py-2 pr-4 text-right">Controls</th>}
              </tr>
            </thead>
            <tbody className="divide-y spu-border">
              {usersData.users.map((u) => (
                <tr key={u.id}>
                  <td className="py-2.5 pr-4 font-semibold">{u.full_name || '--'}</td>
                  <td className="py-2.5 pr-4 font-mono">{u.email}</td>
                  <td className="py-2.5 pr-4">
                    {isSuperAdmin && u.id !== user?.id ? (
                      <select
                        value={u.role}
                        onChange={(e) => handleUpdateUser(u, { role: e.target.value })}
                        className="spu-input py-1 text-xs"
                      >
                        <option value="viewer">viewer</option>
                        <option value="admin">admin</option>
                        <option value="super_admin">super_admin</option>
                      </select>
                    ) : (
                      <span className="font-mono font-bold text-[var(--accent-cyan)]">{u.role}</span>
                    )}
                  </td>
                  <td className="py-2.5 pr-4 font-mono">{u.email_verified ? 'Yes' : 'Pending'}</td>
                  <td className="py-2.5 pr-4">
                    <span className={`rounded px-2 py-0.5 text-[10px] font-bold uppercase ${u.is_active ? 'bg-emerald-500/15 text-emerald-400' : 'bg-rose-500/15 text-rose-400'}`}>
                      {u.is_active ? 'Active' : 'Disabled'}
                    </span>
                  </td>
                  {isSuperAdmin && (
                    <td className="py-2.5 pr-4 text-right">
                      {u.id !== user?.id && (
                        <div className="inline-flex gap-2">
                          {u.first_login_pending && u.is_active && (
                            <button onClick={() => handleReissueTemporaryPassword(u)} className="spu-btn-secondary inline-flex items-center gap-1 text-[11px] py-1 px-2" title="Invalidate the old temporary password and email a new one">
                              <KeyRound className="h-3 w-3" /> Reissue
                            </button>
                          )}
                          <button
                            onClick={() => handleUpdateUser(u, { is_active: !u.is_active })}
                            className="spu-btn-secondary text-[11px] py-1 px-2"
                          >
                            {u.is_active ? 'Disable' : 'Enable'}
                          </button>
                        </div>
                      )}
                    </td>
                  )}
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      </section>

      {/* Invitations & Audit Logs */}
      <div className="grid grid-cols-1 gap-5 lg:grid-cols-2">
        <div className="spu-card p-5">
          <h3 className="text-sm font-bold mb-3">Recent Invitations ({usersData.invitations.length})</h3>
          <div className="space-y-2 max-h-72 overflow-y-auto text-xs">
            {usersData.invitations.length === 0 ? (
              <div className="spu-text-secondary py-6 text-center">No invitations created.</div>
            ) : (
              usersData.invitations.map((inv) => (
                <div key={inv.id} className="spu-subcard rounded-lg px-3 py-2 flex items-center justify-between">
                  <div>
                    <div className="font-mono font-semibold">{inv.email}</div>
                    <div className="text-[10px] spu-text-muted">
                      Role: {inv.role} • Expires: {inv.expires_utc}
                    </div>
                  </div>
                  <span className="font-mono text-[10px] uppercase">
                    {inv.accepted_utc ? 'Accepted' : 'Pending'}
                  </span>
                </div>
              ))
            )}
          </div>
        </div>

        <div className="spu-card p-5">
          <h3 className="text-sm font-bold mb-3">Security &amp; Authentication Audit Trail</h3>
          <div className="space-y-2 max-h-72 overflow-y-auto text-xs">
            {(auditLogs.auth_events || []).slice(0, 40).map((ev) => (
              <div key={ev.id} className="spu-subcard rounded-lg px-3 py-2">
                <div className="flex justify-between font-mono text-[10px]">
                  <span className="font-bold text-[var(--accent-cyan)]">{ev.event_type}</span>
                  <span className="spu-text-muted">{ev.created_utc}</span>
                </div>
                <div className="mt-0.5 font-mono text-[11px] spu-text-secondary">
                  Target: {ev.target_email || '--'}
                </div>
              </div>
            ))}
          </div>
        </div>
      </div>
    </div>
  );
}
