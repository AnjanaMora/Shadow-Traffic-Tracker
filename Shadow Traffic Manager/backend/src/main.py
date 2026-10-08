"""
Shadow Traffic — Core API Gateway, Telemetry Ingestion & Real-Time Alerting
Role in Architecture:
    Central API Gateway providing:
    - Secure metric ingestion with API key auth & rate limiting (POST /api/metrics)
    - Real-time live status and historical feeds (GET /api/status/{site_id})
    - Multi-site overview (GET /api/sites)
    - Custom site threshold tuning (POST /api/sites/{site_id}/thresholds)
    - Real-time telemetry WebSocket streaming (WS /ws/live/{site_id})
    - Container healthchecks (GET /health)
"""

import asyncio
import logging
import math
import random
import time
from contextlib import asynccontextmanager
from datetime import datetime, timezone, timedelta
from typing import Any, Dict, List, Optional
import httpx
from fastapi import (
    FastAPI,
    HTTPException,
    Query,
    WebSocket,
    WebSocketDisconnect,
    Depends,
    status,
)
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel, Field

from shadow_shared.models import (
    MetricEvent,
    TrafficPrediction,
    AlertEvent,
    SiteHealthStatus,
    CongestionLevel,
)
from .config import settings
from .logging_config import setup_logging
from .database import (
    init_db,
    check_db_health,
    clear_alerts_db,
    dal,
)
from .security.auth import verify_api_key, extract_api_key
from .security.rate_limiter import rate_limiter
from .alerting.engine import AlertingEngine
from .remediation.engine import AutoRemediationEngine
from .remediation.models import AutoRemediationAction
from .tenancy.manager import TenantManager
from .tenancy.models import (
    SiteRegistrationRequest,
    SiteRegistrationResponse,
    SiteUpdateRequest,
    RegisteredSiteRecord,
    TenantProfile,
)
from .events import DeploymentEvent, CorrelationResult
from .correlation import RootCauseCorrelator
from .websocket.manager import ws_manager
from .site_simulator import simulation_registry

# Configure structured logging
setup_logging(json_format=settings.LOG_FORMAT_JSON, log_level=settings.LOG_LEVEL)
logger = logging.getLogger("backend.gateway")

alerting_engine = AlertingEngine()
remediation_engine = AutoRemediationEngine()
tenant_manager = TenantManager()
root_cause_correlator = RootCauseCorrelator()
alerting_engine.correlator = root_cause_correlator

# In-memory tracking for fast active-site overview
active_sites: Dict[str, SiteHealthStatus] = {}
latest_assessments: Dict[str, Dict[str, Any]] = {}


@asynccontextmanager
async def lifespan(app: FastAPI):
    logger.info("Initializing Shadow Traffic Gateway...")
    db_ok = await init_db()
    if db_ok:
        logger.info("TimescaleDB connection ready.")
    else:
        logger.warning("TimescaleDB not available on startup; running in resilient fallback mode.")

    # Initialize in-process background simulation for all registered tenant sites
    for site in tenant_manager.list_sites():
        simulation_registry.start_simulation(
            site_id=site.site_id,
            ingest_fn=_ingest_simulated_metric,
            target_url=site.target_url,
        )

    yield
    logger.info("Shutting down Shadow Traffic Gateway...")
    simulation_registry.stop_all()
    await dal.close()


app = FastAPI(
    title="Shadow Traffic — API Gateway",
    description="High-Throughput Telemetry Ingestion, Dynamic Thresholds & Real-Time Alerting",
    version="0.2.0",
    lifespan=lifespan,
)

# Configure environment-aware CORS
_origins = [o.strip() for o in settings.CORS_ALLOWED_ORIGINS.split(",") if o.strip()]
if not _origins:
    _origins = ["*"]

