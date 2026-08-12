from __future__ import annotations

from typing import Any

from fastapi import APIRouter

from .diagnostics_service import DiagnosticsService


class DiagnosticsApi:
    def __init__(self, service: DiagnosticsService):
        self.service = service
        self.router = APIRouter()
        self.router.add_api_route("/api/events", self.events, methods=["GET"])
        self.router.add_api_route(
            "/api/diagnostics",
            self.diagnostics,
            methods=["GET"],
        )
        self.router.add_api_route("/api/logs", self.logs, methods=["GET"])
        self.router.add_api_route(
            "/api/logs/{log_name}",
            self.read_log,
            methods=["GET"],
        )

    def events(self) -> dict[str, Any]:
        return self.service.events()

    def diagnostics(self) -> dict[str, Any]:
        return self.service.diagnostics()

    def logs(self) -> dict[str, Any]:
        return self.service.logs()

    def read_log(self, log_name: str, lines: int = 300) -> dict[str, Any]:
        return self.service.read_log(log_name, lines)
