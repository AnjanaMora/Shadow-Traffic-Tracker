"""
Shadow Traffic — WebSocket Real-Time Connection Manager
Role in Architecture:
    Manages active dashboard WebSocket connections subscribed to /ws/live/{site_id}.
    Broadcasts live MetricEvent snapshots and RiskAssessment updates in real time,
    eliminating client polling overhead.
"""

import logging
from collections import defaultdict
from typing import Dict, List
from fastapi import WebSocket

logger = logging.getLogger("backend.websocket")


class ConnectionManager:
    """Manages active WebSockets and broadcasts live telemetry updates."""

    def __init__(self):
        # site_id -> list of active WebSockets
        self.active_connections: Dict[str, List[WebSocket]] = defaultdict(list)

    async def connect(self, site_id: str, websocket: WebSocket) -> None:
        await websocket.accept()
        self.active_connections[site_id].append(websocket)
        logger.info(f"WebSocket client connected to live feed for site '{site_id}'")

    def disconnect(self, site_id: str, websocket: WebSocket) -> None:
        if websocket in self.active_connections[site_id]:
            self.active_connections[site_id].remove(websocket)
            logger.info(f"WebSocket client disconnected from site '{site_id}'")

    async def broadcast_site_update(self, site_id: str, message: dict) -> None:
        """Broadcast JSON message to all clients connected to site_id feed."""
        subscribers = list(self.active_connections[site_id])
        for ws in subscribers:
            try:
                await ws.send_json(message)
            except Exception as exc:
                logger.debug(f"Failed to send to WebSocket client: {exc}")
                self.disconnect(site_id, ws)

    async def close_site_connections(self, site_id: str) -> None:
        """Closes all active WebSockets connected to site_id and removes them."""
        connections = self.active_connections.pop(site_id, [])
        for ws in connections:
            try:
                await ws.close(code=1000, reason="Site deleted")
            except Exception as exc:
                logger.debug(f"Error closing WebSocket for deleted site '{site_id}': {exc}")
        if connections:
            logger.info(f"Closed {len(connections)} WebSocket connection(s) for site '{site_id}'")


ws_manager = ConnectionManager()