app.add_middleware(
    CORSMiddleware,
    allow_origins=_origins,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


# DTO Models for Endpoints
class SiteThresholdsRequest(BaseModel):
    warning_threshold: float = Field(..., ge=10.0, le=95.0, description="Risk score threshold to trigger Warning (10-95)")
    critical_threshold: float = Field(..., ge=20.0, le=100.0, description="Risk score threshold to trigger Critical (20-100)")


class SiteStatusResponse(BaseModel):
    site_id: str
    timestamp: datetime
    current_risk_score: float
    status: str
    eta_minutes: Optional[float] = None
    primary_bottleneck: Optional[str] = None
    contributing_factors: List[Dict[str, Any]] = Field(default_factory=list)
    recent_metrics_30m: List[MetricEvent] = Field(default_factory=list)
    active_remediation: Optional[AutoRemediationAction] = None
    current_instances: int = 2


# ---------------------------------------------------------------------------
# Background Task: Async Risk Assessment & WebSocket Broadcast
# ---------------------------------------------------------------------------
async def _process_async_risk_and_alert(metric: MetricEvent):
    """
    Non-blocking pipeline execution:
    1. Fetches recent metrics from storage
    2. Calls Prediction Engine (/predict/{site_id})
    3. Evaluates debounced alerting with hysteresis
    4. Broadcasts live frame to WebSocket subscribers
    """
    site_id = metric.site_id
    try:
        # 1. Fetch recent window for trend analysis
        recent_events = await dal.get_recent(site_id=site_id, minutes=15)
        if not recent_events or recent_events[-1].timestamp != metric.timestamp:
            recent_events.append(metric)

        # 2. Call Prediction Engine
        assessment_data = None
        risk_score = 0.0
        status_str = "Normal"
        recommendation = None

        try:
            async with httpx.AsyncClient(timeout=3.0) as client:
                res = await client.post(
                    f"{settings.PREDICTION_ENGINE_URL}/predict/{site_id}",
                    json={"current_window": [e.model_dump(mode="json") for e in recent_events]},
                )
                if res.status_code == 200:
                    assessment_data = res.json()
                    risk_score = float(assessment_data.get("score", 0.0))
                    status_str = assessment_data.get("status", "Normal")
                    recommendation = assessment_data.get("recommendation")
                    latest_assessments[site_id] = assessment_data
                else:
                    raise RuntimeError(f"Prediction engine returned HTTP {res.status_code}")
        except Exception as pe_exc:
            logger.debug(f"Prediction engine call failed for '{site_id}': {pe_exc}")
            # Heuristic score calculation fallback if prediction engine is unreachable
            if metric.error_rate_percent >= 5.0 or metric.avg_response_time_ms >= 500.0:
                risk_score = 85.0
                status_str = "Critical"
            elif metric.error_rate_percent >= 2.0 or metric.avg_response_time_ms >= 250.0:
                risk_score = 65.0
                status_str = "Warning"
            else:
                risk_score = 15.0
                status_str = "Normal"

        # 3. Evaluate Hysteresis Alerting (requires 2 consecutive checks before firing)
        alert = await alerting_engine.evaluate_metric_and_risk(
            metric=metric,
            risk_score=risk_score,
            recommendation=recommendation,
        )

        # 4. Evaluate Auto-Remediation (triggers cloud auto-scale on Critical breach)
        warn_thresh, crit_thresh = alerting_engine.get_site_thresholds(site_id)
        remediation_action = await remediation_engine.evaluate_and_remediate(
            site_id=site_id,
            risk_score=risk_score,
            warning_threshold=warn_thresh,
            critical_threshold=crit_thresh,
            metric=metric,
        )

        # 5. Update In-Memory Site Overview
        observed_level = alerting_engine.classify_level_from_score(site_id, risk_score)
        active_sites[site_id] = SiteHealthStatus(
            site_id=site_id,
            last_seen=metric.timestamp,
            current_status=observed_level,
            active_users=metric.active_users,
            current_rps=metric.request_rate,
            current_latency_ms=metric.avg_response_time_ms,
            current_error_rate=metric.error_rate_percent,
        )

        # 6. Broadcast to WebSockets
        ws_payload = {
            "type": "telemetry_update",
            "site_id": site_id,
            "metric": metric.model_dump(mode="json"),
            "risk": {
                "score": risk_score,
                "status": status_str,
                "eta_minutes": assessment_data.get("eta_minutes") if assessment_data else None,
                "primary_bottleneck": assessment_data.get("primary_bottleneck") if assessment_data else None,
            },
            "alert_fired": bool(alert),
            "remediation": remediation_action.model_dump(mode="json") if remediation_action else None,
            "current_instances": remediation_engine.get_instances(site_id),
        }
        await ws_manager.broadcast_site_update(site_id, ws_payload)

    except Exception as exc:
        logger.error(f"Error in background risk evaluation for '{site_id}': {exc}", exc_info=True)


async def _ingest_simulated_metric(metric: MetricEvent):
    """
    Direct ingestion coroutine for simulated telemetry:
    1. Persists metric to TimescaleDB/DAL
    2. Updates synchronous active_sites tracker
    3. Runs async prediction engine assessment, hysteresis alerting, and WebSocket broadcast
    """
    try:
        if tenant_manager.is_site_deleted(metric.site_id):
            return
        await dal.insert_metric(metric)
        curr_level = active_sites[metric.site_id].current_status if metric.site_id in active_sites else CongestionLevel.LOW
        active_sites[metric.site_id] = SiteHealthStatus(
            site_id=metric.site_id,
            last_seen=metric.timestamp,
            current_status=curr_level,
            active_users=metric.active_users,
            current_rps=metric.request_rate,
            current_latency_ms=metric.avg_response_time_ms,
            current_error_rate=metric.error_rate_percent,
        )
        await _process_async_risk_and_alert(metric)
    except Exception as exc:
        logger.debug(f"Error ingesting simulated metric for '{metric.site_id}': {exc}")


# ---------------------------------------------------------------------------
# API Endpoints
# ---------------------------------------------------------------------------

@app.get("/health", tags=["Health"])
async def health_check():
    """Container healthcheck verifying database and downstream service connectivity."""
    db_healthy = await check_db_health()

    pe_healthy = False
    try:
        async with httpx.AsyncClient(timeout=2.0) as client:
            res = await client.get(f"{settings.PREDICTION_ENGINE_URL}/health")
            pe_healthy = res.status_code == 200
    except Exception:
        pe_healthy = False

    return {
        "status": "healthy" if db_healthy else "degraded",
        "service": settings.SERVICE_NAME,
        "environment": settings.ENVIRONMENT,
        "components": {
            "timescaledb": "connected" if db_healthy else "disconnected",
            "prediction_engine": "connected" if pe_healthy else "unreachable",
        },
    }


@app.post("/api/metrics", status_code=status.HTTP_201_CREATED, tags=["Metrics"])
@app.post("/api/v1/metrics", status_code=status.HTTP_201_CREATED, tags=["Metrics"])
async def ingest_metric(
    metric: MetricEvent,
    raw_api_key: Optional[str] = Depends(extract_api_key),
):
    """
    Ingest a telemetry snapshot:
    1. Authenticated via X-API-Key header (scoped per-site or master organization key).
    2. Rate-limited per site_id (HTTP 429 on flooding).
    3. Strictly validated against canonical MetricEvent schema.
    4. Persisted to TimescaleDB hypertable.
    5. Non-blocking async background task triggered for ML risk assessment and alert evaluation.
    """
    # 0. Reject deleted sites with 404
    if tenant_manager.is_site_deleted(metric.site_id):
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Site '{metric.site_id}' has been deleted.",
        )

    if settings.ENABLE_API_KEY_AUTH:
        if not raw_api_key:
            logger.warning("Rejected ingestion request: Missing X-API-Key header.")
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED,
                detail="Missing required authentication header: X-API-Key",
                headers={"WWW-Authenticate": "ApiKey"},
            )
        
        master_keys = set(settings.ALLOWED_API_KEYS)
        if settings.DEFAULT_API_KEY:
            master_keys.add(settings.DEFAULT_API_KEY)

        if not tenant_manager.validate_api_key_for_site(metric.site_id, raw_api_key, master_keys):
            logger.warning(
                f"Rejected ingestion request: Invalid API key for site '{metric.site_id}'"
            )
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED,
                detail="Invalid or unauthorized API key for site",
                headers={"WWW-Authenticate": "ApiKey"},
            )

    # 1. Rate limiting per site_id
    rate_limiter.check_rate_limit(metric.site_id)
    simulation_registry.note_external_ingest(metric.site_id)

    # 2. Write to TimescaleDB
    await dal.insert_metric(metric)

    # 3. Synchronously track active site telemetry
    curr_level = active_sites[metric.site_id].current_status if metric.site_id in active_sites else CongestionLevel.LOW
    active_sites[metric.site_id] = SiteHealthStatus(
        site_id=metric.site_id,
        last_seen=metric.timestamp,
        current_status=curr_level,
        active_users=metric.active_users,
        current_rps=metric.request_rate,
        current_latency_ms=metric.avg_response_time_ms,
        current_error_rate=metric.error_rate_percent,
    )

    # 4. Non-blocking risk evaluation and WebSocket dispatch
    asyncio.create_task(_process_async_risk_and_alert(metric))

    return {
        "status": "accepted",
        "site_id": metric.site_id,
        "timestamp": metric.timestamp.isoformat(),
    }


