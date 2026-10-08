-- =============================================================================
-- Migration 001: TimescaleDB Schema, Continuous Aggregates & Retention Policies
-- =============================================================================

-- 1. Enable TimescaleDB Extension
CREATE EXTENSION IF NOT EXISTS timescaledb CASCADE;

-- 2. Create Canonical Metrics Table
-- Composite primary key (site_id, timestamp) prevents duplicate telemetry for the same instant
CREATE TABLE IF NOT EXISTS metrics (
    site_id VARCHAR(128) NOT NULL,
    timestamp TIMESTAMPTZ NOT NULL,
    active_users INTEGER NOT NULL CHECK (active_users >= 0),
    request_rate DOUBLE PRECISION NOT NULL CHECK (request_rate >= 0.0),
    avg_response_time_ms DOUBLE PRECISION NOT NULL CHECK (avg_response_time_ms >= 0.0),
    error_rate_percent DOUBLE PRECISION NOT NULL CHECK (error_rate_percent >= 0.0 AND error_rate_percent <= 100.0),
    PRIMARY KEY (site_id, timestamp)
);

-- 3. Convert to TimescaleDB Hypertable
-- 1-day chunk intervals optimize memory locality for active high-frequency writes
DO $$
BEGIN
    IF EXISTS (SELECT 1 FROM pg_extension WHERE extname = 'timescaledb') THEN
        PERFORM create_hypertable(
            'metrics',
            'timestamp',
            chunk_time_interval => INTERVAL '1 day',
            if_not_exists => TRUE
        );
    END IF;
END $$;

-- 4. Compound Index on (site_id, timestamp DESC)
-- Essential for rapid site-scoped time-series queries without full hypertable scans
CREATE INDEX IF NOT EXISTS idx_metrics_site_timestamp ON metrics (site_id, timestamp DESC);

-- 5. Continuous Aggregate: 1-Minute Rollup
-- Pre-computes sample count, averages, maximums, and 95th percentiles
DO $$
BEGIN
    IF EXISTS (SELECT 1 FROM pg_extension WHERE extname = 'timescaledb') THEN
        CREATE MATERIALIZED VIEW IF NOT EXISTS metrics_1m_rollup
        WITH (timescaledb.continuous) AS
        SELECT
            time_bucket('1 minute', timestamp) AS bucket,
            site_id,
            COUNT(*) AS sample_count,
            AVG(active_users)::INTEGER AS avg_active_users,
            MAX(active_users) AS max_active_users,
            ROUND(AVG(request_rate)::NUMERIC, 2)::DOUBLE PRECISION AS avg_request_rate,
            ROUND(MAX(request_rate)::NUMERIC, 2)::DOUBLE PRECISION AS max_request_rate,
            ROUND(percentile_cont(0.95) WITHIN GROUP (ORDER BY request_rate)::NUMERIC, 2)::DOUBLE PRECISION AS p95_request_rate,
            ROUND(AVG(avg_response_time_ms)::NUMERIC, 2)::DOUBLE PRECISION AS avg_response_time_ms,
            ROUND(MAX(avg_response_time_ms)::NUMERIC, 2)::DOUBLE PRECISION AS max_response_time_ms,
            ROUND(percentile_cont(0.95) WITHIN GROUP (ORDER BY avg_response_time_ms)::NUMERIC, 2)::DOUBLE PRECISION AS p95_response_time_ms,
            ROUND(AVG(error_rate_percent)::NUMERIC, 2)::DOUBLE PRECISION AS avg_error_rate_percent,
            ROUND(MAX(error_rate_percent)::NUMERIC, 2)::DOUBLE PRECISION AS max_error_rate_percent
        FROM metrics
        GROUP BY bucket, site_id
        WITH NO DATA;
    END IF;
END $$;

