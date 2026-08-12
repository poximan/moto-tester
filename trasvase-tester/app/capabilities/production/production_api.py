from __future__ import annotations

from typing import Any, Callable

from fastapi import APIRouter, Depends, HTTPException

from ...models import GenericWriteBody
from .production_service import ProductionService


class ProductionApi:
    def __init__(
        self,
        service: ProductionService,
        require_operator: Callable[..., None],
    ):
        self.service = service
        self.router = APIRouter(dependencies=[Depends(require_operator)])
        self.router.add_api_route("/api/write", self.write, methods=["POST"])

    def write(self, body: GenericWriteBody) -> dict[str, Any]:
        try:
            return self.service.write(body.tag, body.value, body.source)
        except KeyError as exc:
            raise HTTPException(status_code=404, detail=exc.args[0]) from exc
        except PermissionError as exc:
            raise HTTPException(status_code=403, detail=str(exc)) from exc
        except (BufferError, ValueError) as exc:
            raise HTTPException(status_code=409, detail=str(exc)) from exc