@app.get("/api/status/{site_id}", response_model=SiteStatusResponse, tags=["Monitoring"])
async def get_site_status(site_id: str):
    """
    Returns current risk score, status, ETA, contributing factors,
    and the last 30 minutes of raw metrics for dashboard graphing.
    """
    # Fetch recent metrics (last 30 minutes)
    recent_30m = await dal.get_recent(site_id=site_id, minutes=30)

    assessment = latest_assessments.get(site_id, {})
    curr_score = float(assessment.get("score", 0.0))
    status_str = assessment.get("status", "Normal")
    eta_mins = assessment.get("eta_minutes")
    bottleneck = assessment.get("primary_bottleneck")
    factors = assessment.get("contributing_factors", [])

    _, crit_thresh = alerting_engine.get_site_thresholds(site_id)
    active_rem = remediation_engine.get_active_remediation(
        site_id=site_id,
        current_risk=curr_score,
        critical_threshold=crit_thresh,
    )
    instances = remediation_engine.get_instances(site_id)

    return SiteStatusResponse(
        site_id=site_id,
        timestamp=datetime.now(timezone.utc),
        current_risk_score=curr_score,
        status=status_str,
        eta_minutes=eta_mins,
        primary_bottleneck=bottleneck,
        contributing_factors=factors,
        recent_metrics_30m=recent_30m,
        active_remediation=active_rem,
        current_instances=instances,
    )


