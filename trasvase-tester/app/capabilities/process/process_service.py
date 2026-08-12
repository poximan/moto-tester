from __future__ import annotations

from typing import Any

from ...adapters.emulator_client import EmulatorClient


class ProcessService:
    def __init__(self, emulator_client: EmulatorClient):
        self.emulator_client = emulator_client

    def state(self) -> dict[str, Any]:
        return self.emulator_client.request("GET", "/state")

    def set_valves(self, values: dict[str, Any]) -> dict[str, Any]:
        payload = {key: value for key, value in values.items() if value is not None}
        return self.emulator_client.request("PUT", "/valves", payload)
