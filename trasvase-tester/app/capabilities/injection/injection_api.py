from __future__ import annotations

from typing import Any, Callable

from fastapi import APIRouter, Depends, HTTPException

from ...models import FacadeBody, InjectionModeBody
from .injection_service import InjectionService


class InjectionApi:
    def __init__(
        self,
        service: InjectionService,
        require_edge: Callable[..., None],
        require_edge_or_emulator: Callable[..., None],
    ):
        self.service = service
        self.router = APIRouter()
        self.router.add_api_route(
            "/api/injection-mode",
            self.get_mode,
            methods=["GET"],
        )
        self.router.add_api_route(
            "/api/injection-mode",
            self.set_mode,
            methods=["PUT"],
            dependencies=[Depends(require_edge)],
        )
        for path in ("/api/injection", "/api/facade"):
            self.router.add_api_route(
                path,
                self.inject,
                methods=["POST"],
                dependencies=[Depends(require_edge_or_emulator)],
            )

    def get_mode(self) -> dict[str, Any]:
        return self.service.mode()

    def set_mode(self, body: InjectionModeBody) -> dict[str, Any]:
        try:
            snapshot = self.service.set_mode(body.mode, body.source)
        except ValueError as exc:
            raise HTTPException(status_code=400, detail=str(exc)) from exc
        return {"ok": True, **snapshot}

    def inject(self, body: FacadeBody) -> dict[str, Any]:
        try:
            results = self.service.inject(body.values, body.source)
        except KeyError as exc:
            raise HTTPException(status_code=404, detail=exc.args[0]) from exc
        except PermissionError as exc:
            raise HTTPException(status_code=403, detail=str(exc)) from exc
        except (BufferError, ValueError) as exc:
            raise HTTPException(status_code=409, detail=str(exc)) from exc
        return {"ok": True, "results": results}
