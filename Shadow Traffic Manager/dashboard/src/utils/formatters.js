/**
 * Telemetry number and date formatters.
 */

export function formatNumber(val, decimals = 1) {
  if (val === null || val === undefined || isNaN(val)) return '—';
  if (val >= 1_000_000) {
    return (val / 1_000_000).toFixed(decimals) + 'M';
  }
  if (val >= 1_000) {
    return (val / 1_000).toFixed(decimals) + 'k';
  }
  return Number(val).toFixed(decimals);
}

export function formatTime(isoString) {
  if (!isoString) return '—';
  try {
    const d = new Date(isoString);
    return d.toLocaleTimeString([], { hour: '2-digit', minute: '2-digit', second: '2-digit' });
  } catch {
    return String(isoString);
  }
}

export function formatRelativeTime(isoString) {
  if (!isoString) return '—';
  try {
    const diffSec = Math.floor((Date.now() - new Date(isoString).getTime()) / 1000);
    if (diffSec < 5) return 'just now';
    if (diffSec < 60) return `${diffSec}s ago`;
    const mins = Math.floor(diffSec / 60);
    if (mins < 60) return `${mins}m ago`;
    return `${Math.floor(mins / 60)}h ago`;
  } catch {
    return '—';
  }
}
