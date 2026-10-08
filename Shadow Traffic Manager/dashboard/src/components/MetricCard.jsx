import React from 'react';

export default function MetricCard({ title, value, unit = '', subtext, statusColor }) {
  return (
    <div className="metric-card">
      <div className="metric-title">{title}</div>
      <div className="metric-value" style={{ color: statusColor || 'var(--text-main)' }}>
        {value} <span style={{ fontSize: '1rem', fontWeight: 'normal', color: 'var(--text-muted)' }}>{unit}</span>
      </div>
      {subtext && <div className="metric-sub">{subtext}</div>}
    </div>
  );
}
