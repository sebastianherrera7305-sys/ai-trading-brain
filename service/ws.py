"""WebSocket fan-out: every connected dashboard client gets the same
snapshot on connect, then the same incremental pushes as everything else
changes. See dashboard/app.js for the client-side contract this mirrors."""

import json
import logging
from typing import Any, Dict, List

from fastapi import WebSocket

logger = logging.getLogger("service.ws")


class ConnectionManager:
    def __init__(self):
        self.active: List[WebSocket] = []

    async def connect(self, ws: WebSocket) -> None:
        await ws.accept()
        self.active.append(ws)

    def disconnect(self, ws: WebSocket) -> None:
        if ws in self.active:
            self.active.remove(ws)

    async def send_snapshot(self, ws: WebSocket, snapshot: Dict[str, Any]) -> None:
        await ws.send_text(json.dumps({"type": "snapshot", "data": snapshot}))

    async def broadcast(self, kind: str, data: Dict[str, Any]) -> None:
        if not self.active:
            return
        message = json.dumps({"type": kind, "data": data})
        dead = []
        for ws in self.active:
            try:
                await ws.send_text(message)
            except Exception:
                logger.info("dropping dead websocket client")
                dead.append(ws)
        for ws in dead:
            self.disconnect(ws)
