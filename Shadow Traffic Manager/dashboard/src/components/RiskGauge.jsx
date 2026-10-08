import React from 'react';
import { getRiskTier } from '../utils/riskColor';

/**
 * High-density color-coded radial gauge for Congestion Risk Score (0-100).
 * Calibrated for Kinetic White backgrounds.
 */
export default function RiskGauge({
  score = 0,
  size = 'md',
  customThresholds = null,
  showLabel = true,
}) {
  const numericScore = Math.max(0, Math.min(100, Math.round(Number(score) || 0)));
  const tier = getRiskTier(numericScore, customThresholds);

  // Sizing variants
  const dimensions = {
    sm: { width: 100, height: 60, radius: 40, stroke: 7, fontSize: 'text-xl', labelSize: 'text-[10px]' },
    md: { width: 140, height: 85, radius: 55, stroke: 9, fontSize: 'text-3xl', labelSize: 'text-xs' },
    lg: { width: 180, height: 110, radius: 72, stroke: 12, fontSize: 'text-4xl', labelSize: 'text-sm' },
  }[size] || dimensions.md;

  // Semi-circle arc calculations (180-degree sweep from left to right)
  const cx = dimensions.width / 2;
  const cy = dimensions.height - 10;
  const r = dimensions.radius;
  const arcLength = Math.PI * r;
  const progressOffset = arcLength * (1 - numericScore / 100);

  return (
    <div className="flex flex-col items-center justify-center select-none">
      <div className="relative flex items-center justify-center" style={{ width: dimensions.width, height: dimensions.height }}>
        <svg
          width={dimensions.width}
          height={dimensions.height}
          viewBox={`0 0 ${dimensions.width} ${dimensions.height}`}
          className="overflow-visible"
        >
          {/* Ambient colored glow filter */}
          <defs>
            <filter id={`gauge-glow-${numericScore}`} x="-20%" y="-20%" width="140%" height="140%">
              <feDropShadow dx="0" dy="0" stdDeviation="3" floodColor={tier.hex} floodOpacity="0.3" />
            </filter>
          </defs>

          {/* Background arc track */}
          <path
            d={`M ${cx - r} ${cy} A ${r} ${r} 0 0 1 ${cx + r} ${cy}`}
            fill="none"
            stroke="#E2E8F0"
            strokeWidth={dimensions.stroke}
            strokeLinecap="round"
          />

          {/* Active progress arc with tier color */}
          <path
            d={`M ${cx - r} ${cy} A ${r} ${r} 0 0 1 ${cx + r} ${cy}`}
            fill="none"
            stroke={tier.hex}
            strokeWidth={dimensions.stroke}
            strokeDasharray={arcLength}
            strokeDashoffset={progressOffset}
            strokeLinecap="round"
            filter={`url(#gauge-glow-${numericScore})`}
            style={{
              transition: 'stroke-dashoffset 0.8s cubic-bezier(0.4, 0, 0.2, 1), stroke 0.4s ease',
            }}
          />
        </svg>

        {/* Center score readout */}
        <div className="absolute inset-0 flex flex-col items-center justify-end pb-1">
          <div className="flex items-baseline gap-0.5 leading-none font-mono">
            <span className={`${dimensions.fontSize} font-bold text-slate-900 tracking-tight`}>
              {numericScore}
            </span>
            <span className="text-[11px] text-slate-400 font-medium">/100</span>
          </div>
        </div>
      </div>

      {/* Tier Pill Badge */}
      {showLabel && (
        <div className="mt-1">
          <span
            className={`inline-flex items-center gap-1.5 px-2.5 py-0.5 rounded-full text-[11px] font-semibold uppercase tracking-wider border ${tier.badgeClass}`}
          >
            <span
              className="w-1.5 h-1.5 rounded-full animate-pulse"
              style={{ backgroundColor: tier.hex }}
            />
            {tier.label}
          </span>
        </div>
      )}
    </div>
  );
}