-- 6. Continuous Aggregate: 5-Minute Rollup
-- Long-range trend forecasting and baseline queries
DO $$
BEGIN
    IF EXISTS (SELECT 1 FROM pg_extension WHERE extname = 'timescaledb') THEN
        CREATE MATERIALIZED VIEW IF NOT EXISTS metrics_5m_rollup
        WITH (timescaledb.continuous) AS
        SELECT
            time_bucket('5 minutes', timestamp) AS bucket,
            site_id,
            COUNT(*) AS sample_count,
            AVG(active_users)::INTEGER AS avg_active_users,
            MAX(active_users) AS max_active_users,
            ROUND(AVG(request_rate)::NUMERIC, 2)::DOUBLE PRECISION AS avg_request_rate,
            ROUND(MAX(request_rate)::NUMERIC, 2)::DOUBLE PRECISION AS max_request_rate,
            ROUND(percentile_cont(0.95) WITHIN GROUP (ORDER BY request_rate)::NUMERIC, 2)::DOUBLE PRECISION AS p95_request_rate,
            ROUND(AVG(avg_response_time_ms)::NUMERIC, 2)::DOUBLE PRECISION AS avg_response_time_ms,
            ROUND(MAX(avg_response_time_ms)::NUMERIC, 2)::DOUBLE PRECISION AS max_response_time_ms,
            ROUND(percentile_cont(0.95) WITHIN GROUP (ORDER BY avg_response_time_ms)::NUMERIC, 2)::DOUBLE PRECISION AS p95_response_time_ms,
            ROUND(AVG(error_rate_percent)::NUMERIC, 2)::DOUBLE PRECISION AS avg_error_rate_percent,
            ROUND(MAX(error_rate_percent)::NUMERIC, 2)::DOUBLE PRECISION AS max_error_rate_percent
        FROM metrics
        GROUP BY bucket, site_id
        WITH NO DATA;
    END IF;
END $$;

-- 7. Continuous Aggregate Refresh Policies
DO $$
BEGIN
    IF EXISTS (SELECT 1 FROM pg_extension WHERE extname = 'timescaledb') THEN
        -- Refresh 1m rollup every minute for data between 2 hours ago and 1 minute ago
        PERFORM add_continuous_aggregate_policy(
            'metrics_1m_rollup',
            start_offset => INTERVAL '2 hours',
            end_offset => INTERVAL '1 minute',
            schedule_interval => INTERVAL '1 minute',
            if_not_exists => TRUE
        );

        -- Refresh 5m rollup every 5 minutes for data between 12 hours ago and 5 minutes ago
        PERFORM add_continuous_aggregate_policy(
            'metrics_5m_rollup',
            start_offset => INTERVAL '12 hours',
            end_offset => INTERVAL '5 minutes',
            schedule_interval => INTERVAL '5 minutes',
            if_not_exists => TRUE
        );
    END IF;
END $$;

-- 8. Retention Policy: Raw Data Dropped After 30 Days
-- Only the continuous aggregate rollups (1m and 5m) remain for long-term historical analysis
DO $$
BEGIN
    IF EXISTS (SELECT 1 FROM pg_extension WHERE extname = 'timescaledb') THEN
        PERFORM add_retention_policy(
            'metrics',
            INTERVAL '30 days',
            if_not_exists => TRUE
        );
    END IF;
END $$;

-- 9. Create Auxiliary Prediction & Alert Tables
CREATE TABLE IF NOT EXISTS predictions (
    id BIGSERIAL PRIMARY KEY,
    site_id VARCHAR(128) NOT NULL,
    predicted_at TIMESTAMPTZ NOT NULL,
    horizon_seconds INTEGER NOT NULL,
    predicted_request_rate DOUBLE PRECISION NOT NULL,
    predicted_response_time_ms DOUBLE PRECISION NOT NULL,
    congestion_risk_score DOUBLE PRECISION NOT NULL,
    congestion_level VARCHAR(32) NOT NULL,
    recommendation TEXT
);
CREATE INDEX IF NOT EXISTS idx_predictions_site_time ON predictions (site_id, predicted_at DESC);

CREATE TABLE IF NOT EXISTS alerts (
    alert_id VARCHAR(64) PRIMARY KEY,
    site_id VARCHAR(128) NOT NULL,
    timestamp TIMESTAMPTZ NOT NULL,
    level VARCHAR(32) NOT NULL,
    title VARCHAR(256) NOT NULL,
    message TEXT NOT NULL
);
CREATE INDEX IF NOT EXISTS idx_alerts_site_time ON alerts (site_id, timestamp DESC);
