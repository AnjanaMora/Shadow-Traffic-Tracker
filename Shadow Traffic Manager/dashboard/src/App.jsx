import React, { useState, useEffect, useCallback } from 'react';
import Header from './components/Header';
import SiteCard from './components/SiteCard';
import DetailView from './components/DetailView';
import AlertHistoryList from './components/AlertHistoryList';
import ThresholdModal from './components/ThresholdModal';
import RegisterSiteModal from './components/RegisterSiteModal';
import DeleteSiteModal from './components/DeleteSiteModal';
import SiteStream from './components/SiteStream';
import { LoadingSkeleton, ErrorState, EmptyState } from './components/EmptyOrErrorState';
import { ShieldAlert, Activity, CheckCircle2, Search } from 'lucide-react';

export default function App() {
  const [sites, setSites] = useState([]);
  const [tenantProfile, setTenantProfile] = useState(null);
  const [showRegisterModal, setShowRegisterModal] = useState(false);
  const [deleteModalSite, setDeleteModalSite] = useState(null);
  const [selectedSiteId, setSelectedSiteId] = useState(null);
  const [siteStatuses, setSiteStatuses] = useState({});
  const [metricsHistory, setMetricsHistory] = useState({});
  const [alerts, setAlerts] = useState([]);
  const [thresholds, setThresholds] = useState({});
  const [showAlertDrawer, setShowAlertDrawer] = useState(false);
  const [thresholdModalSite, setThresholdModalSite] = useState(null);
  const [searchQuery, setSearchQuery] = useState('');
  const [isLoading, setIsLoading] = useState(true);
  const [error, setError] = useState(null);

  // Per-site WebSocket connection status, keyed by site_id.
  // (Replaces the old single "activeStreamSite" approach — see SiteStream.jsx
  // for why every site now needs its own independent connection.)
  const [wsStatusBySite, setWsStatusBySite] = useState({});

  const handleWsStatusChange = useCallback((siteId, status) => {
    setWsStatusBySite((prev) =>
      prev[siteId] === status ? prev : { ...prev, [siteId]: status }
    );
  }, []);

  // WebSocket message handler
  const handleWsMessage = useCallback((payload) => {
    if (!payload || payload.type !== 'telemetry_update') return;

    const { site_id, metric, risk, alert_fired, remediation, current_instances } = payload;
    if (!site_id) return;

    // Update time-series metrics stream (keep last 60 points)
    if (metric) {
      setMetricsHistory((prev) => {
        const existing = prev[site_id] || [];
        const updated = [...existing, metric].slice(-60);
        return { ...prev, [site_id]: updated };
      });
    }

    // Update site status, risk assessment, and auto-remediation state
    setSiteStatuses((prev) => {
      const current = prev[site_id] || {};
      return {
        ...prev,
        [site_id]: {
          ...current,
          site_id,
          current_risk_score: risk?.score ?? current.current_risk_score ?? 0,
          status: risk?.status ?? current.status ?? 'Normal',
          eta_minutes: risk?.eta_minutes ?? current.eta_minutes,
          primary_bottleneck: risk?.primary_bottleneck ?? current.primary_bottleneck,
          timestamp: metric?.timestamp ?? current.timestamp ?? new Date().toISOString(),
          active_remediation: remediation !== undefined ? remediation : current.active_remediation,
          current_instances: current_instances ?? current.current_instances ?? 2,
        },
      };
    });

    // Update site in the sites list
    setSites((prev) =>
      prev.map((s) =>
        s.site_id === site_id
          ? {
              ...s,
              last_seen: metric.timestamp,
              active_users: metric.active_users,
              current_rps: metric.request_rate,
              current_latency_ms: metric.avg_response_time_ms,
              current_error_rate: metric.error_rate_percent,
              current_status: risk?.status ?? s.current_status,
              risk_score: risk?.score ?? s.risk_score,
            }
          : s
      )
    );

    // If an alert was fired, fetch the fresh alert log
    if (alert_fired) {
      fetchAlerts();
    }
  }, []);

  // Aggregate connection status across all per-site streams, for the header
  // indicator and the detail-view "live" badge.
  const connectedSiteCount = Object.values(wsStatusBySite).filter((s) => s === 'connected').length;
  const isWsConnected = connectedSiteCount > 0;
  const wsStatus = sites.length === 0
    ? 'disconnected'
    : connectedSiteCount === sites.length
    ? 'connected'
    : connectedSiteCount > 0
    ? 'connected' // partially connected still reads as "connected" to the user
    : 'reconnecting';
  const reconnectCount = 0; // per-site reconnects are handled individually; no single counter to show

  // REST Data Fetchers
  const fetchSites = async () => {
    try {
      const res = await fetch('/api/sites');
      if (!res.ok) throw new Error(`HTTP ${res.status}`);
      const data = await res.json();
      return Array.isArray(data) ? data : [];
    } catch {
      return [];
    }
  };

  const fetchTenantProfile = async () => {
    try {
      const res = await fetch('/api/account');
      if (res.ok) {
        const data = await res.json();
        setTenantProfile(data);
      }
    } catch {
      // ignore
    }
  };

  const fetchSiteStatus = async (siteId) => {
    try {
      const res = await fetch(`/api/status/${encodeURIComponent(siteId)}`);
      if (!res.ok) return null;
      return await res.json();
    } catch {
      return null;
    }
  };

  const fetchAlerts = async () => {
    try {
      const res = await fetch('/api/alerts?limit=50');
      if (res.ok) {
        const data = await res.json();
        setAlerts(Array.isArray(data) ? data : []);
      }
    } catch {
      // ignore
    }
  };

  // Initial load
  const loadInitialData = async () => {
    setIsLoading(true);
    setError(null);
    try {
      await fetchTenantProfile();
      let siteList = await fetchSites();

      // If backend returns no sites yet (e.g. collector hasn't posted yet),
      // provide default monitored sites for seamless out-of-the-box demo
      if (siteList.length === 0) {
        siteList = [
          {
            site_id: 'shadow-ecommerce-prod',
            last_seen: new Date().toISOString(),
            current_status: 'Warning',
            risk_score: 68.5,
            active_users: 1420,
            current_rps: 420.5,
            current_latency_ms: 385.0,
            current_error_rate: 2.1,
          },
          {
            site_id: 'shadow-payment-gateway',
            last_seen: new Date().toISOString(),
            current_status: 'Normal',
            risk_score: 18.0,
            active_users: 820,
            current_rps: 215.0,
            current_latency_ms: 64.2,
            current_error_rate: 0.05,
          },
          {
            site_id: 'shadow-auth-service',
            last_seen: new Date().toISOString(),
            current_status: 'Watch',
            risk_score: 48.0,
            active_users: 2100,
            current_rps: 650.0,
            current_latency_ms: 195.4,
            current_error_rate: 0.8,
          },
        ];
      }

      setSites(siteList);

      // Fetch status & historical window for each site
      const statuses = {};
      const historyMap = {};

      for (const s of siteList) {
        const statusRes = await fetchSiteStatus(s.site_id);
        if (statusRes) {
          statuses[s.site_id] = statusRes;
          if (statusRes.recent_metrics_30m && statusRes.recent_metrics_30m.length >= 5) {
            historyMap[s.site_id] = statusRes.recent_metrics_30m;
          }
        }

        // If no history returned from backend or fewer than 5 points, generate realistic initial points
        if (!historyMap[s.site_id] || historyMap[s.site_id].length < 5) {
          const now = Date.now();
          const baseUsers = s.active_users || 12000;
          const baseRps = s.current_rps || 420;
          const baseLat = s.current_latency_ms || 95;
          const baseErr = s.current_error_rate || 0.1;
          const mockPoints = Array.from({ length: 20 }).map((_, i) => {
            const time = new Date(now - (20 - i) * 60000).toISOString();
            const jitter = 0.95 + (Math.sin(i * 0.45) * 0.08);
            return {
              site_id: s.site_id,
              timestamp: time,
              active_users: Math.round(baseUsers * jitter),
              request_rate: Number((baseRps * jitter).toFixed(1)),
              avg_response_time_ms: Number((baseLat * jitter).toFixed(1)),
              error_rate_percent: Number((baseErr * (0.8 + Math.random() * 0.4)).toFixed(2)),
            };
          });
          historyMap[s.site_id] = mockPoints;

          // Provide realistic baseline factors if empty
          if (!statuses[s.site_id]) {
            statuses[s.site_id] = {
              site_id: s.site_id,
              timestamp: new Date().toISOString(),
              current_risk_score: s.risk_score || 25,
              status: s.current_status || 'Normal',
              eta_minutes: s.current_status === 'Warning' ? 18.5 : null,
              primary_bottleneck: s.current_status === 'Warning' ? 'avg_response_time_ms' : null,
              contributing_factors: [
                {
                  metric: 'avg_response_time_ms',
                  current_value: s.current_latency_ms || 120,
                  baseline_mean: 85.0,
                  baseline_std: 15.0,
                  z_score: s.current_status === 'Warning' ? 3.4 : 0.8,
                  percentage_contribution: 58.0,
                  reason: 'Latency (+3.4σ above diurnal normal) is primary bottleneck driver.',
                },
                {
                  metric: 'request_rate',
                  current_value: s.current_rps || 300,
                  baseline_mean: 280.0,
                  baseline_std: 35.0,
                  z_score: 1.2,
                  percentage_contribution: 22.0,
                  reason: 'Throughput is tracking upper seasonal boundary.',
                },
                {
                  metric: 'active_users',
                  current_value: s.active_users || 1000,
                  baseline_mean: 950.0,
                  baseline_std: 120.0,
                  z_score: 0.5,
                  percentage_contribution: 10.0,
                  reason: 'Concurrency load within normal diurnal parameters.',
                },
                {
                  metric: 'error_rate_percent',
                  current_value: s.current_error_rate || 0.5,
                  baseline_mean: 0.25,
                  baseline_std: 0.1,
                  z_score: 1.1,
                  percentage_contribution: 10.0,
                  reason: 'Minor 5xx rate elevation.',
                },
              ],
            };
          }
        }
      }

      setSiteStatuses(statuses);
      setMetricsHistory(historyMap);
      await fetchAlerts();
    } catch (err) {
      setError(err.message || 'Failed to initialize dashboard');
    } finally {
      setIsLoading(false);
    }
  };

  useEffect(() => {
    loadInitialData();

    // Polling interval fallback for sites and alerts
    const interval = setInterval(() => {
      fetchAlerts();
    }, 5000);

    return () => clearInterval(interval);
  }, []);

  // Handle setting thresholds
  const handleSaveThresholds = async (siteId, { warning_threshold, critical_threshold }) => {
    const res = await fetch(`/api/sites/${encodeURIComponent(siteId)}/thresholds`, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ warning_threshold, critical_threshold }),
    });

    if (!res.ok) {
      const err = await res.json().catch(() => ({}));
      throw new Error(err.detail || 'Failed to update thresholds');
    }

    setThresholds((prev) => ({
      ...prev,
      [siteId]: { warning: warning_threshold, critical: critical_threshold },
    }));
  };

  // Handle clear alerts (all or per-site)
  const handleClearAlerts = async (siteId = null) => {
    try {
      const url = siteId ? `/api/alerts?site_id=${encodeURIComponent(siteId)}` : '/api/alerts';
      const res = await fetch(url, { method: 'DELETE' });
      if (res.ok) {
        if (siteId) {
          setAlerts((prev) => prev.filter((a) => a.site_id !== siteId));
        } else {
          setAlerts([]);
        }
      }
    } catch (err) {
      console.error('Failed to clear alerts:', err);
    }
  };

  // Handle single alert dismissal
  const handleDismissAlert = async (alertId) => {
    if (!alertId) return;
    try {
      const res = await fetch(`/api/alerts?alert_id=${encodeURIComponent(alertId)}`, { method: 'DELETE' });
      if (res.ok) {
        setAlerts((prev) => prev.filter((a) => (a.alert_id || a.id) !== alertId));
      }
    } catch (err) {
      console.error('Failed to dismiss alert:', err);
    }
  };

  // Handle site deletion
  const handleDeleteSite = async (siteId) => {
    const res = await fetch(`/api/sites/${encodeURIComponent(siteId)}?purge=true`, {
      method: 'DELETE',
    });
    if (!res.ok) {
      const err = await res.json().catch(() => ({}));
      throw new Error(err.detail || 'Failed to remove website');
    }

    // 1. Remove from sites list
    setSites((prev) => prev.filter((s) => s.site_id !== siteId));

    // 2. Remove from siteStatuses and metricsHistory
    setSiteStatuses((prev) => {
      const copy = { ...prev };
      delete copy[siteId];
      return copy;
    });
    setMetricsHistory((prev) => {
      const copy = { ...prev };
      delete copy[siteId];
      return copy;
    });

    // 3. Remove from wsStatusBySite
    setWsStatusBySite((prev) => {
      const copy = { ...prev };
      delete copy[siteId];
      return copy;
    });

    // 4. If the deleted site was open in detail view, return to grid
    if (selectedSiteId === siteId) {
      setSelectedSiteId(null);
    }

    // 5. Update tenantProfile registered_sites_count
    if (tenantProfile) {
      setTenantProfile((prev) => ({
        ...prev,
        registered_sites_count: Math.max(0, (prev?.registered_sites_count || 1) - 1),
      }));
    }

    // 6. Refresh alerts
    fetchAlerts();
  };

  // Filtered sites for search
  const filteredSites = sites.filter((s) =>
    s.site_id.toLowerCase().includes(searchQuery.toLowerCase())
  );

  // Global fleet summary statistics
  const elevatedSitesCount = sites.filter((s) => {
    const st = siteStatuses[s.site_id]?.status || s.current_status || 'Normal';
    return st !== 'Normal' && st !== 'LOW';
  }).length;

  const totalRps = sites.reduce((sum, s) => sum + (s.current_rps || 0), 0);

  return (
    <div className="min-h-screen bg-kinetic-white text-slate-900 flex flex-col font-sans selection:bg-indigo-600 selection:text-white relative overflow-x-hidden">
      {/* Dynamic Kinetic White Animated Aura Elements */}
      <div className="fixed inset-0 pointer-events-none overflow-hidden z-0" aria-hidden="true">
        {/* Kinetic Grid Pattern Overlay */}
        <div className="absolute inset-0 kinetic-grid-overlay opacity-70" />

        {/* Luminous Animated Kinetic Orbs */}
        <div className="absolute -top-32 -left-32 w-96 h-96 rounded-full bg-gradient-to-br from-indigo-400/25 via-purple-300/20 to-transparent blur-3xl animate-kinetic-orb-1" />
        <div className="absolute top-1/4 -right-28 w-[32rem] h-[32rem] rounded-full bg-gradient-to-bl from-sky-400/20 via-blue-300/15 to-transparent blur-3xl animate-kinetic-orb-2" />
        <div className="absolute -bottom-32 left-1/3 w-[36rem] h-[36rem] rounded-full bg-gradient-to-tr from-purple-400/20 via-pink-300/15 to-transparent blur-3xl animate-kinetic-orb-3" />
      </div>

      {/* Live telemetry connections — one independent WebSocket per site, so
          every card updates live regardless of which site (if any) is selected. */}
      {sites.map((s) => (
        <SiteStream
          key={s.site_id}
          siteId={s.site_id}
          onMessage={handleWsMessage}
          onStatusChange={handleWsStatusChange}
        />
      ))}

      {/* Top Header */}
      <div className="relative z-20">
        <Header
          wsStatus={wsStatus}
          reconnectCount={reconnectCount}
          siteCount={sites.length}
          alertCount={alerts.length}
          showAlerts={showAlertDrawer}
          onToggleAlerts={() => setShowAlertDrawer(!showAlertDrawer)}
          onOpenRegisterModal={() => setShowRegisterModal(true)}
          tenantProfile={tenantProfile}
        />
      </div>

      {/* Main Content Area */}
      <main className="flex-1 max-w-[1520px] w-full mx-auto p-4 sm:p-6 lg:p-8 space-y-6 relative z-10">
        {isLoading ? (
          <LoadingSkeleton count={3} />
        ) : error ? (
          <ErrorState message={error} onRetry={loadInitialData} />
        ) : selectedSiteId ? (
          /* Single Site Detail View with Recharts & Baseline Bands */
          <DetailView
            siteId={selectedSiteId}
            siteStatus={siteStatuses[selectedSiteId] || {}}
            history={metricsHistory[selectedSiteId] || []}
            assessment={siteStatuses[selectedSiteId] || {}}
            onBack={() => setSelectedSiteId(null)}
            onOpenThresholds={(id) => setThresholdModalSite(id)}
            customThresholds={thresholds[selectedSiteId]}
            isLive={isWsConnected}
          />
        ) : (
          /* Fleet Overview Grid */
          <div className="space-y-6 animate-fadeIn">
            {/* Fleet KPI Bar & Search Filter */}
            <div className="flex flex-wrap items-center justify-between gap-4 bg-white/90 backdrop-blur-md p-4 rounded-2xl border border-slate-200/80 shadow-md shadow-slate-200/50">
              <div className="flex items-center gap-6 flex-wrap">
                <div>
                  <span className="text-[11px] text-slate-500 font-medium uppercase tracking-wider">
                    Fleet Health
                  </span>
                  <div className="flex items-center gap-2 mt-0.5">
                    {elevatedSitesCount > 0 ? (
                      <span className="text-sm font-bold text-orange-600 flex items-center gap-1">
                        <ShieldAlert className="w-4 h-4" />
                        {elevatedSitesCount} site{elevatedSitesCount > 1 ? 's' : ''} elevated
                      </span>
                    ) : (
                      <span className="text-sm font-bold text-emerald-600 flex items-center gap-1">
                        <CheckCircle2 className="w-4 h-4" />
                        All {sites.length} targets stable
                      </span>
                    )}
                  </div>
                </div>

                <div className="h-8 w-[1px] bg-slate-200 hidden sm:block" />

                <div>
                  <span className="text-[11px] text-slate-500 font-medium uppercase tracking-wider">
                    Aggregated Fleet RPS
                  </span>
                  <div className="text-sm font-bold font-mono text-slate-900 mt-0.5">
                    {totalRps.toFixed(1)} req/s
                  </div>
                </div>

                <div className="h-8 w-[1px] bg-slate-200 hidden sm:block" />

                <div>
                  <span className="text-[11px] text-slate-500 font-medium uppercase tracking-wider">
                    Prediction Horizon
                  </span>
                  <div className="text-sm font-bold font-mono text-indigo-600 mt-0.5">
                    15 min forward
                  </div>
                </div>
              </div>

              {/* Search input */}
              <div className="relative w-full sm:w-64">
                <Search className="w-4 h-4 text-slate-400 absolute left-3 top-1/2 -translate-y-1/2" />
                <input
                  type="text"
                  placeholder="Filter targets by ID..."
                  value={searchQuery}
                  onChange={(e) => setSearchQuery(e.target.value)}
                  className="w-full pl-9 pr-3 py-1.5 rounded-xl bg-slate-50/80 border border-slate-200 text-xs text-slate-800 placeholder-slate-400 focus:outline-none focus:border-indigo-500 focus:bg-white transition-all shadow-2xs"
                />
              </div>
            </div>

            {/* Sites Grid & Alerts Drawer Layout */}
            <div className="grid grid-cols-1 lg:grid-cols-12 gap-6">
              {/* Monitored Site Cards */}
              <div className={showAlertDrawer ? 'lg:col-span-8' : 'lg:col-span-12'}>
                {filteredSites.length === 0 ? (
                  <EmptyState message="No monitored targets match your search filter." />
                ) : (
                  <div className="grid grid-cols-1 md:grid-cols-2 xl:grid-cols-3 gap-6">
                    {filteredSites.map((site) => (
                      <SiteCard
                        key={site.site_id}
                        site={site}
                        assessment={siteStatuses[site.site_id] || {}}
                        history={metricsHistory[site.site_id] || []}
                        onSelect={(id) => setSelectedSiteId(id)}
                        onOpenThresholds={(id) => setThresholdModalSite(id)}
                        onDelete={(s) => setDeleteModalSite(s)}
                        customThresholds={thresholds[site.site_id]}
                      />
                    ))}
                  </div>
                )}
              </div>

              {/* Alert Feed Panel */}
              {showAlertDrawer && (
                <div className="lg:col-span-4 animate-fadeIn">
                  <AlertHistoryList
                    alerts={alerts}
                    selectedSite={selectedSiteId}
                    onSelectSite={(id) => setSelectedSiteId(id)}
                    onClearAlerts={handleClearAlerts}
                    onDismissAlert={handleDismissAlert}
                  />
                </div>
              )}
            </div>
          </div>
        )}
      </main>

      {/* Thresholds Customization Modal */}
      <ThresholdModal
        siteId={thresholdModalSite}
        isOpen={Boolean(thresholdModalSite)}
        onClose={() => setThresholdModalSite(null)}
        currentThresholds={thresholds[thresholdModalSite]}
        onSave={handleSaveThresholds}
      />

      {/* SaaS Website Registration Modal */}
      <RegisterSiteModal
        isOpen={showRegisterModal}
        onClose={() => setShowRegisterModal(false)}
        onSiteRegistered={(newSite) => {
          setSites((prev) => [
            ...prev,
            {
              site_id: newSite.site_id,
              name: newSite.name,
              target_url: newSite.target_url,
              api_key: newSite.api_key,
              last_seen: new Date().toISOString(),
              current_status: 'Normal',
              risk_score: 10.0,
              active_users: 0,
              current_rps: 0,
              current_latency_ms: 0,
              current_error_rate: 0,
            },
          ]);
          if (tenantProfile) {
            setTenantProfile((prev) => ({
              ...prev,
              registered_sites_count: (prev?.registered_sites_count || 0) + 1,
            }));
          }
        }}
      />

      {/* Delete Website Confirmation Modal */}
      <DeleteSiteModal
        isOpen={Boolean(deleteModalSite)}
        site={deleteModalSite}
        onClose={() => setDeleteModalSite(null)}
        onConfirm={handleDeleteSite}
      />
    </div>
  );
}
