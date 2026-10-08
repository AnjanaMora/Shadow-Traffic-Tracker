import React from 'react';
import { AlertTriangle, Clock, ArrowRight, Sliders, ShieldCheck, Activity, Zap, Trash2 } from 'lucide-react';
import RiskGauge from './RiskGauge';
import MetricSparkline from './MetricSparkline';
import ShapAttributionBar from './ShapAttributionBar';
import { getRiskTier, getMetricDisplayName, getMetricUnit } from '../utils/riskColor';
import { formatRelativeTime } from '../utils/formatters';

/**
 * SiteCard renders the primary overview for a monitored site:
 * - Radial RiskGauge with color-coded severity
 * - Estimated time-to-congestion callout (for Watch/Warning/Critical)
 * - Explainable primary bottleneck attribution (WHY the score is elevated)
 * - 4x sparklines over the last 30 minutes
 * - Kinetic White frosted tile styling
 */
export default function SiteCard({
  site,
  assessment = {},
  history = [],
  onSelect,
  onOpenThresholds,
  onDelete,
  customThresholds = null,
}) {
  const siteId = site.site_id;
  const score = assessment.score ?? site.risk_score ?? 0;
  const tier = getRiskTier(score, customThresholds);
  const status = assessment.status || site.current_status || tier.label;
  const etaMinutes = assessment.eta_minutes;
  const primaryBottleneck = assessment.primary_bottleneck;
  const contributingFactors = assessment.contributing_factors || [];
  const remediation = assessment.active_remediation;

  // Find the top contributing factor if available
  const topFactor = contributingFactors.find(
    (f) => f.metric === primaryBottleneck
  ) || contributingFactors[0];

  // Extract metric streams from history
  const activeUsersSeries = history.map((h) => h.active_users);
  const rpsSeries = history.map((h) => h.request_rate);
  const latencySeries = history.map((h) => h.avg_response_time_ms);
  const errorSeries = history.map((h) => h.error_rate_percent);

  // Latest metrics fallback
  const latest = history[history.length - 1] || {
    active_users: site.active_users || 0,
    request_rate: site.current_rps || 0,
    avg_response_time_ms: site.current_latency_ms || 0,
    error_rate_percent: site.current_error_rate || 0,
  };

  const isElevated = tier.tier !== 'NORMAL';

  return (
    <div
      className={`group relative bg-white/90 backdrop-blur-md rounded-2xl border ${
        isElevated ? tier.border : 'border-slate-200/80'
      } hover:border-indigo-300 transition-all duration-300 shadow-md hover:shadow-xl shadow-slate-200/50 flex flex-col justify-between overflow-hidden`}
    >
      {/* Top subtle highlight line matching tier color */}
      <div
        className="h-1 w-full transition-colors duration-500"
        style={{ backgroundColor: tier.hex }}
      />

      <div className="p-5 flex-1 flex flex-col justify-between">
        {/* Card Header: Site ID & Quick Actions */}
        <div className="flex items-start justify-between gap-2 mb-4">
          <div className="flex items-center gap-2.5">
            <span
              className="w-2.5 h-2.5 rounded-full flex-shrink-0 animate-pulse"
              style={{ backgroundColor: tier.hex }}
            />
            <div>
              <h3 className="text-base font-bold text-slate-900 tracking-tight flex items-center gap-2 group-hover:text-indigo-600 transition-colors">
                {site.name || siteId}
              </h3>
              <div className="flex items-center gap-2 text-[11px] text-slate-500 font-mono">
                {site.name && <span className="text-slate-400">[{siteId}]</span>}
                <span>Updated {formatRelativeTime(site.last_seen || latest.timestamp)}</span>
              </div>
              {site.target_url && (
                <a
                  href={site.target_url}
                  target="_blank"
                  rel="noreferrer"
                  onClick={(e) => e.stopPropagation()}
                  className="text-[10px] text-indigo-600 hover:text-indigo-700 flex items-center gap-1 font-mono truncate max-w-[200px] mt-0.5"
                >
                  <span>{site.target_url.replace(/^https?:\/\//, '')}</span>
                </a>
              )}
            </div>
          </div>

          <div className="flex items-center gap-1.5">
            {onDelete && (
              <button
                onClick={(e) => {
                  e.stopPropagation();
                  onDelete(site);
                }}
                title="Remove site from monitoring"
                className="p-1.5 rounded-lg text-slate-400 hover:text-rose-600 hover:bg-rose-50 transition-colors"
              >
                <Trash2 className="w-4 h-4" />
              </button>
            )}
            <button
              onClick={(e) => {
                e.stopPropagation();
                onOpenThresholds(siteId);
              }}
              title="Configure site alert thresholds"
              className="p-1.5 rounded-lg text-slate-400 hover:text-slate-700 hover:bg-slate-100 transition-colors"
            >
              <Sliders className="w-4 h-4" />
            </button>
            <button
              onClick={() => onSelect(siteId)}
              title="Open full telemetry detail"
              className="p-1.5 rounded-lg text-slate-400 hover:text-indigo-600 hover:bg-indigo-50 transition-colors"
            >
              <ArrowRight className="w-4 h-4" />
            </button>
          </div>
        </div>

        {/* Middle Section: Gauge + Explainability & ETA */}
        <div className="grid grid-cols-1 md:grid-cols-12 gap-4 items-center bg-slate-50/80 rounded-xl p-3.5 border border-slate-200/60 mb-4 shadow-2xs">
          {/* Gauge Column */}
          <div className="md:col-span-5 flex flex-col items-center justify-center border-b md:border-b-0 md:border-r border-slate-200/80 pb-3 md:pb-0 md:pr-3">
            <span className="text-[10px] font-semibold uppercase tracking-wider text-slate-500 mb-1">
              Congestion Risk
            </span>
            <RiskGauge score={score} size="md" customThresholds={customThresholds} />
          </div>

          {/* Explainability & ETA Column */}
          <div className="md:col-span-7 flex flex-col justify-center space-y-2">
            {/* Time-To-Congestion ETA */}
            {isElevated ? (
              <div
                className={`flex items-center gap-2 px-2.5 py-1.5 rounded-lg border text-xs font-semibold shadow-2xs ${
                  tier.tier === 'CRITICAL'
                    ? 'bg-rose-50 border-rose-200 text-rose-700'
                    : tier.tier === 'WARNING'
                    ? 'bg-orange-50 border-orange-200 text-orange-700'
                    : 'bg-amber-50 border-amber-200 text-amber-700'
                }`}
              >
                <Clock className="w-3.5 h-3.5 flex-shrink-0 animate-bounce" />
                <span>
                  {etaMinutes !== null && etaMinutes !== undefined
                    ? `~${Math.round(etaMinutes)} min until critical breach`
                    : 'Elevated congestion trajectory'}
                </span>
              </div>
            ) : (
              <div className="flex items-center gap-2 px-2.5 py-1.5 rounded-lg bg-emerald-50 border border-emerald-200 text-emerald-700 text-xs font-medium shadow-2xs">
                <ShieldCheck className="w-3.5 h-3.5 flex-shrink-0" />
                <span>Operating within normal seasonal bounds</span>
              </div>
            )}

            {/* Explainability Callout (WHY) */}
            <div className="text-xs">
              <div className="text-slate-500 text-[11px] font-medium uppercase tracking-wider mb-0.5">
                Primary Contributor:
              </div>
              {primaryBottleneck ? (
                <div className="bg-white border border-slate-200/80 rounded-lg p-2 text-slate-800 shadow-2xs">
                  <div className="font-semibold text-slate-900 flex items-center justify-between">
                    <span>{getMetricDisplayName(primaryBottleneck)}</span>
                    {topFactor && (
                      <span className="text-[11px] font-mono font-bold text-orange-600">
                        {Math.round(topFactor.percentage_contribution)}% of risk
                      </span>
                    )}
                  </div>
                  <p className="text-[11px] text-slate-500 mt-1 leading-relaxed">
                    {topFactor?.reason || `Telemetry departing from diurnal expectations for this time slot.`}
                  </p>
                </div>
              ) : (
                <p className="text-[11px] text-slate-500 leading-relaxed italic">
                  All metrics steady within expected EWMA confidence intervals.
                </p>
              )}
            </div>
          </div>
        </div>

        {/* Auto-Remediation Live Hook Banner */}
        {remediation && (
          <div className="mb-3.5 p-2.5 rounded-xl bg-indigo-50 border border-indigo-200 text-indigo-900 text-xs flex items-center justify-between gap-2 shadow-2xs animate-fadeIn">
            <div className="flex items-center gap-2">
              <Zap className="w-4 h-4 text-indigo-600 flex-shrink-0 animate-pulse" />
              <span className="font-semibold text-indigo-950">
                {remediation.message || "Auto-remediation triggered: scaled from 2 to 4 instances."}
              </span>
            </div>
            <span className="text-[10px] px-2 py-0.5 rounded-md bg-indigo-100 text-indigo-700 font-mono font-semibold flex-shrink-0 border border-indigo-200">
              {remediation.new_instances || 4} INSTANCES
            </span>
          </div>
        )}

        {/* SHAP-Style Compact Attribution Bar */}
        <div className="mb-3">
          <ShapAttributionBar
            factors={contributingFactors}
            isElevated={isElevated}
            compact={true}
          />
        </div>

        {/* 4-Metric Sparklines Grid */}
        <div className="space-y-1.5 mb-3">
          <div className="flex items-center justify-between text-[11px] text-slate-500 font-semibold px-0.5">
            <span>30m Metric Trends</span>
            <span className="text-[10px] text-slate-400">Live Window</span>
          </div>
          <div className="grid grid-cols-2 gap-2">
            <MetricSparkline
              label="Active Users"
              values={activeUsersSeries}
              currentValue={latest.active_users}
              unit="users"
              color="#059669"
              isElevated={primaryBottleneck === 'active_users'}
            />
            <MetricSparkline
              label="Throughput"
              values={rpsSeries}
              currentValue={latest.request_rate}
              unit="RPS"
              color="#6366F1"
              isElevated={primaryBottleneck === 'request_rate'}
            />
            <MetricSparkline
              label="Avg Latency"
              values={latencySeries}
              currentValue={latest.avg_response_time_ms}
              unit="ms"
              color="#D97706"
              isElevated={primaryBottleneck === 'avg_response_time_ms' || latest.avg_response_time_ms > 300}
              alertColor={latest.avg_response_time_ms > 300 ? '#DC2626' : null}
            />
            <MetricSparkline
              label="Error Rate"
              values={errorSeries}
              currentValue={latest.error_rate_percent}
              unit="%"
              color="#DC2626"
              isElevated={primaryBottleneck === 'error_rate_percent' || latest.error_rate_percent > 2.0}
              alertColor={latest.error_rate_percent > 2.0 ? '#DC2626' : null}
            />
          </div>
        </div>
      </div>

      {/* Card Action Footer */}
      <button
        onClick={() => onSelect(siteId)}
        className="w-full py-2.5 px-4 bg-slate-50/80 hover:bg-indigo-50/60 border-t border-slate-200/80 text-xs font-semibold text-slate-700 hover:text-indigo-600 flex items-center justify-center gap-1.5 transition-all"
      >
        <span>Inspect Deep Dive & Seasonal Baselines</span>
        <ArrowRight className="w-3.5 h-3.5 group-hover:translate-x-1 transition-transform" />
      </button>
    </div>
  );
}
