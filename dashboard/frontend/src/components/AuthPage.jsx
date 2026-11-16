
import React, { useState } from 'react';
import { api } from '../api.js';
import { LockKeyhole, Mail, Loader2 } from 'lucide-react';
import SpuLogo from './SpuLogo.jsx';

export default function AuthPage({ onAuthenticated }) {
  const [stage, setStage] = useState('login');
  const [email, setEmail] = useState('');
  const [password, setPassword] = useState('');
  const [code, setCode] = useState('');
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState('');
  const [message, setMessage] = useState('');

  const handleLogin = async (event) => {
    event.preventDefault();
    setError('');
    setMessage('');
    setLoading(true);

    try {
      const result = await api.login(email.trim(), password);
      setStage('otp');
      setMessage(result?.message || 'A verification code has been sent to your email.');
    } catch (err) {
      setError(err.message || 'Unable to sign in.');
    } finally {
      setLoading(false);
    }
  };

  const handleVerifyOtp = async (event) => {
    event.preventDefault();
    setError('');
    setLoading(true);

    try {
      await api.verifyOtp(email.trim(), code.trim());
      const result = await api.getMe();

      if (!result?.authenticated || !result?.user) {
        throw new Error('Your session could not be verified. Please sign in again.');
      }

      onAuthenticated(result.user);
    } catch (err) {
      setError(err.message || 'OTP verification failed.');
    } finally {
      setLoading(false);
    }
  };

  const handleBack = () => {
    setStage('login');
    setCode('');
    setError('');
    setMessage('');
  };

  return (
    <div className="flex min-h-screen items-center justify-center bg-[var(--bg-app)] px-4 py-10">
      <div className="w-full max-w-md">
        <div className="mb-8 text-center">
          <div className="mx-auto mb-3">
            <SpuLogo />
          </div>

          <h1 className="text-2xl font-bold tracking-tight spu-text-primary">
            HPC Predictive Monitoring Dashboard
          </h1>
          <p className="mt-2 text-sm spu-text-secondary">
            Sol Plaatje University
          </p>
        </div>

        <div className="rounded-2xl border border-[var(--border-color)] bg-[var(--bg-card)] p-6 shadow-xl sm:p-8">
          {stage === 'login' ? (
            <>
              <div className="mb-6">
                <h2 className="text-xl font-semibold spu-text-primary">
                  Sign in
                </h2>
                <p className="mt-1 text-sm spu-text-secondary">
                  Sign in using your registered account.
                </p>
              </div>

              <form onSubmit={handleLogin} className="space-y-5">
                <div>
                  <label className="mb-2 block text-sm font-medium spu-text-primary">
                    Email address
                  </label>
                  <div className="relative">
                    <Mail className="absolute left-3 top-3.5 text-gray-400" size={17} />
                    <input
                      type="email"
                      required
                      autoComplete="username"
                      value={email}
                      onChange={(e) => setEmail(e.target.value)}
                      placeholder="you@example.com"
                      className="w-full rounded-xl border border-[var(--border-color)] bg-[var(--bg-app)] py-3 pl-10 pr-3 text-sm spu-text-primary outline-none focus:border-cyan-500"
                    />
                  </div>
                </div>

                <div>
                  <label className="mb-2 block text-sm font-medium spu-text-primary">
                    Password
                  </label>
                  <div className="relative">
                    <LockKeyhole className="absolute left-3 top-3.5 text-gray-400" size={17} />
                    <input
                      type="password"
                      required
                      autoComplete="current-password"
                      value={password}
                      onChange={(e) => setPassword(e.target.value)}
                      placeholder="Enter your password"
                      className="w-full rounded-xl border border-[var(--border-color)] bg-[var(--bg-app)] py-3 pl-10 pr-3 text-sm spu-text-primary outline-none focus:border-cyan-500"
                    />
                  </div>
                </div>

                {error && (
                  <p role="alert" className="rounded-lg border border-red-500/30 bg-red-500/10 p-3 text-sm text-red-400">
                    {error}
                  </p>
                )}

                <button
                  type="submit"
                  disabled={loading}
                  className="flex w-full items-center justify-center gap-2 rounded-xl bg-cyan-500 px-4 py-3 text-sm font-semibold text-slate-950 transition hover:bg-cyan-400 disabled:cursor-not-allowed disabled:opacity-60"
                >
                  {loading && <Loader2 size={17} className="animate-spin" />}
                  {loading ? 'Signing in...' : 'Continue'}
                </button>
              </form>
            </>
          ) : (
            <>
              <div className="mb-6">
                <h2 className="text-xl font-semibold spu-text-primary">
                  Email verification
                </h2>
                <p className="mt-2 text-sm spu-text-secondary">
                  Enter the verification code sent to:
                </p>
                <p className="mt-1 break-all text-sm font-semibold text-cyan-400">
                  {email}
                </p>
              </div>

              <form onSubmit={handleVerifyOtp} className="space-y-5">
                <div>
                  <label className="mb-2 block text-sm font-medium spu-text-primary">
                    One-time password
                  </label>
                  <input
                    type="text"
                    inputMode="numeric"
                    autoComplete="one-time-code"
                    required
                    maxLength={6}
                    value={code}
                    onChange={(e) => setCode(e.target.value.replace(/\D/g, ''))}
                    placeholder="Enter your OTP"
                    className="w-full rounded-xl border border-[var(--border-color)] bg-[var(--bg-app)] px-4 py-4 text-center text-xl font-bold tracking-[0.5em] spu-text-primary outline-none focus:border-cyan-500"
                  />
                </div>

                {message && (
                  <p className="text-sm text-cyan-400">{message}</p>
                )}

                {error && (
                  <p role="alert" className="rounded-lg border border-red-500/30 bg-red-500/10 p-3 text-sm text-red-400">
                    {error}
                  </p>
                )}

                <button
                  type="submit"
                  disabled={loading || code.length !== 6}
                  className="flex w-full items-center justify-center gap-2 rounded-xl bg-cyan-500 px-4 py-3 text-sm font-semibold text-slate-950 transition hover:bg-cyan-400 disabled:cursor-not-allowed disabled:opacity-60"
                >
                  {loading && <Loader2 size={17} className="animate-spin" />}
                  {loading ? 'Verifying...' : 'Verify and sign in'}
                </button>

                <button
                  type="button"
                  onClick={handleBack}
                  disabled={loading}
                  className="w-full py-2 text-sm spu-text-secondary transition hover:text-cyan-400"
                >
                  Back to sign in
                </button>
              </form>
            </>
          )}
        </div>

        <p className="mt-6 text-center text-xs spu-text-secondary">
          Restricted access · Authorised cluster personnel only
        </p>
      </div>
    </div>
  );
}