@app.get("/api/account", response_model=TenantProfile, tags=["Tenancy"])
async def get_tenant_account():
    """Retrieve tenant organization profile, subscription tier, and registered site counts."""
    return tenant_manager.get_profile()


@app.post("/api/sites", response_model=SiteRegistrationResponse, status_code=status.HTTP_201_CREATED, tags=["Tenancy"])
async def register_tenant_site(req: SiteRegistrationRequest):
    """
    Register a new independent website under the tenant account.
    Generates a unique per-site ingestion API key and returns the ready-to-run collector command.
    """
    try:
        res = tenant_manager.register_site(req)
        # Configure site-specific thresholds and alert webhook in alerting engine
        alerting_engine.set_site_thresholds(
            site_id=res.site_id,
            warning_score=res.warning_threshold,
            critical_score=res.critical_threshold,
        )
        if res.alert_webhook_url or res.alert_email:
            alerting_engine.set_site_alert_channels(
                site_id=res.site_id,
                webhook_url=res.alert_webhook_url,
                email=res.alert_email,
            )

        # Automatically spawn in-process background simulation task for this registered site
        simulation_registry.start_simulation(
            site_id=res.site_id,
            ingest_fn=_ingest_simulated_metric,
            target_url=res.target_url,
        )

        return res
    except ValueError as val_err:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(val_err))


