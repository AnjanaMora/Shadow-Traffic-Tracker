/**
 * Pure helper functions for risk scoring, color mapping, and metric metadata.
 * Styled for the crisp Kinetic White design system.
 */

export const RISK_TIERS = {
  NORMAL: {
    tier: 'NORMAL',
    label: 'Normal',
    hex: '#10B981',
    color: 'text-emerald-600',
    bg: 'bg-emerald-50',
    border: 'border-emerald-200',
    glow: 'rgba(16, 185, 129, 0.2)',
    badgeClass: 'text-emerald-700 bg-emerald-50/90 border-emerald-200/90 shadow-2xs',
  },
  WATCH: {
    tier: 'WATCH',
    label: 'Watch',
    hex: '#F59E0B',
    color: 'text-amber-600',
    bg: 'bg-amber-50',
    border: 'border-amber-200',
    glow: 'rgba(245, 158, 11, 0.2)',
    badgeClass: 'text-amber-700 bg-amber-50/90 border-amber-200/90 shadow-2xs',
  },
  WARNING: {
    tier: 'WARNING',
    label: 'Warning',
    hex: '#EA580C',
    color: 'text-orange-600',
    bg: 'bg-orange-50',
    border: 'border-orange-200',
    glow: 'rgba(234, 88, 12, 0.25)',
    badgeClass: 'text-orange-700 bg-orange-50/90 border-orange-200/90 shadow-2xs',
  },
  CRITICAL: {
    tier: 'CRITICAL',
    label: 'Critical',
    hex: '#E11D48',
    color: 'text-rose-600',
    bg: 'bg-rose-50',
    border: 'border-rose-200',
    glow: 'rgba(225, 29, 72, 0.25)',
    badgeClass: 'text-rose-700 bg-rose-50/90 border-rose-200/90 shadow-2xs',
  },
};

/**
 * Maps a numeric score (0-100) or status string to its risk tier attributes.
 *
 * @param {number|string} score - Risk score between 0 and 100, or a tier name
 * @param {object} [customThresholds] - Optional custom warning/critical thresholds
 * @returns {object} Tier metadata including color, hex, label, and style classes
 */
export function getRiskTier(score, customThresholds = null) {
  // If string status was passed directly
  if (typeof score === 'string') {
    const upper = score.toUpperCase();
    if (upper.includes('CRIT')) return RISK_TIERS.CRITICAL;
    if (upper.includes('WARN')) return RISK_TIERS.WARNING;
    if (upper.includes('WATCH') || upper.includes('MED')) return RISK_TIERS.WATCH;
    return RISK_TIERS.NORMAL;
  }

  const num = Number(score);
  if (isNaN(num)) return RISK_TIERS.NORMAL;

  const warnThreshold = customThresholds?.warning ?? 60.0;
  const critThreshold = customThresholds?.critical ?? 80.0;

  if (num >= critThreshold) {
    return RISK_TIERS.CRITICAL;
  }
  if (num >= warnThreshold) {
    return RISK_TIERS.WARNING;
  }
  if (num >= 40.0) {
    return RISK_TIERS.WATCH;
  }
  return RISK_TIERS.NORMAL;
}

/**
 * Converts metric keys to human-friendly display titles.
 */
export function getMetricDisplayName(metricKey) {
  const map = {
    active_users: 'Active Users',
    request_rate: 'Throughput (RPS)',
    avg_response_time_ms: 'Latency (Avg)',
    error_rate_percent: 'Error Rate',
  };
  return map[metricKey] || metricKey;
}

/**
 * Returns canonical units for metrics.
 */
export function getMetricUnit(metricKey) {
  const map = {
    active_users: 'users',
    request_rate: 'req/s',
    avg_response_time_ms: 'ms',
    error_rate_percent: '%',
  };
  return map[metricKey] || '';
}

/**
 * Returns consistent accent colors for metric factors in attribution charts.
 */
export function getMetricColor(metricKey) {
  const map = {
    avg_response_time_ms: '#6366F1', // Indigo
    request_rate: '#0284C7',         // Sky
    error_rate_percent: '#EA580C',   // Orange
    active_users: '#059669',         // Emerald
  };
  return map[metricKey] || '#64748B';
}

/**
 * Returns concise display labels for attribution breakdowns.
 */
export function getMetricShortName(metricKey) {
  const map = {
    avg_response_time_ms: 'Response time',
    request_rate: 'Request rate',
    error_rate_percent: 'Error rate',
    active_users: 'Active users',
  };
  return map[metricKey] || metricKey;
}
