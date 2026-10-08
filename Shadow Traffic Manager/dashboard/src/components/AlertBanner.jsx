import React from 'react';

export default function AlertBanner({ prediction }) {
  if (!prediction) return null;

  const level = prediction.congestion_level || 'LOW';

  return (
    <div className={`banner-card ${level}`}>
      <div>
        <div style={{ display: 'flex', alignItems: 'center', gap: '10px' }}>
          <span className={`status-badge ${level}`}>{level} RISK</span>
          <strong style={{ fontSize: '1rem' }}>
            {level === 'LOW'
              ? 'Traffic Congestion Model: Stable'
              : `Proactive Congestion Warning (${(prediction.congestion_risk_score * 100).toFixed(0)}% Risk Index)`}
          </strong>
        </div>
        <p style={{ fontSize: '0.86rem', color: '#cbd5e1', marginTop: '6px' }}>
          {prediction.recommendation}
        </p>
      </div>

      <div style={{ textAlign: 'right', minWidth: '160px' }}>
        <div style={{ fontSize: '0.75rem', color: 'var(--text-muted)' }}>
          Forecast Horizon: {prediction.horizon_seconds}s
        </div>
        <div style={{ fontSize: '0.85rem', fontWeight: 600, marginTop: '2px' }}>
          Expected RPS: {prediction.predicted_request_rate?.toFixed(1) || '0.0'}
        </div>
      </div>
    </div>
  );
}
