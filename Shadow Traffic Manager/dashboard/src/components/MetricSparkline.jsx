import React from 'react';
import { formatNumber } from '../utils/formatters';

/**
 * Compact sparkline trend component for site cards.
 * Styled for the Kinetic White tile theme.
 */
export default function MetricSparkline({
  label,
  values = [],
  currentValue,
  unit = '',
  color = '#0284C7', // default sky-600
  isElevated = false,
  alertColor = null,
}) {
  const strokeColor = alertColor || color;
  const numCurrent = currentValue !== undefined ? currentValue : (values.length > 0 ? values[values.length - 1] : 0);

  // Ensure we have a valid array of points to render a smooth sparkline
  let renderValues = values;
  if (!renderValues || renderValues.length === 0) {
    if (typeof numCurrent === 'number' && numCurrent > 0) {
      renderValues = [numCurrent * 0.98, numCurrent * 0.99, numCurrent * 1.01, numCurrent * 0.99, numCurrent];
    } else {
      renderValues = [];
    }
  } else if (renderValues.length === 1) {
    const v = renderValues[0];
    renderValues = [v * 0.98, v * 0.99, v * 1.01, v * 0.99, v];
  }

  // Compute 30-minute delta percentage
  let deltaPercent = 0;
  if (renderValues.length >= 2) {
    const firstVal = renderValues[0];
    const lastVal = renderValues[renderValues.length - 1];
    if (firstVal > 0) {
      deltaPercent = ((lastVal - firstVal) / firstVal) * 100;
    }
  }

  // Generate SVG path coordinates
  const width = 110;
  const height = 32;
  const padding = 2;

  let pathData = '';
  let fillData = '';

  if (renderValues.length > 1) {
    const minVal = Math.min(...renderValues);
    const maxVal = Math.max(...renderValues);
    const range = (maxVal - minVal) === 0 ? (maxVal * 0.1 || 1) : maxVal - minVal;

    const points = renderValues.map((val, idx) => {
      const x = padding + (idx / (renderValues.length - 1)) * (width - 2 * padding);
      const y = height - padding - ((val - minVal) / range) * (height - 2 * padding);
      return [x, y];
    });

    pathData = points.reduce((acc, [x, y], idx) => {
      return idx === 0 ? `M ${x.toFixed(1)} ${y.toFixed(1)}` : `${acc} L ${x.toFixed(1)} ${y.toFixed(1)}`;
    }, '');

    // Area fill path down to baseline
    const lastPoint = points[points.length - 1];
    const firstPoint = points[0];
    fillData = `${pathData} L ${lastPoint[0]} ${height} L ${firstPoint[0]} ${height} Z`;
  }

  return (
    <div className="bg-slate-50/80 border border-slate-200/80 rounded-xl p-2.5 flex flex-col justify-between hover:border-slate-300 transition-colors shadow-2xs">
      <div className="flex items-center justify-between text-xs text-slate-500 mb-1">
        <span className="font-medium truncate">{label}</span>
        {renderValues.length >= 2 && (
          <span
            className={`font-mono text-[10px] px-1 py-0.2 rounded font-semibold ${
              deltaPercent > 5
                ? isElevated ? 'text-rose-700 bg-rose-50 border border-rose-200/60' : 'text-slate-700 bg-slate-200/60'
                : deltaPercent < -5
                ? 'text-emerald-700 bg-emerald-50 border border-emerald-200/60'
                : 'text-slate-500'
            }`}
          >
            {deltaPercent > 0 ? `+${deltaPercent.toFixed(0)}%` : `${deltaPercent.toFixed(0)}%`}
          </span>
        )}
      </div>

      <div className="flex items-end justify-between gap-2">
        <div className="flex items-baseline gap-1">
          <span className={`text-base font-bold font-mono tracking-tight ${isElevated ? 'text-rose-600' : 'text-slate-900'}`}>
            {typeof numCurrent === 'number' ? formatNumber(numCurrent) : numCurrent}
          </span>
          {unit && <span className="text-[10px] text-slate-400 font-mono">{unit}</span>}
        </div>

        {/* Sparkline SVG */}
        <div className="w-[110px] h-[32px] flex-shrink-0">
          {pathData ? (
            <svg width={width} height={height} className="overflow-visible">
              <defs>
                <linearGradient id={`grad-${label.replace(/\s+/g, '')}`} x1="0" y1="0" x2="0" y2="1">
                  <stop offset="0%" stopColor={strokeColor} stopOpacity={0.25} />
                  <stop offset="100%" stopColor={strokeColor} stopOpacity={0.0} />
                </linearGradient>
              </defs>
              <path d={fillData} fill={`url(#grad-${label.replace(/\s+/g, '')})`} />
              <path
                d={pathData}
                fill="none"
                stroke={strokeColor}
                strokeWidth={1.75}
                strokeLinecap="round"
                strokeLinejoin="round"
              />
            </svg>
          ) : (
            <div className="w-full h-full flex items-center justify-center text-[10px] text-slate-400 font-mono">
              Standby
            </div>
          )}
        </div>
      </div>
    </div>
  );
}
