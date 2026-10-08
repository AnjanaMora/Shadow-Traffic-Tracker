import React from 'react';
import { Activity, Radio, Bell, ShieldAlert, Cpu, Building2, Plus, Sparkles } from 'lucide-react';

export default function Header({
  wsStatus = 'connected',
  reconnectCount = 0,
  siteCount = 0,
  alertCount = 0,
  onToggleAlerts,
  showAlerts = false,
  onOpenRegisterModal,
  tenantProfile = null,
}) {
  const isWsConnected = wsStatus === 'connected';
  const isWsReconnecting = wsStatus === 'reconnecting';
  const orgName = tenantProfile?.organization_name || 'Acme Global Ops';
  const planTier = tenantProfile?.plan_tier || 'Enterprise Pro';

  return (
    <header className="flex flex-wrap items-center justify-between gap-4 py-3.5 px-6 bg-white/80 border-b border-slate-200/80 backdrop-blur-md sticky top-0 z-40 shadow-xs">
      {/* Brand & Tagline */}
      <div className="flex items-center gap-3">
        <div className="w-9 h-9 rounded-xl bg-gradient-to-br from-indigo-500 via-purple-500 to-indigo-600 flex items-center justify-center shadow-md shadow-indigo-500/25 border border-indigo-400/30">
          <Activity className="w-5 h-5 text-white" />
        </div>
        <div>
          <div className="flex items-center gap-2">
            <h1 className="text-base font-black tracking-tight text-slate-900 uppercase font-mono">
              Shadow Traffic
            </h1>
            <span className="text-[10px] font-bold px-1.5 py-0.5 rounded-md bg-indigo-50 text-indigo-700 border border-indigo-200">
              v0.2
            </span>
          </div>
          <p className="text-[11px] text-slate-500 font-medium">
            Preemptive Congestion Forecasting & Seasonal Telemetry Guard
          </p>
        </div>
      </div>

      {/* Status Badges & Quick Stats */}
      <div className="flex items-center gap-3">
        {/* Tenant Organization & Plan Tier Pill */}
        <div className="hidden md:flex items-center gap-2 px-3 py-1.5 rounded-xl bg-slate-50/80 border border-slate-200 text-xs text-slate-700 shadow-2xs">
          <Building2 className="w-3.5 h-3.5 text-indigo-600" />
          <span className="font-semibold text-slate-800">{orgName}</span>
          <span className="text-[10px] font-bold px-1.5 py-0.2 rounded-md bg-indigo-100 text-indigo-700 border border-indigo-200">
            {planTier}
          </span>
        </div>

        {/* Monitored Sites Badge */}
        <div className="hidden sm:flex items-center gap-1.5 px-3 py-1.5 rounded-xl bg-slate-50/80 border border-slate-200 text-xs text-slate-600 shadow-2xs">
          <Radio className="w-3.5 h-3.5 text-indigo-600" />
          <span>Sites:</span>
          <span className="font-mono font-bold text-slate-900">{siteCount}</span>
        </div>

        {/* Add Website SaaS CTA */}
        {onOpenRegisterModal && (
          <button
            onClick={onOpenRegisterModal}
            className="flex items-center gap-1.5 px-3 py-1.5 rounded-xl text-xs font-semibold bg-indigo-600 hover:bg-indigo-700 text-white shadow-md shadow-indigo-600/20 transition-all border border-indigo-500"
          >
            <Plus className="w-3.5 h-3.5" />
            <span>Add Website</span>
          </button>
        )}

        {/* WebSocket Live Connection Pill */}
        <div className="flex items-center gap-2 px-3 py-1.5 rounded-xl bg-slate-50/80 border border-slate-200 text-xs shadow-2xs">
          <span
            className={`w-2 h-2 rounded-full ${
              isWsConnected
                ? 'bg-emerald-500 shadow-[0_0_8px_rgba(16,185,129,0.8)] animate-pulse'
                : isWsReconnecting
                ? 'bg-amber-500 animate-ping'
                : 'bg-slate-400'
            }`}
          />
          <span className="font-mono text-[11px] text-slate-600">
            {isWsConnected
              ? 'Live Stream'
              : isWsReconnecting
              ? `Reconnecting... (${reconnectCount})`
              : 'REST Polling'}
          </span>
        </div>

        {/* Kinetic White Theme Pill */}
        <div className="hidden lg:flex items-center gap-1.5 px-2.5 py-1.5 rounded-xl bg-indigo-50/80 border border-indigo-200/80 text-xs text-indigo-700 shadow-2xs">
          <Sparkles className="w-3.5 h-3.5 text-indigo-600 animate-pulse" />
          <span className="text-[11px] font-semibold text-indigo-900">Kinetic White</span>
        </div>

        {/* Alert Feed Toggle Button */}
        <button
          onClick={onToggleAlerts}
          className={`flex items-center gap-1.5 px-3 py-1.5 rounded-xl text-xs font-semibold transition-all border shadow-2xs ${
            showAlerts
              ? 'bg-indigo-600 border-indigo-500 text-white shadow-md shadow-indigo-600/25'
              : alertCount > 0
              ? 'bg-orange-50 border-orange-200 text-orange-700 hover:bg-orange-100'
              : 'bg-white border-slate-200 text-slate-700 hover:bg-slate-50'
          }`}
        >
          <Bell className="w-3.5 h-3.5" />
          <span>Alerts</span>
          {alertCount > 0 && (
            <span className="px-1.5 py-0.2 rounded-full bg-orange-600 text-white font-mono text-[10px] font-bold">
              {alertCount}
            </span>
          )}
        </button>
      </div>
    </header>
  );
}
