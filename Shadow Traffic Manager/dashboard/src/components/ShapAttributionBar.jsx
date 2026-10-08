import React from 'react';
import { Sparkles, PieChart } from 'lucide-react';
import { getMetricColor, getMetricShortName } from '../utils/riskColor';

/**
 * ShapAttributionBar renders an explainable SHAP-style weighted percentage
 * breakdown of the factors contributing to the current Congestion Risk Score.
 * Styled for the Kinetic White tile theme.
 */
export default function ShapAttributionBar({
  factors = [],
  isElevated = false,
  compact = false,
}) {
  // Normalize factors into a sorted attribution list with percentages summing to 100%
  const attributionList = (() => {
    if (factors && factors.length > 0) {
      const activeFactors = factors
        .filter((f) => (f.percentage_contribution || 0) > 0)
        .sort((a, b) => (b.percentage_contribution || 0) - (a.percentage_contribution || 0));

      if (activeFactors.length > 0) {
        const total = activeFactors.reduce((acc, f) => acc + f.percentage_contribution, 0);
        return activeFactors.map((f) => ({
          metric: f.metric,
          name: getMetricShortName(f.metric),
          percentage: total > 0 ? Math.round((f.percentage_contribution / total) * 100) : 25,
          color: getMetricColor(f.metric),
          reason: f.reason,
          zScore: f.z_score,
        }));
      }
    }

    // Baseline fallback defaults for display when metrics are healthy or booting
    if (isElevated) {
      return [
        { metric: 'avg_response_time_ms', name: 'Response time', percentage: 45, color: getMetricColor('avg_response_time_ms') },
        { metric: 'request_rate', name: 'Request rate', percentage: 30, color: getMetricColor('request_rate') },
        { metric: 'error_rate_percent', name: 'Error rate', percentage: 25, color: getMetricColor('error_rate_percent') },
      ];
    }

    return [
      { metric: 'avg_response_time_ms', name: 'Response time', percentage: 35, color: getMetricColor('avg_response_time_ms') },
      { metric: 'request_rate', name: 'Request rate', percentage: 25, color: getMetricColor('request_rate') },
      { metric: 'error_rate_percent', name: 'Error rate', percentage: 20, color: getMetricColor('error_rate_percent') },
      { metric: 'active_users', name: 'Active users', percentage: 20, color: getMetricColor('active_users') },
    ];
  })();

  // Format the headline text
  const headlineText = attributionList
    .map((item, index) => {
      if (index === 0) {
        return `${item.name}: ${item.percentage}% of risk score`;
      }
      return `${item.name}: ${item.percentage}%`;
    })
    .join(', ');

  if (compact) {
    return (
      <div className="space-y-1.5">
        <div className="flex items-center justify-between text-[10px] text-slate-500 font-mono">
          <span className="flex items-center gap-1 font-semibold text-slate-700">
            <Sparkles className="w-3 h-3 text-indigo-600" />
            Attribution
          </span>
          <span className="truncate max-w-[200px]" title={headlineText}>{headlineText}</span>
        </div>
        <div className="w-full h-2 rounded-full bg-slate-200/80 overflow-hidden flex gap-0.5 p-0.5">
          {attributionList.map((item) => (
            <div
              key={item.metric}
              style={{
                width: `${item.percentage}%`,
                backgroundColor: item.color,
              }}
              className="h-full rounded-sm transition-all duration-300"
              title={`${item.name}: ${item.percentage}%`}
            />
          ))}
        </div>
      </div>
    );
  }

  return (
    <div className="bg-slate-50/90 rounded-2xl border border-slate-200/80 p-4 space-y-3 shadow-xs animate-fadeIn">
      {/* Header and Headline Attribution String */}
      <div className="flex flex-col sm:flex-row sm:items-center justify-between gap-2">
        <div className="flex items-center gap-2">
          <div className="p-1.5 rounded-lg bg-indigo-50 border border-indigo-200 text-indigo-600">
            <Sparkles className="w-4 h-4" />
          </div>
          <div>
            <h4 className="text-xs font-bold uppercase tracking-wider text-slate-800">
              SHAP-Style Risk Factor Attribution
            </h4>
            <p className="text-[11px] font-mono text-indigo-700 font-medium">
              {headlineText}
            </p>
          </div>
        </div>

        <span className="text-[10px] px-2 py-0.5 rounded-full bg-white text-slate-600 border border-slate-200 font-mono self-start sm:self-center shadow-2xs">
          EXPLAINABLE AI
        </span>
      </div>

      {/* Multi-Segment Stacked Horizontal Bar */}
      <div className="w-full h-3.5 rounded-lg bg-slate-200/80 border border-slate-300/60 overflow-hidden flex gap-1 p-0.5 shadow-inner">
        {attributionList.map((item) => (
          <div
            key={item.metric}
            style={{
              width: `${item.percentage}%`,
              backgroundColor: item.color,
            }}
            className="h-full rounded-sm transition-all duration-500 hover:brightness-105 relative group cursor-pointer"
            title={`${item.name}: ${item.percentage}% of risk score`}
          />
        ))}
      </div>

      {/* Individual Factor Legend Cards */}
      <div className="grid grid-cols-2 sm:grid-cols-4 gap-2.5 pt-1">
        {attributionList.map((item) => (
          <div
            key={item.metric}
            className="flex items-center gap-2.5 bg-white border border-slate-200/80 rounded-xl p-2.5 hover:border-slate-300 transition-colors shadow-2xs"
          >
            <span
              className="w-2.5 h-2.5 rounded-full flex-shrink-0 shadow-xs"
              style={{ backgroundColor: item.color }}
            />
            <div className="min-w-0 flex-1">
              <div className="text-[10px] text-slate-500 truncate">{item.name}</div>
              <div className="text-xs font-bold font-mono text-slate-900 flex items-center justify-between">
                <span>{item.percentage}%</span>
                {item.zScore !== undefined && item.zScore > 1.5 && (
                  <span className="text-[9px] text-orange-600 font-mono font-bold">
                    +{item.zScore.toFixed(1)}σ
                  </span>
                )}
              </div>
            </div>
          </div>
        ))}
      </div>
    </div>
  );
}
