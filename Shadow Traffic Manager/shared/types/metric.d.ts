/**
 * Canonical Metric Event TypeScript Definitions
 * Mirror of shared/schema/metric_event.json and shadow_shared.models.MetricEvent
 */

export interface MetricEvent {
  site_id: string;
  timestamp: string; // ISO 8601 UTC
  active_users: number;
  request_rate: number;
  avg_response_time_ms: number;
  error_rate_percent: number;
}

export type CongestionLevel = 'LOW' | 'MEDIUM' | 'HIGH' | 'CRITICAL';

export interface TrafficPrediction {
  site_id: string;
  predicted_at: string;
  horizon_seconds: number;
  predicted_request_rate: number;
  predicted_response_time_ms: number;
  congestion_risk_score: number; // 0.0 - 1.0
  congestion_level: CongestionLevel;
  recommendation: string;
}

export interface AlertEvent {
  alert_id: string;
  site_id: string;
  timestamp: string;
  level: CongestionLevel;
  title: string;
  message: string;
  metric_snapshot: MetricEvent;
  prediction?: TrafficPrediction;
}

export interface SiteHealthStatus {
  site_id: string;
  last_seen: string;
  current_status: CongestionLevel;
  active_users: number;
  current_rps: number;
  current_latency_ms: number;
  current_error_rate: number;
}
