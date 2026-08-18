from __future__ import annotations

from typing import Any, Callable

from fastapi import APIRouter, Depends, HTTPException

from ...adapters.emulator_client import EmulatorClientError
from ...models import EmulatorValveBody
from .process_service import ProcessService


class ProcessApi:
    def __init__(
        self,
        service: ProcessService,
        require_edge: Callable[..., None],
    ):
        self.service = service
        self.router = APIRouter()
        self.router.add_api_route(
            "/api/emulator/state",
            self.state,
            methods=["GET"],
        )
        self.router.add_api_route(
            "/api/emulator/valves",
            self.set_valves,
            methods=["PUT"],
            dependencies=[Depends(require_edge)],
        )

    def state(self) -> dict[str, Any]:
        return self._request(self.service.state)

    def set_valves(self, body: EmulatorValveBody) -> dict[str, Any]:
        return self._request(lambda: self.service.set_valves(body.model_dump()))

    @staticmethod
    def _request(operation: Callable[[], dict[str, Any]]) -> dict[str, Any]:
        try:
            return operation()
        except EmulatorClientError as exc:
            raise HTTPException(status_code=exc.status_code, detail=exc.detail) from exc
