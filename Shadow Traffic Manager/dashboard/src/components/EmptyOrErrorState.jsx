import React from 'react';
import { AlertCircle, RefreshCw, Radio, ServerOff } from 'lucide-react';

export function LoadingSkeleton({ count = 3 }) {
  return (
    <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-3 gap-6 animate-pulse">
      {Array.from({ length: count }).map((_, idx) => (
        <div
          key={idx}
          className="bg-white/80 rounded-2xl border border-slate-200/80 p-5 space-y-4 shadow-sm"
        >
          <div className="flex justify-between items-center">
            <div className="h-5 bg-slate-200/70 rounded-lg w-36" />
            <div className="h-4 bg-slate-200/70 rounded-lg w-16" />
          </div>

          <div className="h-28 bg-slate-100/80 rounded-xl" />

          <div className="grid grid-cols-2 gap-2">
            <div className="h-14 bg-slate-100/90 rounded-xl" />
            <div className="h-14 bg-slate-100/90 rounded-xl" />
            <div className="h-14 bg-slate-100/90 rounded-xl" />
            <div className="h-14 bg-slate-100/90 rounded-xl" />
          </div>

          <div className="h-8 bg-slate-100/90 rounded-xl" />
        </div>
      ))}
    </div>
  );
}

export function ErrorState({ message = 'Unable to connect to backend gateway.', onRetry }) {
  return (
    <div className="bg-white/95 border border-rose-200 rounded-2xl p-8 text-center max-w-lg mx-auto shadow-xl my-12">
      <div className="w-12 h-12 rounded-full bg-rose-50 border border-rose-200 text-rose-600 flex items-center justify-center mx-auto mb-4 shadow-2xs">
        <ServerOff className="w-6 h-6" />
      </div>
      <h3 className="text-base font-bold text-slate-900">Gateway Connection Error</h3>
      <p className="text-xs text-slate-500 mt-2 leading-relaxed max-w-sm mx-auto">
        {message}
      </p>

      {onRetry && (
        <button
          onClick={onRetry}
          className="mt-5 inline-flex items-center gap-2 px-4 py-2 rounded-xl bg-indigo-600 hover:bg-indigo-700 text-xs font-semibold text-white transition-colors shadow-md shadow-indigo-600/20"
        >
          <RefreshCw className="w-3.5 h-3.5" />
          <span>Retry Connection</span>
        </button>
      )}
    </div>
  );
}

export function EmptyState({ message = 'No monitored sites currently reporting telemetry.' }) {
  return (
    <div className="bg-white/90 border border-slate-200/80 rounded-2xl p-10 text-center max-w-lg mx-auto my-12 shadow-sm">
      <div className="w-12 h-12 rounded-full bg-indigo-50 border border-indigo-100 text-indigo-600 flex items-center justify-center mx-auto mb-3 shadow-2xs">
        <Radio className="w-6 h-6 animate-pulse" />
      </div>
      <h3 className="text-base font-bold text-slate-900">Awaiting Inbound Telemetry</h3>
      <p className="text-xs text-slate-500 mt-2 leading-relaxed max-w-sm mx-auto">
        {message} Once collector agents begin publishing to <code>/api/metrics</code>, real-time sites and predictions will render automatically.
      </p>
    </div>
  );
}
