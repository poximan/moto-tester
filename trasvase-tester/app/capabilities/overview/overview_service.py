from __future__ import annotations

import logging
from typing import Any

from ...config import AppConfig
from ...state import RuntimeState


class OverviewService:
    def __init__(self, config: AppConfig, state: RuntimeState, logger: logging.Logger):
        self.config = config
        self.state = state
        self.logger = logger

    def health(self) -> dict[str, Any]:
        snapshot = self.state.snapshot()
        return {
            "ok": True,
            "connected": snapshot["connection"].get("connected", False),
            "mode": snapshot["connection"].get("mode"),
            "injection_mode": snapshot["injection_mode"].get("mode"),
            "injection_enabled": snapshot["injection_mode"].get("enabled"),
            "modbus_polling": snapshot["modbus_polling"],
            "last_error": snapshot["connection"].get("last_error"),
        }

    def snapshot(self) -> dict[str, Any]:
        return self.state.snapshot()

    def config_contract(self) -> dict[str, Any]:
        return {
            "project": self.config.project,
            "controller": {
                "host": self.config.controller.host,
                "port": self.config.controller.port,
                "unit_id": self.config.controller.unit_id,
                "timeout_s": self.config.controller.timeout_s,
            },
            "server": {
                "host": self.config.server.host,
                "port": self.config.server.port,
            },
            "polling": {
                "interval_ms": self.config.polling.interval_ms,
                "max_stale_ms": self.config.polling.max_stale_ms,
            },
            "addressing_mode": self.config.addressing_mode,
            "injection_mode": self.state.injection_mode_snapshot(),
            "modbus_polling": self.state.polling_control_snapshot(),
            "field_emulator_url": self.config.runtime.field_emulator_url,
            "tables": {
                name: {
                    "label": table.label,
                    "kind": table.kind,
                    "start_ref": table.start_ref,
                    "start_pdu": table.start_pdu,
                    "count": table.count,
                    "writable": table.writable,
                    "data_type": table.data_type,
                    "optional": table.optional,
                    "signals": [
                        {
                            "row": signal.row,
                            "tag": signal.tag,
                            "label": signal.label,
                            "mapped_value": signal.mapped_value,
                            "reference": signal.reference,
                            "pdu_address": signal.pdu_address,
                            "function_code": signal.function_code,
                            "writable": signal.writable,
                            "facade": signal.facade,
                            "write_kind": signal.write_kind,
                            "write_reference": signal.write_reference,
                            "write_pdu_address": signal.write_pdu_address,
                            "write_function_code": signal.write_function_code,
                            "injects_tag": signal.injects_tag,
                            "injection_group": signal.injection_group,
                            "data_type": signal.data_type,
                            "default": signal.default,
                        }
                        for signal in table.signals
                    ],
                }
                for name, table in self.config.tables.items()
            },
        }

    def polling(self) -> dict[str, Any]:
        return self.state.polling_control_snapshot()

    def set_polling(
        self,
        function_code: str,
        *,
        enabled: bool | None,
        sample_rate_ms: int | None,
        source: str,
    ) -> dict[str, Any]:
        self.logger.info(
            "polling control request fc=%s enabled=%s sample_rate_ms=%s source=%s",
            function_code,
            enabled,
            sample_rate_ms,
            source,
        )
        return self.state.update_polling_control(
            function_code,
            enabled=enabled,
            sample_rate_ms=sample_rate_ms,
            source=source,
        )
