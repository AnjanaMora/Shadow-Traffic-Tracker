import React, { useState } from 'react';
import { Sliders, X, Check, AlertCircle } from 'lucide-react';

export default function ThresholdModal({
  siteId,
  isOpen = false,
  onClose,
  currentThresholds = null,
  onSave,
}) {
  if (!isOpen) return null;

  const defaultWarn = currentThresholds?.warning ?? 60.0;
  const defaultCrit = currentThresholds?.critical ?? 80.0;

  const [warningVal, setWarningVal] = useState(defaultWarn);
  const [criticalVal, setCriticalVal] = useState(defaultCrit);
  const [isSubmitting, setIsSubmitting] = useState(false);
  const [error, setError] = useState(null);
  const [success, setSuccess] = useState(false);

  const handleSubmit = async (e) => {
    e.preventDefault();
    if (warningVal >= criticalVal) {
      setError('Warning threshold must be strictly lower than Critical threshold.');
      return;
    }

    try {
      setIsSubmitting(true);
      setError(null);
      await onSave(siteId, {
        warning_threshold: Number(warningVal),
        critical_threshold: Number(criticalVal),
      });
      setSuccess(true);
      setTimeout(() => {
        setSuccess(false);
        onClose();
      }, 1000);
    } catch (err) {
      setError(err.message || 'Failed to update thresholds');
    } finally {
      setIsSubmitting(false);
    }
  };

  return (
    <div className="fixed inset-0 z-50 flex items-center justify-center p-4 bg-slate-900/40 backdrop-blur-sm animate-fadeIn">
      <div className="bg-white/95 border border-slate-200 rounded-2xl max-w-md w-full p-6 shadow-2xl space-y-5 text-slate-800">
        <div className="flex items-center justify-between border-b border-slate-100 pb-3">
          <div className="flex items-center gap-2">
            <Sliders className="w-5 h-5 text-indigo-600" />
            <h3 className="text-base font-bold text-slate-900">
              Customize Alert Thresholds
            </h3>
          </div>
          <button
            onClick={onClose}
            className="p-1.5 rounded-lg text-slate-400 hover:text-slate-700 hover:bg-slate-100 transition-colors"
          >
            <X className="w-4 h-4" />
          </button>
        </div>

        <p className="text-xs text-slate-500">
          Set custom sensitivity for <strong className="text-slate-800">{siteId}</strong>.
          Adjusting thresholds dictates at what congestion risk score an incident notification fires.
        </p>

        {error && (
          <div className="flex items-center gap-2 p-3 rounded-xl bg-rose-50 border border-rose-200 text-rose-700 text-xs">
            <AlertCircle className="w-4 h-4 flex-shrink-0" />
            <span>{error}</span>
          </div>
        )}

        {success && (
          <div className="flex items-center gap-2 p-3 rounded-xl bg-emerald-50 border border-emerald-200 text-emerald-700 text-xs">
            <Check className="w-4 h-4 flex-shrink-0" />
            <span>Thresholds successfully updated!</span>
          </div>
        )}

        <form onSubmit={handleSubmit} className="space-y-4">
          {/* Warning Slider */}
          <div className="space-y-1.5">
            <div className="flex justify-between text-xs">
              <span className="font-semibold text-orange-600">Warning Trigger Score</span>
              <span className="font-mono font-bold text-slate-900">{warningVal} / 100</span>
            </div>
            <input
              type="range"
              min="20"
              max="85"
              value={warningVal}
              onChange={(e) => setWarningVal(Number(e.target.value))}
              className="w-full h-2 bg-slate-200 rounded-lg appearance-none cursor-pointer accent-orange-500"
            />
            <span className="text-[10px] text-slate-400">
              Default: 60. Lower values notify earlier on minor deviations.
            </span>
          </div>

          {/* Critical Slider */}
          <div className="space-y-1.5">
            <div className="flex justify-between text-xs">
              <span className="font-semibold text-rose-600">Critical Trigger Score</span>
              <span className="font-mono font-bold text-slate-900">{criticalVal} / 100</span>
            </div>
            <input
              type="range"
              min="30"
              max="95"
              value={criticalVal}
              onChange={(e) => setCriticalVal(Number(e.target.value))}
              className="w-full h-2 bg-slate-200 rounded-lg appearance-none cursor-pointer accent-rose-500"
            />
            <span className="text-[10px] text-slate-400">
              Default: 80. Triggers urgent paging and remediation alerts.
            </span>
          </div>

          <div className="pt-2 flex justify-end gap-2.5 border-t border-slate-100">
            <button
              type="button"
              onClick={onClose}
              className="px-4 py-2 rounded-xl bg-slate-100 hover:bg-slate-200 text-xs font-semibold text-slate-700 transition-colors"
            >
              Cancel
            </button>
            <button
              type="submit"
              disabled={isSubmitting}
              className="px-4 py-2 rounded-xl bg-indigo-600 hover:bg-indigo-700 disabled:opacity-50 text-xs font-semibold text-white transition-colors flex items-center gap-1.5 shadow-md shadow-indigo-600/20"
            >
              {isSubmitting ? 'Updating...' : 'Save Thresholds'}
            </button>
          </div>
        </form>
      </div>
    </div>
  );
}
