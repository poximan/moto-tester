from __future__ import annotations

import time
from collections import deque
from dataclasses import asdict, dataclass
from threading import Lock
from typing import Any, Literal

from .config import AppConfig, Signal
from .polling_control import PollingControlStore
from .write_mode import WriteModeStore

Quality = Literal["unknown", "good", "stale", "error", "local"]
WriteKind = Literal["coil", "holding_register"]


@dataclass
class SignalValue:
    tag: str
    label: str
    mapped_value: str | None
    table: str
    kind: str
    row: int
    reference: int
    pdu_address: int
    function_code: str
    writable: bool = False
    facade: bool = False
    write_kind: str | None = None
    write_reference: int | None = None
    write_pdu_address: int | None = None
    write_function_code: str | None = None
    injects_tag: str | None = None
    injection_group: str | None = None
    value: Any = None
    quality: Quality = "unknown"
    updated_at: float | None = None
    error: str | None = None


@dataclass
class WriteRequest:
    tag: str
    value: bool | int
    source: str
    created_at: float


class RuntimeState:
    def __init__(
        self,
        config: AppConfig,
        write_mode: WriteModeStore,
        polling_control: PollingControlStore,
    ):
        self.config = config
        self.write_mode = write_mode
        self.polling_control = polling_control
        self._lock = Lock()
        self._values: dict[str, SignalValue] = {
            tag: SignalValue(
                tag=tag,
                label=signal.label,
                mapped_value=signal.mapped_value,
                table=signal.table,
                kind=signal.kind,
                row=signal.row,
                reference=signal.reference,
                pdu_address=signal.pdu_address,
                function_code=signal.function_code,
                writable=signal.writable,
                facade=signal.facade,
                write_kind=signal.write_kind,
                write_reference=signal.write_reference,
                write_pdu_address=signal.write_pdu_address,
                write_function_code=signal.write_function_code,
                injects_tag=signal.injects_tag,
                injection_group=signal.injection_group,
                value=signal.default,
                quality="local" if signal.default is not None else "unknown",
                updated_at=time.time() if signal.default is not None else None,
            )
            for tag, signal in config.signals_by_tag.items()
        }
        self._connection: dict[str, Any] = {
            "connected": False,
            "last_poll_at": None,
            "last_success_at": None,
            "last_error": None,
            "poll_count": 0,
            "error_count": 0,
            "mode": "simulation" if config.runtime.simulation_mode else "modbus",
        }
        self._events: deque[dict[str, Any]] = deque(maxlen=300)
        self._write_queue: deque[WriteRequest] = deque(maxlen=200)
        self._local_commands: dict[str, Any] = {}
        self.add_event("startup", "Runtime iniciado", level="info")

    def add_event(self, event_type: str, message: str, level: str = "info", **extra: Any) -> None:
        event = {
            "ts": time.time(),
            "type": event_type,
            "level": level,
            "message": message,
            **extra,
        }
        with self._lock:
            self._events.appendleft(event)

    def update_connection(self, **kwargs: Any) -> None:
        with self._lock:
            self._connection.update(kwargs)

    def mark_poll_start(self) -> None:
        with self._lock:
            self._connection["last_poll_at"] = time.time()
            self._connection["poll_count"] += 1

    def mark_poll_success(self) -> None:
        with self._lock:
            self._connection.update({"connected": True, "last_success_at": time.time(), "last_error": None})

    def mark_poll_error(self, error: str) -> None:
        with self._lock:
            self._connection.update({"connected": False, "last_error": error})
            self._connection["error_count"] += 1

    def update_values(self, updates: dict[str, Any], quality: Quality = "good", error: str | None = None) -> None:
        now = time.time()
        with self._lock:
            for tag, value in updates.items():
                if tag not in self._values:
                    continue
                item = self._values[tag]
                item.value = value
                item.quality = quality
                item.updated_at = now
                item.error = error

    def update_value(self, tag: str, value: Any, quality: Quality = "good", error: str | None = None) -> None:
        self.update_values({tag: value}, quality=quality, error=error)

    def mark_table_error(self, table_name: str, error: str) -> None:
        now = time.time()
        with self._lock:
            for item in self._values.values():
                if item.table == table_name and not item.facade:
                    item.quality = "error"
                    item.updated_at = now
                    item.error = error

    def enqueue_write(self, tag: str, value: bool | int, source: str = "web") -> dict[str, Any]:
        signal = self.config.signals_by_tag.get(tag)
        if signal is None:
            raise KeyError(f"Tag no definido: {tag}")
        if not signal.writable:
            raise PermissionError(f"El tag {tag} no está marcado como escribible")

        now = time.time()
        with self._lock:
            self._local_commands[tag] = {"value": value, "source": source, "created_at": now}
            mode_snapshot = self.write_mode.snapshot()
            if not bool(mode_snapshot["write_enabled"]):
                # Etapa read_only: registrar pedido y reflejarlo como valor local para feedback de UI.
                if tag in self._values:
                    item = self._values[tag]
                    item.value = value
                    item.quality = "local"
                    item.updated_at = now
                    item.error = f"write_mode={mode_snapshot['mode']}: comando no escrito en PLC"
                self._events.appendleft(
                    {
                        "ts": now,
                        "type": "command_local",
                        "level": "warning",
                        "message": f"Comando {tag}={value} registrado localmente; modo {mode_snapshot['mode']}",
                        "tag": tag,
                        "value": value,
                        "source": source,
                    }
                )
                return {"queued": False, "written": False, "reason": f"write_mode={mode_snapshot['mode']}"}

            request = WriteRequest(tag=tag, value=value, source=source, created_at=now)
            self._write_queue.append(request)
            # Eco local inmediato: evita que la UI y el emulador queden un ciclo
            # atrasados mientras el poller procesa la escritura Modbus. La
            # confirmación real reemplaza esta marca con quality=good/error.
            if tag in self._values:
                item = self._values[tag]
                item.value = value
                item.quality = "local"
                item.updated_at = now
                item.error = "write queued"
            self._events.appendleft(
                {
                    "ts": now,
                    "type": "command_queued",
                    "level": "info",
                    "message": f"Comando {tag}={value} encolado para escritura PLC",
                    "tag": tag,
                    "value": value,
                    "source": source,
                }
            )
            return {"queued": True, "written": False}

    def drain_writes(self, limit: int = 50) -> list[WriteRequest]:
        drained: list[WriteRequest] = []
        with self._lock:
            while self._write_queue and len(drained) < limit:
                drained.append(self._write_queue.popleft())
        return drained

    def has_pending_writes(self) -> bool:
        with self._lock:
            return bool(self._write_queue)

    def writes_enabled(self) -> bool:
        return self.write_mode.is_write_enabled()

    def write_mode_snapshot(self) -> dict[str, Any]:
        return self.write_mode.snapshot()

    def set_write_mode(self, mode: str, source: str = "web") -> dict[str, Any]:
        snapshot = self.write_mode.set_mode(mode)
        self.add_event(
            "write_mode",
            f"Modo de escritura cambiado a {snapshot['mode']}",
            level="warning" if snapshot["write_enabled"] else "info",
            source=source,
        )
        return snapshot

    def polling_control_snapshot(self) -> dict[str, Any]:
        return self.polling_control.snapshot()

    def update_polling_control(
        self,
        function_code: str,
        *,
        enabled: bool | None = None,
        sample_rate_ms: int | None = None,
        source: str = "web",
    ) -> dict[str, Any]:
        snapshot = self.polling_control.update(
            function_code,
            enabled=enabled,
            sample_rate_ms=sample_rate_ms,
        )
        self.add_event(
            "polling_control",
            (
                f"FC{int(snapshot['function_code'])} "
                f"{'activa' if snapshot['enabled'] else 'pausada'} "
                f"cada {snapshot['sample_rate_ms']} ms"
            ),
            level="info" if snapshot["enabled"] else "warning",
            source=source,
        )
        return snapshot

    def write_result(self, tag: str, value: Any, ok: bool, error: str | None = None) -> None:
        now = time.time()
        with self._lock:
            if tag in self._values:
                item = self._values[tag]
                item.value = value
                item.quality = "good" if ok else "error"
                item.updated_at = now
                item.error = error
            self._events.appendleft(
                {
                    "ts": now,
                    "type": "write_ok" if ok else "write_error",
                    "level": "info" if ok else "error",
                    "message": f"Escritura {tag}={value} {'OK' if ok else 'falló'}",
                    "tag": tag,
                    "value": value,
                    "error": error,
                }
            )

    def snapshot(self) -> dict[str, Any]:
        now = time.time()
        with self._lock:
            values = {tag: asdict(value) for tag, value in self._values.items()}
            connection = dict(self._connection)
            events = list(self._events)[:100]
            local_commands = dict(self._local_commands)

        polling_control = self.polling_control.snapshot()
        max_stale_s = self.config.polling.max_stale_ms / 1000.0
        for item in values.values():
            updated_at = item.get("updated_at")
            item["age_s"] = None if updated_at is None else round(now - updated_at, 3)
            function_control = polling_control["functions"].get(item["function_code"], {})
            signal_stale_s = max(
                max_stale_s,
                int(function_control.get("sample_rate_ms", 0)) / 1000.0 * 2,
            )
            if updated_at and now - updated_at > signal_stale_s and item.get("quality") == "good":
                item["quality"] = "stale"

        write_mode = self.write_mode.snapshot()

        return {
            "project": self.config.project,
            "timestamp": now,
            "connection": connection,
            "write_mode": write_mode,
            "modbus_polling": polling_control,
            "controller": {
                "host": self.config.controller.host,
                "port": self.config.controller.port,
                "unit_id": self.config.controller.unit_id,
            },
            "values": values,
            "groups": self._build_groups(values),
            "events": events,
            "local_commands": local_commands,
        }

    def _build_groups(self, values: dict[str, dict[str, Any]]) -> dict[str, Any]:
        pumps: list[dict[str, Any]] = []
        for pump in range(1, 6):
            prefix = f"bB{pump}"
            pumps.append(
                {
                    "id": pump,
                    "rtu": values.get(f"{prefix}RTU"),
                    "aut": values.get(f"{prefix}Aut"),
                    "ok": values.get(f"{prefix}Ok"),
                    "running": values.get(f"{prefix}EMar"),
                    "arr": values.get(f"{prefix}Arndo"),
                    "interlock": values.get(f"{prefix}InE"),
                    "fault": values.get(f"{prefix}Falla"),
                    "hours": values.get(f"eB{pump}Hs"),
                    "cmd_aut": values.get(f"cB{pump}Aut"),
                    "cmd_mr": values.get(f"cB{pump}Mr"),
                }
            )
        return {
            "process": {
                "nivel_camara_aspiracion": values.get("eNvCamAsp"),
                "nivel_reserva": values.get("eNvRes"),
                "turbiedad": values.get("eTurb"),
                "reserva": {
                    "rebalse": values.get("bResRb"),
                    "alto": values.get("bResAt"),
                    "bajo": values.get("bResBj"),
                    "alto_pera": values.get("bResNvAtP"),
                    "bajo_pera": values.get("bResNvBjP"),
                },
                "camara_aspiracion": {
                    "rebalse": values.get("bCAspRb"),
                    "alto": values.get("bCAspAt"),
                    "bajo": values.get("bCAspBj"),
                    "alto_pera": values.get("bCAspNvAtP"),
                    "bajo_pera": values.get("bCAspNvBjP"),
                },
            },
            "pumps": pumps,
        }
