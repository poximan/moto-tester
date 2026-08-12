from __future__ import annotations

import logging
from typing import Any

from ...adapters.emulator_client import EmulatorClient
from ...config import AppConfig
from ...state import RuntimeState


class PumpsService:
    def __init__(
        self,
        config: AppConfig,
        state: RuntimeState,
        emulator_client: EmulatorClient,
        logger: logging.Logger,
    ):
        self.config = config
        self.state = state
        self.emulator_client = emulator_client
        self.logger = logger

    def command(self, tag: str, value: bool, source: str) -> dict[str, Any]:
        signal = self.config.signals_by_tag.get(tag)
        if signal is None:
            raise KeyError(f"Tag no definido: {tag}")
        if signal.table != "digital_commands" or signal.facade:
            raise ValueError("Este endpoint solo acepta comandos digitales reales cB#")
        result = self.state.enqueue_write(tag, value, source=source)
        return {"ok": True, "tag": tag, "value": value, **result}

    def pump_command(
        self,
        pump_id: int,
        *,
        aut: bool | None,
        mr: bool | None,
        source: str,
    ) -> dict[str, Any]:
        self.logger.info(
            "pump command pump=%s aut=%s mr=%s source=%s",
            pump_id,
            aut,
            mr,
            source,
        )
        if pump_id < 1 or pump_id > 5:
            raise KeyError("pump_id debe estar entre 1 y 5")
        requested: dict[str, bool] = {}
        if aut is not None:
            requested[f"cB{pump_id}Aut"] = bool(aut)
        if mr is not None:
            requested[f"cB{pump_id}Mr"] = bool(mr)
        results = self.state.enqueue_writes(requested, source=source)
        return {"ok": True, "pump_id": pump_id, "results": results}

    def set_generate_emar(self, pump_id: int, enabled: bool) -> dict[str, Any]:
        return self.emulator_client.request(
            "PUT",
            f"/pumps/{pump_id}/generate-emar",
            {"enabled": enabled},
        )
