import React from 'react';

export default function TrafficChart({ data = [], height = 220 }) {
  if (!data || data.length === 0) {
    return (
      <div style={{ height, display: 'flex', alignItems: 'center', justifyContent: 'center', color: 'var(--text-muted)' }}>
        Awaiting telemetry stream...
      </div>
    );
  }

  const points = data.slice(-30);
  const rpsValues = points.map((p) => p.request_rate || 0);
  const latencyValues = points.map((p) => p.avg_response_time_ms || 0);

  const maxRps = Math.max(...rpsValues, 100);
  const maxLatency = Math.max(...latencyValues, 100);

  const width = 700;
  const padding = 30;
  const chartW = width - padding * 2;
  const chartH = height - padding * 2;

  // Build SVG path for RPS
  const rpsCoords = points.map((p, idx) => {
    const x = padding + (idx / Math.max(points.length - 1, 1)) * chartW;
    const y = height - padding - (p.request_rate / maxRps) * chartH;
    return `${x},${y}`;
  });

  // Build SVG path for Latency
  const latencyCoords = points.map((p, idx) => {
    const x = padding + (idx / Math.max(points.length - 1, 1)) * chartW;
    const y = height - padding - (p.avg_response_time_ms / maxLatency) * chartH;
    return `${x},${y}`;
  });

  const rpsPath = rpsCoords.length > 1 ? `M ${rpsCoords.join(' L ')}` : '';
  const latencyPath = latencyCoords.length > 1 ? `M ${latencyCoords.join(' L ')}` : '';

  return (
    <div>
      <div style={{ display: 'flex', gap: '20px', marginBottom: '8px', fontSize: '0.8rem' }}>
        <div style={{ display: 'flex', alignItems: 'center', gap: '6px' }}>
          <span style={{ width: '12px', height: '3px', background: '#6366f1', display: 'inline-block' }} />
          <span>Request Rate (RPS, Peak: {maxRps.toFixed(0)})</span>
        </div>
        <div style={{ display: 'flex', alignItems: 'center', gap: '6px' }}>
          <span style={{ width: '12px', height: '3px', background: '#f59e0b', display: 'inline-block' }} />
          <span>Avg Latency (ms, Peak: {maxLatency.toFixed(0)})</span>
        </div>
      </div>
      <svg viewBox={`0 0 ${width} ${height}`} style={{ width: '100%', height: 'auto', background: 'rgba(0,0,0,0.2)', borderRadius: '8px' }}>
        {/* Horizontal grid lines */}
        {[0, 0.25, 0.5, 0.75, 1].map((ratio) => {
          const y = height - padding - ratio * chartH;
          return (
            <line
              key={ratio}
              x1={padding}
              y1={y}
              x2={width - padding}
              y2={y}
              stroke="var(--border-color)"
              strokeDasharray="4"
              strokeWidth="0.5"
            />
          );
        })}

        {/* Latency line (amber) */}
        {latencyPath && (
          <path d={latencyPath} fill="none" stroke="#f59e0b" strokeWidth="2.2" strokeLinecap="round" opacity="0.85" />
        )}

        {/* RPS line (indigo) */}
        {rpsPath && (
          <path d={rpsPath} fill="none" stroke="#6366f1" strokeWidth="2.5" strokeLinecap="round" />
        )}

        {/* Data points */}
        {points.map((p, idx) => {
          const x = padding + (idx / Math.max(points.length - 1, 1)) * chartW;
          const yRps = height - padding - (p.request_rate / maxRps) * chartH;
          return <circle key={idx} cx={x} cy={yRps} r="2.5" fill="#818cf8" />;
        })}
      </svg>
    </div>
  );
}
