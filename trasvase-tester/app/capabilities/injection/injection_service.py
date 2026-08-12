from __future__ import annotations

import logging
from typing import Any

from ...config import AppConfig
from ...state import RuntimeState


class InjectionService:
    def __init__(self, config: AppConfig, state: RuntimeState, logger: logging.Logger):
        self.config = config
        self.state = state
        self.logger = logger

    def mode(self) -> dict[str, Any]:
        return self.state.injection_mode_snapshot()

    def set_mode(self, mode: str, source: str) -> dict[str, Any]:
        self.logger.warning(
            "injection_mode request mode=%s source=%s",
            mode,
            source,
        )
        return self.state.set_injection_mode(mode, source=source)

    def inject(self, values: dict[str, Any], source: str) -> dict[str, Any]:
        self.logger.info("injection request source=%s values=%s", source, values)
        for tag in values:
            signal = self.config.signals_by_tag.get(tag)
            if signal is None:
                raise KeyError(f"Tag de inyección no definido: {tag}")
            if not signal.writable or not signal.facade:
                raise PermissionError(f"{tag} no pertenece a inyección escribible")
        return self.state.enqueue_injections(values, source=source)
