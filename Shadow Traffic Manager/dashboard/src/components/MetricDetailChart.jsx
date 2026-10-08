import React from 'react';
import {
  ResponsiveContainer,
  ComposedChart,
  Area,
  Line,
  XAxis,
  YAxis,
  Tooltip,
  CartesianGrid,
} from 'recharts';
import { AlertCircle, CheckCircle2 } from 'lucide-react';
import { formatNumber, formatTime } from '../utils/formatters';

/**
 * Custom Recharts Tooltip showing observed metric, seasonal baseline mean,
 * and normal confidence interval range [lower, upper].
 * Styled for the Kinetic White theme.
 */
function CustomChartTooltip({ active, payload, label, unit, metricName }) {
  if (!active || !payload || !payload.length) return null;

  const dataPoint = payload[0]?.payload;
  if (!dataPoint) return null;

  const actual = dataPoint.actual;
  const mean = dataPoint.baseline_mean;
  const lower = dataPoint.baseline_lower;
  const upper = dataPoint.baseline_upper;

  const isAbove = upper !== undefined && actual > upper;
  const isBelow = lower !== undefined && actual < lower;
  const isDeparted = isAbove || isBelow;

  return (
    <div className="bg-white/95 border border-slate-200 rounded-xl p-3 shadow-xl backdrop-blur-md text-xs font-sans min-w-[220px] text-slate-800">
      <div className="text-slate-500 font-mono text-[11px] border-b border-slate-100 pb-1.5 mb-2 flex justify-between items-center">
        <span>Time: {label || formatTime(dataPoint.timestamp)}</span>
        {isDeparted ? (
          <span className="flex items-center gap-1 text-orange-600 font-semibold text-[10px]">
            <AlertCircle className="w-3 h-3" />
            Seasonal Departure
          </span>
        ) : (
          <span className="flex items-center gap-1 text-emerald-600 font-semibold text-[10px]">
            <CheckCircle2 className="w-3 h-3" />
            Normal Range
          </span>
        )}
      </div>

      <div className="space-y-1.5">
        <div className="flex justify-between items-center">
          <span className="text-slate-600 font-medium">Observed Telemetry:</span>
          <span className={`font-mono font-bold text-sm ${isDeparted ? 'text-orange-600' : 'text-slate-900'}`}>
            {formatNumber(actual, 1)} {unit}
          </span>
        </div>

        {mean !== undefined && (
          <div className="flex justify-between items-center text-slate-500">
            <span>Seasonal Expected:</span>
            <span className="font-mono text-slate-700 font-semibold">
              {formatNumber(mean, 1)} {unit}
            </span>
          </div>
        )}

        {lower !== undefined && upper !== undefined && (
          <div className="flex justify-between items-center text-slate-500">
            <span>Normal Band (±1.5σ):</span>
            <span className="font-mono text-indigo-700 font-semibold">
              [{formatNumber(lower, 1)} – {formatNumber(upper, 1)}] {unit}
            </span>
          </div>
        )}
      </div>
    </div>
  );
}

/**
 * MetricDetailChart renders a Recharts full-size chart for a single metric stream.
 * It prominently overlays the normal seasonal baseline band as a shaded Area.
 * Calibrated for Kinetic White tiles.
 */
