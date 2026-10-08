import React, { useState } from 'react';
import { X, Plus, Key, Terminal, ExternalLink, Check, Copy, AlertCircle, Globe } from 'lucide-react';

export default function RegisterSiteModal({ isOpen, onClose, onSiteRegistered }) {
  const [formData, setFormData] = useState({
    site_id: '',
    name: '',
    target_url: '',
    warning_threshold: 60.0,
    critical_threshold: 80.0,
    alert_webhook_url: '',
    alert_email: '',
  });

  const [isSubmitting, setIsSubmitting] = useState(false);
  const [error, setError] = useState(null);
  const [registeredResult, setRegisteredResult] = useState(null);
  const [copiedKey, setCopiedKey] = useState(false);
  const [copiedCmd, setCopiedCmd] = useState(false);
  const [showAdvanced, setShowAdvanced] = useState(false);

  if (!isOpen) return null;

  const handleChange = (e) => {
    const { name, value, type } = e.target;
    setFormData((prev) => ({
      ...prev,
      [name]: type === 'number' ? parseFloat(value) : value,
    }));
  };

  const handleSubmit = async (e) => {
    e.preventDefault();
    setError(null);
    setIsSubmitting(true);

    try {
      const res = await fetch('/api/sites', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({
          site_id: formData.site_id.trim().toLowerCase().replace(/\s+/g, '-'),
          name: formData.name.trim(),
          target_url: formData.target_url.trim() || null,
          warning_threshold: Number(formData.warning_threshold),
          critical_threshold: Number(formData.critical_threshold),
          alert_webhook_url: formData.alert_webhook_url.trim() || null,
          alert_email: formData.alert_email.trim() || null,
        }),
      });

      if (!res.ok) {
        const errData = await res.json();
        throw new Error(errData.detail || 'Registration failed');
      }

      const data = await res.json();
      setRegisteredResult(data);
      if (onSiteRegistered) {
        onSiteRegistered(data);
      }
    } catch (err) {
      setError(err.message);
    } finally {
      setIsSubmitting(false);
    }
  };

  const copyToClipboard = (text, type) => {
    navigator.clipboard.writeText(text);
    if (type === 'key') {
      setCopiedKey(true);
      setTimeout(() => setCopiedKey(false), 2000);
    } else {
      setCopiedCmd(true);
      setTimeout(() => setCopiedCmd(false), 2000);
    }
  };

  const handleDone = () => {
    setRegisteredResult(null);
    setShowAdvanced(false);
    setFormData({
      site_id: '',
      name: '',
      target_url: '',
      warning_threshold: 60.0,
      critical_threshold: 80.0,
      alert_webhook_url: '',
      alert_email: '',
    });
    onClose();
  };

  return (
    <div className="fixed inset-0 z-50 flex items-center justify-center p-4 bg-slate-900/40 backdrop-blur-sm animate-fadeIn">
      <div className="relative w-full max-w-xl bg-white/95 border border-slate-200 rounded-2xl shadow-2xl overflow-hidden text-slate-800">
        {/* Header */}
        <div className="flex items-center justify-between px-6 py-4 border-b border-slate-100 bg-slate-50/80">
          <div className="flex items-center gap-2.5">
            <div className="p-2 rounded-xl bg-indigo-50 text-indigo-600 border border-indigo-200">
              <Globe className="w-5 h-5" />
            </div>
            <div>
              <h2 className="text-base font-bold text-slate-900 tracking-tight">
                {registeredResult ? 'Site Registered Successfully' : 'Register New Website'}
              </h2>
              <p className="text-xs text-slate-500 font-mono">
                {registeredResult ? 'Live telemetry collection active' : 'Add an independent website to your organization account'}
              </p>
            </div>
          </div>
          <button
            onClick={handleDone}
            className="p-1.5 rounded-lg text-slate-400 hover:text-slate-700 hover:bg-slate-100 transition-colors"
          >
            <X className="w-5 h-5" />
          </button>
        </div>

        {registeredResult ? (
          /* Success Screen: Live Monitoring Started Automatically */
          <div className="p-6 space-y-4">
            <div className="p-4 rounded-xl bg-emerald-50 border border-emerald-200 text-emerald-800 flex items-start gap-3">
              <Check className="w-5 h-5 text-emerald-600 flex-shrink-0 mt-0.5" />
              <div>
                <h4 className="text-sm font-semibold text-emerald-900">
                  Website "{registeredResult.name}" is Live & Actively Monitored!
                </h4>
                <p className="text-xs text-emerald-700 mt-1">
                  Telemetry collection and early-warning risk analysis started automatically in the background. Real-time metrics and dynamic alerts are now streaming to your console with no manual setup needed.
                </p>
              </div>
            </div>

            {/* Live Monitoring Status Card */}
            <div className="p-3.5 bg-slate-50 rounded-xl border border-slate-200 text-xs space-y-2">
              <div className="flex items-center justify-between text-slate-700 font-medium">
                <span className="flex items-center gap-2">
                  <span className="relative flex h-2.5 w-2.5">
                    <span className="animate-ping absolute inline-flex h-full w-full rounded-full bg-emerald-400 opacity-75"></span>
                    <span className="relative inline-flex rounded-full h-2.5 w-2.5 bg-emerald-500"></span>
                  </span>
                  Live Telemetry Pipeline
                </span>
                <span className="px-2 py-0.5 rounded-full text-[10px] font-semibold bg-emerald-100 text-emerald-800">
                  Streaming Now
                </span>
              </div>
              <div className="grid grid-cols-2 gap-2 text-[11px] text-slate-600 pt-1 border-t border-slate-200/60 font-mono">
                <div>
                  <span className="text-slate-400">Site ID: </span>
                  <span className="font-semibold text-slate-800">{registeredResult.site_id}</span>
                </div>
                <div>
                  <span className="text-slate-400">Thresholds: </span>
                  <span className="text-orange-600 font-semibold">{registeredResult.warning_threshold}%</span>
                  <span className="text-slate-400"> / </span>
                  <span className="text-rose-600 font-semibold">{registeredResult.critical_threshold}%</span>
                </div>
              </div>
            </div>

            {/* De-emphasized / Optional External Collector Details */}
            <div className="border border-slate-200/80 rounded-xl overflow-hidden bg-white">
              <button
                type="button"
                onClick={() => setShowAdvanced(!showAdvanced)}
                className="w-full px-3.5 py-2.5 flex items-center justify-between text-left text-xs text-slate-600 hover:bg-slate-50 transition-colors"
              >
                <span className="font-medium flex items-center gap-1.5 text-slate-700">
                  <Key className="w-3.5 h-3.5 text-indigo-500" />
                  Optional: External Agent Credentials & Custom Collectors
                </span>
                <span className="text-[11px] text-slate-400">
                  {showAdvanced ? 'Hide' : 'Show'}
                </span>
              </button>

              {showAdvanced && (
                <div className="p-3.5 pt-0 border-t border-slate-100 space-y-3 bg-slate-50/50">
                  <p className="text-[11px] text-slate-500 mt-2">
                    Background telemetry is already streaming. If you additionally wish to push metrics directly from your own production servers (Nginx logs or Prometheus scraping), use this dedicated API key:
                  </p>

                  <div className="space-y-1">
                    <label className="text-[11px] font-semibold text-slate-600">Site API Key</label>
                    <div className="flex items-center gap-2 p-2 bg-slate-900 rounded-lg border border-slate-800 font-mono text-xs text-amber-300 break-all select-all">
                      <span className="flex-1">{registeredResult.api_key}</span>
                      <button
                        type="button"
                        onClick={() => copyToClipboard(registeredResult.api_key, 'key')}
                        className="px-2 py-1 rounded bg-slate-800 hover:bg-slate-700 text-slate-200 text-[10px] flex items-center gap-1 flex-shrink-0"
                      >
                        {copiedKey ? <Check className="w-3 h-3 text-emerald-400" /> : <Copy className="w-3 h-3" />}
                        <span>{copiedKey ? 'Copied' : 'Copy'}</span>
                      </button>
                    </div>
                  </div>

                  <div className="space-y-1">
                    <label className="text-[11px] font-semibold text-slate-600">CLI Collector Command</label>
                    <div className="flex items-center gap-2 p-2 bg-slate-900 rounded-lg border border-slate-800 font-mono text-xs text-emerald-400 break-all select-all">
                      <span className="flex-1 text-[11px]">{registeredResult.collector_command}</span>
                      <button
                        type="button"
                        onClick={() => copyToClipboard(registeredResult.collector_command, 'cmd')}
                        className="px-2 py-1 rounded bg-slate-800 hover:bg-slate-700 text-slate-200 text-[10px] flex items-center gap-1 flex-shrink-0"
                      >
                        {copiedCmd ? <Check className="w-3 h-3 text-emerald-400" /> : <Copy className="w-3 h-3" />}
                        <span>{copiedCmd ? 'Copied' : 'Copy'}</span>
                      </button>
                    </div>
                  </div>
                </div>
              )}
            </div>

            {/* Action Buttons */}
            <div className="pt-2 flex justify-end">
              <button
                type="button"
                onClick={handleDone}
                className="px-5 py-2.5 rounded-xl bg-indigo-600 hover:bg-indigo-700 text-white font-medium text-xs shadow-md shadow-indigo-600/25 transition-all"
              >
                Go to Dashboard
              </button>
            </div>
          </div>
        ) : (
          /* Form Screen */
          <form onSubmit={handleSubmit} className="p-6 space-y-4">
            {error && (
              <div className="p-3 rounded-xl bg-rose-50 border border-rose-200 text-rose-700 text-xs flex items-center gap-2">
                <AlertCircle className="w-4 h-4 text-rose-600 flex-shrink-0" />
                <span>{error}</span>
              </div>
            )}

            <div className="grid grid-cols-1 sm:grid-cols-2 gap-4">
              {/* Site ID */}
              <div>
                <label className="block text-xs font-semibold text-slate-700 mb-1">
                  Site Identifier (slug) *
                </label>
                <input
                  type="text"
                  name="site_id"
                  required
                  placeholder="e.g. checkout-service"
                  value={formData.site_id}
                  onChange={handleChange}
                  className="w-full px-3 py-2 bg-slate-50 border border-slate-200 rounded-xl text-xs text-slate-900 placeholder:text-slate-400 focus:outline-none focus:border-indigo-500 focus:bg-white font-mono shadow-2xs"
                />
              </div>

              {/* Display Name */}
              <div>
                <label className="block text-xs font-semibold text-slate-700 mb-1">
                  Website Display Name *
                </label>
                <input
                  type="text"
                  name="name"
                  required
                  placeholder="e.g. Checkout & Billing Engine"
                  value={formData.name}
                  onChange={handleChange}
                  className="w-full px-3 py-2 bg-slate-50 border border-slate-200 rounded-xl text-xs text-slate-900 placeholder:text-slate-400 focus:outline-none focus:border-indigo-500 focus:bg-white shadow-2xs"
                />
              </div>
            </div>

            {/* Target URL */}
            <div>
              <label className="block text-xs font-semibold text-slate-700 mb-1">
                Monitored Website URL
              </label>
              <input
                type="url"
                name="target_url"
                placeholder="https://checkout.acmecorp.com"
                value={formData.target_url}
                onChange={handleChange}
                className="w-full px-3 py-2 bg-slate-50 border border-slate-200 rounded-xl text-xs text-slate-900 placeholder:text-slate-400 focus:outline-none focus:border-indigo-500 focus:bg-white font-mono shadow-2xs"
              />
            </div>

            {/* Thresholds */}
            <div className="grid grid-cols-2 gap-4">
              <div>
                <label className="block text-xs font-semibold text-orange-600 mb-1">
                  Warning Threshold (10-95)
                </label>
                <input
                  type="number"
                  name="warning_threshold"
                  min="10"
                  max="95"
                  step="5"
                  value={formData.warning_threshold}
                  onChange={handleChange}
                  className="w-full px-3 py-2 bg-slate-50 border border-slate-200 rounded-xl text-xs text-slate-900 focus:outline-none focus:border-orange-500 focus:bg-white font-mono shadow-2xs"
                />
              </div>

              <div>
                <label className="block text-xs font-semibold text-rose-600 mb-1">
                  Critical Threshold (20-100)
                </label>
                <input
                  type="number"
                  name="critical_threshold"
                  min="20"
                  max="100"
                  step="5"
                  value={formData.critical_threshold}
                  onChange={handleChange}
                  className="w-full px-3 py-2 bg-slate-50 border border-slate-200 rounded-xl text-xs text-slate-900 focus:outline-none focus:border-rose-500 focus:bg-white font-mono shadow-2xs"
                />
              </div>
            </div>

            {/* Dedicated Alert Webhook */}
            <div>
              <label className="block text-xs font-semibold text-slate-700 mb-1">
                Dedicated Webhook URL (Slack / Discord / PagerDuty)
              </label>
              <input
                type="url"
                name="alert_webhook_url"
                placeholder="https://hooks.slack.com/services/..."
                value={formData.alert_webhook_url}
                onChange={handleChange}
                className="w-full px-3 py-2 bg-slate-50 border border-slate-200 rounded-xl text-xs text-slate-900 placeholder:text-slate-400 focus:outline-none focus:border-indigo-500 focus:bg-white font-mono text-[11px] shadow-2xs"
              />
            </div>

            {/* Dedicated Alert Email */}
            <div>
              <label className="block text-xs font-semibold text-slate-700 mb-1">
                Dedicated On-Call Email
              </label>
              <input
                type="email"
                name="alert_email"
                placeholder="checkout-ops@acmecorp.com"
                value={formData.alert_email}
                onChange={handleChange}
                className="w-full px-3 py-2 bg-slate-50 border border-slate-200 rounded-xl text-xs text-slate-900 placeholder:text-slate-400 focus:outline-none focus:border-indigo-500 focus:bg-white font-mono text-[11px] shadow-2xs"
              />
            </div>

            {/* Actions */}
            <div className="pt-3 flex items-center justify-end gap-3 border-t border-slate-100">
              <button
                type="button"
                onClick={onClose}
                className="px-4 py-2 text-xs font-medium text-slate-600 hover:text-slate-900 transition-colors"
              >
                Cancel
              </button>
              <button
                type="submit"
                disabled={isSubmitting}
                className="px-5 py-2.5 rounded-xl bg-indigo-600 hover:bg-indigo-700 disabled:bg-indigo-300 text-white font-semibold text-xs shadow-md shadow-indigo-600/20 flex items-center gap-1.5 transition-all"
              >
                <Plus className="w-4 h-4" />
                <span>{isSubmitting ? 'Registering...' : 'Register Website'}</span>
              </button>
            </div>
          </form>
        )}
      </div>
    </div>
  );
}