@app.put("/api/sites/{site_id}", response_model=RegisteredSiteRecord, tags=["Tenancy"])
async def update_tenant_site(site_id: str, req: SiteUpdateRequest):
    """Update settings, thresholds, or alert webhooks for an existing tenant site."""
    try:
        updated = tenant_manager.update_site(site_id, req)
        if req.warning_threshold is not None or req.critical_threshold is not None:
            alerting_engine.set_site_thresholds(
                site_id=site_id,
                warning_score=updated.warning_threshold,
                critical_score=updated.critical_threshold,
            )
        if req.alert_webhook_url is not None or req.alert_email is not None:
            alerting_engine.set_site_alert_channels(
                site_id=site_id,
                webhook_url=updated.alert_webhook_url,
                email=updated.alert_email,
            )
        return updated
    except KeyError as key_err:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(key_err))


@app.delete("/api/sites/{site_id}", status_code=status.HTTP_200_OK, tags=["Tenancy"])
async def delete_tenant_site(
    site_id: str,
    purge: bool = Query(default=False, description="Purge historical metrics from database")
):
    """Deregister and remove a monitored site from the tenant organization."""
    success = tenant_manager.delete_site(site_id)
    if not success:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=f"Site '{site_id}' not found.")
    
    # 1. Cleanly cancel and remove background collection task for this site
    simulation_registry.stop_simulation(site_id)

    # 2. Remove entries from remediation_engine (site_instances, active_remediations, last_action_time)
    remediation_engine.remove_site(site_id)

    # 3. Remove entries from alerting_engine (site_states, custom_thresholds, site_webhooks, site_emails, and site alert history)
    alerting_engine.remove_site(site_id)

    # 4. Remove active_sites and latest_assessments
    active_sites.pop(site_id, None)
    latest_assessments.pop(site_id, None)

    # 5. Close its websocket connections
    await ws_manager.close_site_connections(site_id)

    # 6. Purge historical metrics from database if purge=true
    if purge:
        await dal.delete_metrics(site_id)

    return {"status": "deleted", "site_id": site_id, "purged": purge}


@app.get("/api/sites", tags=["Monitoring"])
async def list_monitored_sites():
    """
    List all monitored sites for multi-site dashboard.
    Merges registered tenant sites with active live telemetry state for full visibility.
    """
    results: List[Dict[str, Any]] = []
    registered = {s.site_id: s for s in tenant_manager.list_sites()}

    # First include all registered tenant sites
    for site_id, reg in registered.items():
        live_health = active_sites.get(site_id)
        assessment = latest_assessments.get(site_id, {})
        
        last_seen = live_health.last_seen if live_health else reg.created_at
        current_status = live_health.current_status if live_health else CongestionLevel.LOW
        current_rps = live_health.current_rps if live_health else 0.0
        current_latency = live_health.current_latency_ms if live_health else 0.0
        current_errors = live_health.current_error_rate if live_health else 0.0
        active_users = live_health.active_users if live_health else 0

        results.append({
            "site_id": site_id,
            "name": reg.name,
            "target_url": reg.target_url,
            "api_key": reg.api_key,
            "warning_threshold": reg.warning_threshold,
            "critical_threshold": reg.critical_threshold,
            "alert_webhook_url": reg.alert_webhook_url,
            "last_seen": last_seen.isoformat(),
            "current_status": current_status.value if hasattr(current_status, "value") else str(current_status),
            "risk_score": float(assessment.get("score", 0.0)),
            "active_users": active_users,
            "current_rps": current_rps,
            "current_latency_ms": current_latency,
            "current_error_rate": current_errors,
        })

    # Also include any active ephemeral sites that sent metrics but were not pre-registered
    for site_id, live_health in active_sites.items():
        if site_id not in registered:
            assessment = latest_assessments.get(site_id, {})
            results.append({
                "site_id": site_id,
                "name": site_id,
                "target_url": None,
                "api_key": None,
                "warning_threshold": 60.0,
                "critical_threshold": 80.0,
                "alert_webhook_url": None,
                "last_seen": live_health.last_seen.isoformat(),
                "current_status": live_health.current_status.value if hasattr(live_health.current_status, "value") else str(live_health.current_status),
                "risk_score": float(assessment.get("score", 0.0)),
                "active_users": live_health.active_users,
                "current_rps": live_health.current_rps,
                "current_latency_ms": live_health.current_latency_ms,
                "current_error_rate": live_health.current_error_rate,
            })

    return results


