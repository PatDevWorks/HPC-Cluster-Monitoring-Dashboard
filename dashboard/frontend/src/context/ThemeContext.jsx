import React, { createContext, useContext, useEffect, useMemo, useState } from 'react';

const ThemeContext = createContext(null);

function resolveSystemTheme() {
  if (typeof window === 'undefined') return 'dark';
  return window.matchMedia('(prefers-color-scheme: dark)').matches ? 'dark' : 'light';
}

export function ThemeProvider({ children }) {
  const [preference, setPreference] = useState(() => {
    try {
      return localStorage.getItem('spu_hpc_theme') || 'dark';
    } catch {
      return 'dark';
    }
  });

  const [systemTheme, setSystemTheme] = useState(resolveSystemTheme);

  useEffect(() => {
    const mq = window.matchMedia('(prefers-color-scheme: dark)');
    const handler = (e) => setSystemTheme(e.matches ? 'dark' : 'light');
    mq.addEventListener('change', handler);
    return () => mq.removeEventListener('change', handler);
  }, []);

  const resolvedTheme = preference === 'system' ? systemTheme : preference;

  useEffect(() => {
    document.documentElement.setAttribute('data-theme', resolvedTheme);
    try {
      localStorage.setItem('spu_hpc_theme', preference);
    } catch {
      // ignore storage quota errors
    }
  }, [preference, resolvedTheme]);

  const chartTheme = useMemo(() => {
    const isDark = resolvedTheme === 'dark';
    return {
      isDark,
      grid: isDark ? '#16243d' : '#e2e8f0',
      axis: isDark ? '#94a3b8' : '#475569',
      cyan: isDark ? '#5eead4' : '#0f766e',
      blue: isDark ? '#38bdf8' : '#2563eb',
      purple: isDark ? '#a855f7' : '#7c3aed',
      emerald: isDark ? '#10b981' : '#059669',
      amber: isDark ? '#f59e0b' : '#d97706',
      red: isDark ? '#ef4444' : '#dc2626',
      tooltipStyle: {
        backgroundColor: isDark ? '#0b1324' : '#ffffff',
        border: `1px solid ${isDark ? '#23385c' : '#cbd5e1'}`,
        borderRadius: '10px',
        fontSize: '13px',
        color: isDark ? '#f1f5f9' : '#0f172a',
        boxShadow: isDark
          ? '0 8px 24px rgba(0,0,0,0.45)'
          : '0 8px 24px rgba(15,23,42,0.12)',
      },
    };
  }, [resolvedTheme]);

  const value = useMemo(
    () => ({
      preference,
      setPreference,
      theme: resolvedTheme,
      resolvedTheme,
      isDark: resolvedTheme === 'dark',
      chartTheme,
    }),
    [preference, resolvedTheme, chartTheme]
  );

  return <ThemeContext.Provider value={value}>{children}</ThemeContext.Provider>;
}

export function useTheme() {
  const ctx = useContext(ThemeContext);
  if (!ctx) throw new Error('useTheme must be used inside ThemeProvider');
  return ctx;
}
