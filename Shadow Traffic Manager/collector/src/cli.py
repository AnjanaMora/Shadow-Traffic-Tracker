"""
Shadow Traffic — Collector CLI Entry Point
Role in Architecture:
    Unified command-line interface for the Collector service. Parses CLI flags
    for Real Collector Mode (tail-log, scrape-prometheus) and Simulation Mode
    (seasonal parameters, simulation speed, congestion timing, site_id).
"""

import argparse
import asyncio
import logging
import sys

from .client import ResilientMetricClient
from shadow_shared.logging import setup_structured_logging
from .config import settings
from .real_collector import AccessLogTailer, PrometheusScraper
from .simulator import TrafficSimulator

setup_structured_logging(
    service_name="shadow-collector",
    log_level=settings.LOG_LEVEL,
    json_format=True,
)
logger = logging.getLogger("collector.cli")


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="Shadow Traffic Collector — Real Telemetry & Simulation Agent"
    )

    parser.add_argument(
        "--mode",
        choices=["simulate", "tail-log", "scrape-prometheus"],
        default=settings.COLLECTOR_MODE,
        help="Operational mode (default: simulate)",
    )
    parser.add_argument(
        "--site-id",
        type=str,
        default=settings.SITE_ID,
        help="Monitored site identifier",
    )
    parser.add_argument(
        "--backend-url",
        type=str,
        default=settings.BACKEND_API_URL,
        help="Ingestion API base URL (default: http://localhost:8000)",
    )
    parser.add_argument(
        "--endpoint",
        type=str,
        default="/api/metrics",
        help="Target metric ingestion endpoint path (default: /api/metrics)",
    )
    parser.add_argument(
        "--interval",
        type=float,
        default=settings.REPORT_INTERVAL_SECONDS,
        help="Reporting interval in seconds (default: 3.0)",
    )

    # Simulation Mode Options
    sim_group = parser.add_argument_group("Simulation Mode Options")
    sim_group.add_argument(
        "--speed",
        type=float,
        default=settings.SIM_SPEED_MULTIPLIER,
        help="Simulation virtual time speed multiplier (e.g. 1.0 = real-time, 10.0 = 10x)",
    )
    sim_group.add_argument(
        "--base-users",
        type=int,
        default=settings.SIM_BASE_USERS,
        help="Base concurrent user baseline (default: 1200)",
    )
    sim_group.add_argument(
        "--noise-percent",
        type=float,
        default=settings.SIM_NOISE_PERCENT,
        help="Random Gaussian noise percentage around baseline (default: 10.0)",
    )
    sim_group.add_argument(
        "--congestion-delay-seconds",
        type=float,
        default=settings.SIM_CONGESTION_DELAY_SECONDS,
        help="Simulation seconds before injecting a congestion event (default: 60.0)",
    )
    sim_group.add_argument(
        "--congestion-duration-seconds",
        type=float,
        default=settings.SIM_CONGESTION_DURATION_SECONDS,
        help="Duration of the congestion ramp event in simulation seconds (default: 300.0)",
    )
    sim_group.add_argument(
        "--congestion-severity",
        type=float,
        default=settings.SIM_CONGESTION_SEVERITY,
        help="Peak traffic multiplier during congestion (default: 3.5)",
    )

    # Real Mode Options
    real_group = parser.add_argument_group("Real Collector Mode Options")
    real_group.add_argument(
        "--log-file",
        type=str,
        default=settings.LOG_FILE_PATH,
        help="Path to Nginx/Apache access log file to tail",
    )
    real_group.add_argument(
        "--scrape-url",
        type=str,
        default=settings.PROMETHEUS_METRICS_URL,
        help="Prometheus /metrics scrape URL",
    )

    return parser


async def run_simulation(args: argparse.Namespace, client: ResilientMetricClient):
    """Run the traffic simulation loop."""
    simulator = TrafficSimulator(
        site_id=args.site_id,
        base_users=args.base_users,
        noise_percent=args.noise_percent,
        speed_multiplier=args.speed,
        congestion_delay_seconds=args.congestion_delay_seconds,
        congestion_duration_seconds=args.congestion_duration_seconds,
        congestion_severity=args.congestion_severity,
    )

    logger.info(
        f"Starting Simulation Mode for site '{args.site_id}' at {args.speed}x speed. "
        f"Congestion injection scheduled in {args.congestion_delay_seconds}s (duration: {args.congestion_duration_seconds}s)."
    )

    while True:
        metric = simulator.generate_next_metric(step_seconds=args.interval)
        await client.push(metric)
        await asyncio.sleep(args.interval)


async def async_main(args: argparse.Namespace):
    client = ResilientMetricClient(
        backend_url=args.backend_url,
        endpoint_path=args.endpoint,
        max_buffer_size=settings.MAX_BUFFER_SIZE,
    )

    if args.mode == "simulate":
        await run_simulation(args, client)
    elif args.mode == "tail-log":
        tailer = AccessLogTailer(
            log_file_path=args.log_file,
            site_id=args.site_id,
            client=client,
            interval_seconds=args.interval,
        )
        await tailer.run()
    elif args.mode == "scrape-prometheus":
        scraper = PrometheusScraper(
            metrics_url=args.scrape_url,
            site_id=args.site_id,
            client=client,
            interval_seconds=args.interval,
        )
        await scraper.run()
    else:
        logger.error(f"Unknown mode: {args.mode}")
        sys.exit(1)


def main():
    parser = build_parser()
    args = parser.parse_args()
    try:
        asyncio.run(async_main(args))
    except KeyboardInterrupt:
        logger.info("Collector agent shut down gracefully.")


if __name__ == "__main__":
    main()