@app.get("/api/remediations", response_model=List[AutoRemediationAction], tags=["Remediation"])
async def get_remediations(limit: int = 50):
    """Retrieve history of automated infrastructure scaling / auto-remediation actions."""
    return remediation_engine.get_history(limit=limit)


@app.post("/api/remediations/simulate/{site_id}", response_model=AutoRemediationAction, tags=["Remediation"])
async def trigger_manual_remediation(site_id: str):
    """
    Manually triggers a mock cloud auto-scale remediation event for live demo
    and future-scope demonstration ("Moving from prediction to action").
    """
    prev = remediation_engine.get_instances(site_id)
    new = min(remediation_engine.max_instances, prev + remediation_engine.scale_step)
    remediation_engine.site_instances[site_id] = new

    action = AutoRemediationAction(
        id=f"rem-demo-{int(datetime.now(timezone.utc).timestamp())}",
        site_id=site_id,
        timestamp=datetime.now(timezone.utc),
        trigger_score=88.5,
        action_type="SCALE_OUT",
        previous_instances=prev,
        new_instances=new,
        provider="AWS Auto Scaling / Kubernetes HPA (Simulated)",
        status="COMPLETED",
        message=f"Auto-remediation triggered: scaled from {prev} to {new} instances.",
        webhook_status_code=200,
        execution_latency_ms=115.0,
    )
    remediation_engine.active_remediations[site_id] = action
    remediation_engine.remediation_history.appendleft(action)

    # Broadcast live over WebSockets
    ws_payload = {
        "type": "telemetry_update",
        "site_id": site_id,
        "remediation": action.model_dump(mode="json"),
        "current_instances": new,
    }
    await ws_manager.broadcast_site_update(site_id, ws_payload)
    return action


@app.post("/api/remediate/{site_id}", tags=["Remediation"])
async def trigger_remediation_alias(site_id: str):
    """Endpoint for instant auto-scaling remediation demo invoked by dashboard."""
    action = await trigger_manual_remediation(site_id)
    return {
        "status": "success",
        "action": action.model_dump(mode="json"),
        "current_instances": action.new_instances,
    }


@app.post("/api/sites/{site_id}/thresholds", tags=["Configuration"])
async def set_site_thresholds(site_id: str, req: SiteThresholdsRequest):
    """
    Customize risk score thresholds for Warning and Critical alerts for a specific site.
    """
    if req.warning_threshold >= req.critical_threshold:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="warning_threshold must be strictly less than critical_threshold",
        )

    alerting_engine.set_site_thresholds(
        site_id=site_id,
        warning_score=req.warning_threshold,
        critical_score=req.critical_threshold,
    )

    return {
        "site_id": site_id,
        "warning_threshold": req.warning_threshold,
        "critical_threshold": req.critical_threshold,
        "status": "updated",
    }


