from __future__ import annotations

import hmac

from fastapi import HTTPException, Request


EDGE_OPERATOR_MODES = frozenset({"secure", "protected"})


class EdgeAccessGuard:
    def __init__(self, internal_emulator_token: str):
        self.internal_emulator_token = internal_emulator_token

    @staticmethod
    def require_edge(request: Request) -> None:
        if request.headers.get("x-edge-mode", "") not in EDGE_OPERATOR_MODES:
            raise HTTPException(
                status_code=403,
                detail="Acceso requerido a traves de edge-platform",
            )

    def require_edge_or_emulator(self, request: Request) -> None:
        supplied_token = request.headers.get("x-internal-emulator-token", "")
        if supplied_token and hmac.compare_digest(
            supplied_token,
            self.internal_emulator_token,
        ):
            return
        self.require_edge(request)
