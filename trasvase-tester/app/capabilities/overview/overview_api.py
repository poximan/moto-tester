from __future__ import annotations

from typing import Any, Callable

from fastapi import APIRouter, Depends, HTTPException, WebSocket, WebSocketDisconnect

from ...control.snapshot_hub import SnapshotHub
from ...models import PollingControlBody
from .overview_service import OverviewService


class OverviewApi:
    def __init__(
        self,
        service: OverviewService,
        snapshot_hub: SnapshotHub,
        require_operator: Callable[..., None],
    ):
        self.service = service
        self.snapshot_hub = snapshot_hub
        self.router = APIRouter()
        self.router.add_api_route("/api/health", self.health, methods=["GET"])
        self.router.add_api_route("/api/snapshot", self.snapshot, methods=["GET"])
        self.router.add_api_route("/api/config", self.config, methods=["GET"])
        self.router.add_api_route(
            "/api/modbus-polling",
            self.polling,
            methods=["GET"],
        )
        self.router.add_api_route(
            "/api/modbus-polling/{function_code}",
            self.set_polling,
            methods=["PUT"],
            dependencies=[Depends(require_operator)],
        )
        self.router.add_api_websocket_route("/ws/stream", self.stream)

    def health(self) -> dict[str, Any]:
        return self.service.health()

    def snapshot(self) -> dict[str, Any]:
        return self.service.snapshot()

    def config(self) -> dict[str, Any]:
        return self.service.config_contract()

    def polling(self) -> dict[str, Any]:
        return self.service.polling()

    def set_polling(
        self,
        function_code: str,
        body: PollingControlBody,
    ) -> dict[str, Any]:
        try:
            snapshot = self.service.set_polling(
                function_code,
                enabled=body.enabled,
                sample_rate_ms=body.sample_rate_ms,
                source=body.source,
            )
        except ValueError as exc:
            raise HTTPException(status_code=400, detail=str(exc)) from exc
        return {"ok": True, **snapshot}

    async def stream(self, websocket: WebSocket) -> None:
        await websocket.accept()
        revision = -1
        try:
            while True:
                revision, snapshot = await self.snapshot_hub.wait_next(revision)
                await websocket.send_json(snapshot)
        except WebSocketDisconnect:
            return