@app.get("/api/alerts", response_model=List[AlertEvent], tags=["Alerts"])
async def get_alert_history(
    site_id: Optional[str] = Query(default=None, description="Optional site identifier filter"),
    limit: int = Query(default=50, ge=1, le=100),
):
    """Retrieve logged alerts history for demo and review (supports optional site_id filtering)."""
    return alerting_engine.get_alert_history(site_id=site_id, limit=limit)


@app.delete("/api/alerts", tags=["Alerts"])
@app.post("/api/alerts/clear", tags=["Alerts"])
async def clear_alert_history(
    site_id: Optional[str] = Query(default=None, description="Optional site identifier to clear only that site's alerts"),
    alert_id: Optional[str] = Query(default=None, description="Optional specific alert identifier to dismiss"),
):
    """Clear past alert events globally, for a specific site, or for a single alert ID."""
    cleared_count = alerting_engine.clear_alerts(site_id=site_id, alert_id=alert_id)
    await clear_alerts_db(site_id=site_id, alert_id=alert_id)

    # Broadcast real-time alerts_cleared event over WebSocket so all connected clients update immediately
    ws_payload = {
        "type": "alerts_cleared",
        "site_id": site_id,
        "alert_id": alert_id,
        "cleared_count": cleared_count,
    }
    if site_id:
        await ws_manager.broadcast_site_update(site_id, ws_payload)
    else:
        for s_id in list(ws_manager.active_connections.keys()):
            await ws_manager.broadcast_site_update(s_id, ws_payload)

    return {
        "status": "cleared",
        "cleared_count": cleared_count,
        "site_id": site_id,
        "alert_id": alert_id,
    }


@app.post("/api/deployments", response_model=DeploymentEvent, status_code=status.HTTP_201_CREATED, tags=["Deployments"])
async def record_deployment_event(event: DeploymentEvent):
    """
    Log a software release or deployment event. Used for automated
    root-cause correlation when incident alerts occur.
    """
    return root_cause_correlator.record_deployment(event)


@app.get("/api/deployments", response_model=List[DeploymentEvent], tags=["Deployments"])
async def list_deployment_events(
    site_id: Optional[str] = Query(default=None, description="Optional site filter"),
    limit: int = Query(default=50, ge=1, le=100),
):
    """List recorded software deployments and configuration rollouts."""
    return root_cause_correlator.get_deployments(site_id=site_id, limit=limit)


@app.get("/api/correlate/{site_id}", response_model=CorrelationResult, tags=["Correlation"])
async def correlate_site_root_cause(site_id: str):
    """
    Inspect if the site's current operational state or recent alert
    correlates with a recent deployment event.
    """
    now = datetime.now(timezone.utc)
    return root_cause_correlator.correlate_alert(site_id=site_id, alert_timestamp=now)


# ---------------------------------------------------------------------------
# WebSocket Endpoint: Live Dashboard Streaming
# ---------------------------------------------------------------------------
@app.websocket("/ws/live/{site_id}")
async def websocket_live_feed(websocket: WebSocket, site_id: str):
    """
    Pushes live metric and risk updates to connected dashboard clients
    without polling.
    """
    await ws_manager.connect(site_id, websocket)
    try:
        # Initial greeting with current status
        recent = await dal.get_recent(site_id=site_id, minutes=5)
        await websocket.send_json({
            "type": "connection_ack",
            "site_id": site_id,
            "connected_at": datetime.now(timezone.utc).isoformat(),
            "recent_count": len(recent),
        })

        # Keep alive loop
        while True:
            # Await client pings or messages
            data = await websocket.receive_text()
            if data == "ping":
                await websocket.send_text("pong")
    except WebSocketDisconnect:
        ws_manager.disconnect(site_id, websocket)
    except Exception as exc:
        logger.debug(f"WebSocket exception on '{site_id}': {exc}")
        ws_manager.disconnect(site_id, websocket)