export default function MetricDetailChart({
  title,
  unit = '',
  data = [],
  currentValue,
  baselineMean,
  baselineStd,
  color = '#0284C7',
  isBottleneck = false,
  height = 240,
}) {
  // Format chart series data
  const chartData = data.map((d) => {
    const rawVal = typeof d === 'number' ? d : d.value ?? d.actual ?? 0;
    const ts = typeof d === 'object' && d.timestamp ? formatTime(d.timestamp) : '';

    // Calculate baseline band
    const bMean = d.baseline_mean ?? baselineMean ?? (rawVal > 0 ? rawVal : 100);
    const bStd = d.baseline_std ?? baselineStd ?? (bMean * 0.15);

    const lower = Math.max(0, bMean - 1.5 * bStd);
    const upper = bMean + 1.5 * bStd;

    return {
      timestamp: ts,
      actual: rawVal,
      baseline_mean: Number(bMean.toFixed(2)),
      baseline_lower: Number(lower.toFixed(2)),
      baseline_upper: Number(upper.toFixed(2)),
      // Recharts floating Area band [min, max]
      baseline_band: [Number(lower.toFixed(2)), Number(upper.toFixed(2))],
    };
  });

  const latestPoint = chartData[chartData.length - 1];
  const isCurrentlyDeparted = latestPoint && latestPoint.baseline_upper && latestPoint.actual > latestPoint.baseline_upper;

  return (
    <div
      className={`bg-white/90 backdrop-blur-md rounded-2xl border ${
        isBottleneck
          ? 'border-orange-300 ring-2 ring-orange-200/70 shadow-md shadow-orange-500/10'
          : 'border-slate-200/80 shadow-md'
      } p-5 shadow-slate-200/50 flex flex-col justify-between`}
    >
      {/* Chart Card Header */}
      <div className="flex flex-wrap items-center justify-between gap-2 mb-3">
        <div className="flex items-center gap-2">
          <span
            className="w-2.5 h-2.5 rounded-full"
            style={{ backgroundColor: color }}
          />
          <h3 className="text-sm font-bold text-slate-900 tracking-tight">{title}</h3>
          {isBottleneck && (
            <span className="text-[10px] uppercase font-bold tracking-wider px-2 py-0.5 rounded-md bg-orange-50 text-orange-700 border border-orange-200">
              Primary Bottleneck
            </span>
          )}
        </div>

        <div className="flex items-center gap-4 text-xs font-mono">
          <div className="flex items-center gap-1.5">
            <span className="text-slate-500 text-[11px]">Current:</span>
            <span className={`font-bold ${isCurrentlyDeparted ? 'text-orange-600' : 'text-slate-900'}`}>
              {formatNumber(currentValue ?? latestPoint?.actual, 1)} {unit}
            </span>
          </div>

          {baselineMean !== undefined && (
            <div className="flex items-center gap-1.5 hidden sm:flex">
              <span className="text-slate-400 text-[11px]">Seasonal Mean:</span>
              <span className="text-slate-700">
                {formatNumber(baselineMean, 1)} {unit}
              </span>
            </div>
          )}

          {isCurrentlyDeparted && (
            <span className="text-[11px] px-2 py-0.5 rounded-full bg-rose-50 border border-rose-200 text-rose-700 font-semibold flex items-center gap-1 animate-pulse">
              <AlertCircle className="w-3 h-3" />
              Above Baseline Band
            </span>
          )}
        </div>
      </div>

      {/* Chart Legend Banner */}
      <div className="flex items-center gap-4 text-[11px] text-slate-500 mb-2 px-1">
        <div className="flex items-center gap-1.5">
          <span className="w-3 h-0.5" style={{ backgroundColor: color }} />
          <span>Observed Telemetry</span>
        </div>
        <div className="flex items-center gap-1.5">
          <span className="w-3 h-2 bg-indigo-100 border border-indigo-300 rounded-sm" />
          <span>Normal Seasonal Band (±1.5σ EWMA)</span>
        </div>
        <div className="flex items-center gap-1.5 hidden sm:flex">
          <span className="w-3 h-0.5 border-t border-dashed border-slate-400" />
          <span>Expected Mean</span>
        </div>
      </div>

      {/* Recharts Composed Area + Line Chart */}
      <div style={{ width: '100%', height }}>
        {chartData.length > 0 ? (
          <ResponsiveContainer width="100%" height="100%">
            <ComposedChart data={chartData} margin={{ top: 10, right: 10, left: -10, bottom: 0 }}>
              <defs>
                <linearGradient id={`area-band-${title.replace(/\s+/g, '')}`} x1="0" y1="0" x2="0" y2="1">
                  <stop offset="0%" stopColor="#818CF8" stopOpacity={0.28} />
                  <stop offset="100%" stopColor="#818CF8" stopOpacity={0.08} />
                </linearGradient>
              </defs>

              <CartesianGrid strokeDasharray="3 3" stroke="#E2E8F0" vertical={false} />

              <XAxis
                dataKey="timestamp"
                stroke="#64748B"
                fontSize={10}
                tickLine={false}
                axisLine={{ stroke: '#CBD5E1' }}
              />

              <YAxis
                stroke="#64748B"
                fontSize={10}
                tickLine={false}
                axisLine={{ stroke: '#CBD5E1' }}
                tickFormatter={(val) => formatNumber(val, 0)}
                domain={['auto', 'auto']}
              />

              <Tooltip
                content={<CustomChartTooltip unit={unit} metricName={title} />}
              />

              {/* Shaded Normal Seasonal Band */}
              <Area
                type="monotone"
                dataKey="baseline_band"
                stroke="#818CF8"
                strokeWidth={1}
                strokeDasharray="4 4"
                strokeOpacity={0.6}
                fill={`url(#area-band-${title.replace(/\s+/g, '')})`}
                name="Normal Seasonal Band"
                isAnimationActive={false}
              />

              {/* Expected Seasonal Mean Line */}
              <Line
                type="monotone"
                dataKey="baseline_mean"
                stroke="#94A3B8"
                strokeWidth={1.2}
                strokeDasharray="4 4"
                dot={false}
                name="Expected Mean"
                isAnimationActive={false}
              />

              {/* Observed Actual Telemetry Line */}
              <Line
                type="monotone"
                dataKey="actual"
                stroke={color}
                strokeWidth={2.2}
                dot={false}
                activeDot={{ r: 5, fill: color, stroke: '#FFFFFF', strokeWidth: 2 }}
                name="Observed Telemetry"
                isAnimationActive={false}
              />
            </ComposedChart>
          </ResponsiveContainer>
        ) : (
          <div className="w-full h-full flex items-center justify-center text-slate-400 text-xs">
            Gathering time-series telemetry...
          </div>
        )}
      </div>
    </div>
  );
}
