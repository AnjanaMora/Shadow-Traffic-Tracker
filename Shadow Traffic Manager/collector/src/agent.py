"""
Shadow Traffic — Collector Agent Entry
Role in Architecture:
    Main runtime entry module for the Collector container. Provides the
    CollectorAgent wrapper and invokes the CLI runner with configured
    environment parameters, initiating either real telemetry gathering
    or synthetic traffic generation.
"""

import asyncio
from .client import ResilientMetricClient
from .config import settings
from .simulator import TrafficSimulator
from .cli import main


class CollectorAgent:
    """
    Convenience wrapper around TrafficSimulator and ResilientMetricClient.
    """

    def __init__(
        self,
        backend_url: str = settings.BACKEND_API_URL,
        site_id: str = settings.SITE_ID,
    ):
        self.backend_url = backend_url
        self.site_id = site_id
        self.simulator = TrafficSimulator(site_id=site_id)
        self.client = ResilientMetricClient(
            backend_url=backend_url,
            endpoint_path="/api/metrics",
        )

    async def send_metric(self, metric) -> bool:
        return await self.client.push(metric)

    async def run_loop(self, interval: float = settings.REPORT_INTERVAL_SECONDS):
        while True:
            metric = self.simulator.generate_next_metric(step_seconds=interval)
            await self.client.push(metric)
            await asyncio.sleep(interval)


if __name__ == "__main__":
    main()
