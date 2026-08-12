from __future__ import annotations

from typing import Any

from ...config import AppConfig
from ...state import RuntimeState


class ProductionService:
    def __init__(self, config: AppConfig, state: RuntimeState):
        self.config = config
        self.state = state

    def write(self, tag: str, value: Any, source: str) -> dict[str, Any]:
        signal = self.config.signals_by_tag.get(tag)
        if signal is None:
            raise KeyError(f"Tag no definido: {tag}")
        if not signal.writable:
            raise PermissionError(f"{tag} no está definido como escribible")
        result = self.state.enqueue_write(tag, value, source=source)
        return {"ok": True, "tag": tag, "value": value, **result}
