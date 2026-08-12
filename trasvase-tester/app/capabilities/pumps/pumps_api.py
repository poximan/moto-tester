from __future__ import annotations

from typing import Any, Callable

from fastapi import APIRouter, Depends, HTTPException

from ...adapters.emulator_client import EmulatorClientError
from ...models import CommandBody, EmulatorPumpEmarBody, PumpCommandBody
from .pumps_service import PumpsService


class PumpsApi:
    def __init__(
        self,
        service: PumpsService,
        require_operator: Callable[..., None],
    ):
        self.service = service
        self.router = APIRouter(dependencies=[Depends(require_operator)])
        self.router.add_api_route("/api/command", self.command, methods=["POST"])
        self.router.add_api_route(
            "/api/pumps/{pump_id}/command",
            self.pump_command,
            methods=["POST"],
        )
        self.router.add_api_route(
            "/api/emulator/pumps/{pump_id}/generate-emar",
            self.set_generate_emar,
            methods=["PUT"],
        )

    def command(self, body: CommandBody) -> dict[str, Any]:
        return self._state_request(
            lambda: self.service.command(body.tag, body.value, body.source)
        )

    def pump_command(self, pump_id: int, body: PumpCommandBody) -> dict[str, Any]:
        return self._state_request(
            lambda: self.service.pump_command(
                pump_id,
                aut=body.aut,
                mr=body.mr,
                source=body.source,
            )
        )

    def set_generate_emar(
        self,
        pump_id: int,
        body: EmulatorPumpEmarBody,
    ) -> dict[str, Any]:
        try:
            return self.service.set_generate_emar(pump_id, body.enabled)
        except EmulatorClientError as exc:
            raise HTTPException(status_code=exc.status_code, detail=exc.detail) from exc

    @staticmethod
    def _state_request(operation: Callable[[], dict[str, Any]]) -> dict[str, Any]:
        try:
            return operation()
        except KeyError as exc:
            raise HTTPException(status_code=404, detail=exc.args[0]) from exc
        except PermissionError as exc:
            raise HTTPException(status_code=403, detail=str(exc)) from exc
        except (BufferError, ValueError) as exc:
            status = 400 if str(exc).startswith("Este endpoint") else 409
            raise HTTPException(status_code=status, detail=str(exc)) from exc
