import React, { useState } from 'react';
import { AlertCircle, AlertTriangle, CheckCircle, Bell, Filter, Clock, GitCommit, Trash2, X } from 'lucide-react';
import { formatTime, formatRelativeTime, formatNumber } from '../utils/formatters';

export default function AlertHistoryList({
  alerts = [],
  selectedSite = null,
  onSelectSite = null,
  onClearAlerts = null,
  onDismissAlert = null,
}) {
  const [filterSite, setFilterSite] = useState(false);

  const filteredAlerts = filterSite && selectedSite
    ? alerts.filter((a) => a.site_id === selectedSite)
    : alerts;

  return (
    <div className="bg-white/90 backdrop-blur-md rounded-2xl border border-slate-200/80 shadow-md flex flex-col h-full overflow-hidden">
      {/* Panel Header */}
      <div className="p-4 border-b border-slate-200/80 flex items-center justify-between">
        <div className="flex items-center gap-2">
          <Bell className="w-4 h-4 text-indigo-600" />
          <h2 className="text-sm font-bold text-slate-900 tracking-tight">
            Congestion Alert History
          </h2>
          <span className="px-2 py-0.5 rounded-full bg-slate-100 text-slate-700 font-mono text-xs font-semibold">
            {filteredAlerts.length}
          </span>
        </div>

        <div className="flex items-center gap-2">
          {filteredAlerts.length > 0 && (
            <button
              onClick={() => onClearAlerts && onClearAlerts(filterSite && selectedSite ? selectedSite : null)}
              className="flex items-center gap-1.5 px-2.5 py-1 rounded-lg text-xs font-medium text-slate-600 hover:text-rose-600 hover:bg-rose-50 border border-slate-200 hover:border-rose-200 transition-colors shadow-2xs"
              title={filterSite && selectedSite ? `Clear alerts for ${selectedSite}` : "Clear all alerts"}
            >
              <Trash2 className="w-3.5 h-3.5" />
              <span>{filterSite && selectedSite ? 'Clear site' : 'Clear all'}</span>
            </button>
          )}

          {selectedSite && (
            <button
              onClick={() => setFilterSite(!filterSite)}
              className={`flex items-center gap-1.5 px-2.5 py-1 rounded-lg text-xs font-medium transition-colors ${
                filterSite
                  ? 'bg-indigo-600 text-white'
                  : 'bg-slate-100 text-slate-700 hover:bg-slate-200'
              }`}
            >
              <Filter className="w-3 h-3" />
              <span>{filterSite ? selectedSite : 'Filter site'}</span>
            </button>
          )}
        </div>
      </div>

      {/* Timeline Feed */}
      <div className="p-4 flex-1 overflow-y-auto space-y-3 max-h-[480px]">
        {filteredAlerts.length === 0 ? (
          <div className="text-center py-12 px-4">
            <CheckCircle className="w-8 h-8 text-emerald-500 mx-auto mb-2" />
            <h4 className="text-sm font-semibold text-slate-800">No Congestion Incidents</h4>
            <p className="text-xs text-slate-500 mt-1 max-w-xs mx-auto">
              Monitored sites are operating within standard seasonal limits. Alerts will record here when risk thresholds are breached.
            </p>
          </div>
        ) : (
          filteredAlerts.map((alert, idx) => {
            const levelUpper = (alert.level || 'WARNING').toUpperCase();
            const isCrit = levelUpper.includes('CRIT');
            const isResolved = levelUpper.includes('RESOLVED');

            // Check if root-cause correlation hypothesis is present in the alert message
            const hasCorrelatedCause = alert.message && alert.message.includes('Suggested Cause:');
            let mainMessage = alert.message || '';
            let correlatedText = '';
            if (hasCorrelatedCause) {
              const parts = alert.message.split('Suggested Cause:');
              mainMessage = parts[0].trim();
              correlatedText = parts[1].trim();
            }

            return (
              <div
                key={alert.id || idx}
                onClick={() => onSelectSite && onSelectSite(alert.site_id)}
                className={`p-3.5 rounded-xl border text-xs transition-all cursor-pointer shadow-2xs ${
                  isCrit
                    ? 'bg-rose-50/70 border-rose-200/90 hover:border-rose-300 text-rose-950'
                    : isResolved
                    ? 'bg-emerald-50/70 border-emerald-200/90 hover:border-emerald-300 text-emerald-950'
                    : 'bg-orange-50/70 border-orange-200/90 hover:border-orange-300 text-orange-950'
                }`}
              >
                <div className="flex items-start justify-between gap-2 mb-1.5">
                  <div className="flex items-center gap-1.5">
                    {isCrit ? (
                      <AlertCircle className="w-4 h-4 text-rose-600 flex-shrink-0" />
                    ) : isResolved ? (
                      <CheckCircle className="w-4 h-4 text-emerald-600 flex-shrink-0" />
                    ) : (
                      <AlertTriangle className="w-4 h-4 text-orange-600 flex-shrink-0" />
                    )}
                    <span className="font-bold tracking-tight">
                      {alert.site_id}
                    </span>
                    <span
                      className={`text-[10px] font-mono uppercase px-1.5 py-0.2 rounded font-semibold ${
                        isCrit
                          ? 'bg-rose-100 text-rose-700 border border-rose-200'
                          : isResolved
                          ? 'bg-emerald-100 text-emerald-700 border border-emerald-200'
                          : 'bg-orange-100 text-orange-700 border border-orange-200'
                      }`}
                    >
                      {alert.level}
                    </span>
                  </div>

                  <div className="flex items-center gap-1.5 flex-shrink-0">
                    <span className="text-[10px] text-slate-500 font-mono whitespace-nowrap">
                      {formatTime(alert.timestamp)}
                    </span>
                    {onDismissAlert && (
                      <button
                        onClick={(e) => {
                          e.stopPropagation();
                          onDismissAlert(alert.alert_id || alert.id);
                        }}
                        className="p-0.5 rounded text-slate-400 hover:text-rose-600 hover:bg-rose-100/60 transition-colors"
                        title="Dismiss this alert"
                      >
                        <X className="w-3.5 h-3.5" />
                      </button>
                    )}
                  </div>
                </div>

                <p className="text-slate-700 leading-relaxed mb-2 font-medium">
                  {mainMessage}
                </p>

                {/* Root-Cause Correlation Hypothesis Banner */}
                {hasCorrelatedCause && (
                  <div className="mb-2 p-2 rounded-lg bg-indigo-50/80 border border-indigo-200 text-indigo-950 flex items-start gap-1.5 shadow-2xs">
                    <GitCommit className="w-3.5 h-3.5 text-indigo-600 flex-shrink-0 mt-0.5" />
                    <div className="text-[11px] leading-snug">
                      <span className="font-bold text-indigo-900">Root Cause Hypothesis: </span>
                      <span className="text-indigo-800">{correlatedText}</span>
                    </div>
                  </div>
                )}

                {/* Triggering Metrics Pill Row */}
                {alert.metrics && (
                  <div className="flex flex-wrap items-center gap-2 pt-1 border-t border-slate-200/60 text-[10px] font-mono text-slate-600">
                    {alert.metrics.request_rate !== undefined && (
                      <span>RPS: <strong>{formatNumber(alert.metrics.request_rate)}</strong></span>
                    )}
                    {alert.metrics.avg_response_time_ms !== undefined && (
                      <span>Lat: <strong>{Math.round(alert.metrics.avg_response_time_ms)}ms</strong></span>
                    )}
                    {alert.metrics.error_rate_percent !== undefined && (
                      <span>Err: <strong>{alert.metrics.error_rate_percent.toFixed(2)}%</strong></span>
                    )}
                    {alert.risk_score !== undefined && (
                      <span className="ml-auto font-bold text-slate-800">
                        Score: {Math.round(alert.risk_score)}
                      </span>
                    )}
                  </div>
                )}
              </div>
            );
          })
        )}
      </div>
    </div>
  );
}
