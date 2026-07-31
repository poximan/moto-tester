from __future__ import annotations

import logging
import math
import random
import threading
import time
from typing import Any

from pymodbus.client import ModbusTcpClient

from .config import AppConfig, Signal, TableDefinition
from .state import RuntimeState, WriteRequest

LOGGER = logging.getLogger("trasvase.modbus")


def _decode_register(raw: int, data_type: str | None) -> int:
    if data_type == "uint16" or data_type is None:
        return int(raw)
    if data_type == "int16":
        return int(raw) - 0x10000 if int(raw) & 0x8000 else int(raw)
    raise ValueError(f"Tipo de dato no soportado para registro: {data_type}")


def _encode_register(value: int, data_type: str | None) -> int:
    if data_type in (None, "uint16"):
        if not 0 <= int(value) <= 0xFFFF:
            raise ValueError(f"Valor fuera de rango uint16: {value}")
        return int(value)
    if data_type == "int16":
        if not -32768 <= int(value) <= 32767:
            raise ValueError(f"Valor fuera de rango int16: {value}")
        return int(value) & 0xFFFF
    raise ValueError(f"Tipo de dato no soportado para registro: {data_type}")


def _call_modbus(method: Any, *args: Any, slave: int, **kwargs: Any) -> Any:
    """Pymodbus changed the unit-id keyword across versions.

    Try the current keyword first, then fall back to older variants.
    """
    try:
        return method(*args, slave=slave, **kwargs)
    except TypeError:
        try:
            return method(*args, unit=slave, **kwargs)
        except TypeError:
            return method(*args, device_id=slave, **kwargs)


class ModbusPoller:
    def __init__(self, config: AppConfig, state: RuntimeState):
        self.config = config
        self.state = state
        self._stop = threading.Event()
        self._thread: threading.Thread | None = None
        self._client: ModbusTcpClient | None = None
        self._next_due: dict[str, float] = {}
        self._polling_revision = -1

    def start(self) -> None:
        if self._thread and self._thread.is_alive():
            return
        LOGGER.info(
            "modbus poller start host=%s port=%s unit_id=%s timeout_s=%s default_interval_ms=%s",
            self.config.controller.host,
            self.config.controller.port,
            self.config.controller.unit_id,
            self.config.controller.timeout_s,
            self.config.polling.interval_ms,
        )
        self._thread = threading.Thread(target=self._run, name="modbus-poller", daemon=True)
        self._thread.start()

    def stop(self) -> None:
        LOGGER.info("modbus poller stop")
        self._stop.set()
        if self._thread:
            self._thread.join(timeout=3)
        if self._client:
            self._client.close()

    def _run(self) -> None:
        while not self._stop.is_set():
            polling = self.state.polling_control_snapshot()
            if polling["revision"] != self._polling_revision:
                self._reset_schedule(polling)
                self._polling_revision = int(polling["revision"])

            now = time.monotonic()
            due_tables: list[TableDefinition] = []
            for table in self.config.tables.values():
                signals = self._pollable_signals(table)
                if not signals:
                    continue
                function_code = signals[0].function_code
                control = polling["functions"][function_code]
                if not control["enabled"]:
                    self._next_due.pop(function_code, None)
                    continue
                if now >= self._next_due.get(function_code, 0.0):
                    due_tables.append(table)
                    self._next_due[function_code] = (
                        now + int(control["sample_rate_ms"]) / 1000.0
                    )

            if due_tables:
                self.state.mark_poll_start()
                self._poll_tables(due_tables)

            try:
                self._process_writes()
            except Exception as exc:  # noqa: BLE001 - poller must not die
                error = f"{type(exc).__name__}: {exc}"
                LOGGER.exception("modbus write cycle error: %s", error)
                self.state.mark_poll_error(error)
                self.state.add_event("write_cycle_error", error, level="error")
                self._safe_close()
                self._stop.wait(self.config.controller.reconnect_backoff_s)

            self._stop.wait(0.1)

    def _reset_schedule(self, polling: dict[str, Any]) -> None:
        """Desfasa el primer ciclo para evitar una rafaga de cuatro pedidos."""
        self._next_due.clear()
        enabled = [
            code
            for code, control in polling["functions"].items()
            if control["enabled"]
        ]
        if not enabled:
            return
        now = time.monotonic()
        shortest_interval_s = min(
            int(polling["functions"][code]["sample_rate_ms"]) / 1000.0
            for code in enabled
        )
        spacing_s = shortest_interval_s / len(enabled)
        for index, function_code in enumerate(enabled):
            self._next_due[function_code] = now + index * spacing_s

    def _ensure_client(self) -> None:
        if self._client is not None and self._client.connected:
            return
        self._client = ModbusTcpClient(
            host=self.config.controller.host,
            port=self.config.controller.port,
            timeout=self.config.controller.timeout_s,
        )
        LOGGER.info("modbus connecting host=%s port=%s unit_id=%s", self.config.controller.host, self.config.controller.port, self.config.controller.unit_id)
        if not self._client.connect():
            LOGGER.error("modbus connection failed host=%s port=%s unit_id=%s", self.config.controller.host, self.config.controller.port, self.config.controller.unit_id)
            raise ConnectionError(
                f"No se pudo conectar a {self.config.controller.host}:{self.config.controller.port}"
            )
        LOGGER.info("modbus connected host=%s port=%s unit_id=%s", self.config.controller.host, self.config.controller.port, self.config.controller.unit_id)
        self.state.update_connection(connected=True)
        self.state.add_event(
            "modbus_connected",
            f"Conectado a {self.config.controller.host}:{self.config.controller.port} unit {self.config.controller.unit_id}",
            level="info",
        )

    def _safe_close(self) -> None:
        if self._client:
            try:
                self._client.close()
            finally:
                self._client = None

    def _poll_tables(self, tables: list[TableDefinition]) -> None:
        try:
            self._ensure_client()
        except Exception as exc:  # noqa: BLE001
            error = f"{type(exc).__name__}: {exc}"
            for table in tables:
                signals = self._pollable_signals(table)
                if not signals:
                    continue
                function_code = signals[0].function_code
                self.state.polling_control.mark_attempt(function_code)
                self.state.polling_control.mark_error(function_code, error)
                self.state.mark_table_error(table.name, error)
            self.state.mark_poll_error(error)
            self.state.add_event("poll_connection_error", error, level="error")
            self._safe_close()
            self._stop.wait(self.config.controller.reconnect_backoff_s)
            return

        successes = 0
        errors: list[str] = []
        for table in tables:
            signals = self._pollable_signals(table)
            if not signals:
                continue
            function_code = signals[0].function_code
            self.state.polling_control.mark_attempt(function_code)
            try:
                updates = self._read_table(table)
                if updates:
                    self.state.update_values(updates, quality="good")
                self.state.polling_control.mark_success(function_code)
                successes += 1
            except Exception as exc:  # noqa: BLE001
                error = f"{type(exc).__name__}: {exc}"
                LOGGER.exception("modbus table read error table=%s error=%s", table.name, error)
                self.state.polling_control.mark_error(function_code, error)
                self.state.mark_table_error(table.name, error)
                errors.append(f"FC{int(function_code)}: {error}")
                self.state.add_event(
                    "table_poll_error",
                    f"FC{int(function_code)} {table.name}: {error}",
                    level="error",
                )

        if successes:
            self.state.mark_poll_success()
        elif errors:
            self.state.mark_poll_error("; ".join(errors))
            if self._client is not None and not self._client.connected:
                self._safe_close()

    @staticmethod
    def _pollable_signals(table: TableDefinition) -> list[Signal]:
        # Las zonas y* son memoria de entrada para inyección hacia el PLC.
        # No se leen para representar el estado del proceso: el feedback oficial
        # siempre son sus análogas reales e*/b* del intercambio genuino.
        return [sig for sig in table.signals if not sig.facade]

    @classmethod
    def _poll_count(cls, table: TableDefinition) -> int:
        signals = cls._pollable_signals(table)
        if not signals:
            return 0
        return max(sig.row for sig in signals) + 1

    def _read_table(self, table: TableDefinition) -> dict[str, Any]:
        if self._client is None:
            raise RuntimeError("Cliente Modbus no inicializado")
        slave = self.config.controller.unit_id
        signals = self._pollable_signals(table)
        read_count = self._poll_count(table)
        if read_count <= 0:
            return {}

        LOGGER.info(
            "modbus read table=%s kind=%s fc=%s ref_start=%s pdu_start=%s count=%s unit_id=%s",
            table.name,
            table.kind,
            signals[0].function_code if signals else "?",
            table.start_ref,
            table.start_pdu,
            read_count,
            slave,
        )

        if table.kind == "input_register":
            result = _call_modbus(
                self._client.read_input_registers,
                address=table.start_pdu,
                count=read_count,
                slave=slave,
            )
            self._raise_on_error(result)
            raw_values = list(result.registers)
            return {
                sig.tag: _decode_register(raw_values[sig.row], sig.data_type)
                for sig in signals
            }

        if table.kind == "holding_register":
            result = _call_modbus(
                self._client.read_holding_registers,
                address=table.start_pdu,
                count=read_count,
                slave=slave,
            )
            self._raise_on_error(result)
            raw_values = list(result.registers)
            return {
                sig.tag: _decode_register(raw_values[sig.row], sig.data_type)
                for sig in signals
            }

        if table.kind == "discrete_input":
            result = _call_modbus(
                self._client.read_discrete_inputs,
                address=table.start_pdu,
                count=read_count,
                slave=slave,
            )
            self._raise_on_error(result)
            raw_bits = list(result.bits)[: read_count]
            return {sig.tag: bool(raw_bits[sig.row]) for sig in signals}

        if table.kind == "coil":
            result = _call_modbus(
                self._client.read_coils,
                address=table.start_pdu,
                count=read_count,
                slave=slave,
            )
            self._raise_on_error(result)
            raw_bits = list(result.bits)[: read_count]
            return {sig.tag: bool(raw_bits[sig.row]) for sig in signals}

        raise ValueError(f"Tipo de tabla no soportado: {table.kind}")

    @staticmethod
    def _raise_on_error(result: Any) -> None:
        if result is None:
            raise TimeoutError("Respuesta Modbus vacía")
        is_error = getattr(result, "isError", None)
        if callable(is_error) and is_error():
            raise RuntimeError(str(result))

    def _process_writes(self) -> None:
        if not self.state.has_pending_writes():
            return
        if not self.state.writes_enabled():
            for request in self.state.drain_writes():
                self.state.write_result(
                    request.tag,
                    request.value,
                    ok=False,
                    error="write_mode=read_only",
                )
            return
        if self._client is None:
            self._ensure_client()
        for request in self.state.drain_writes():
            self._write_request(request)

    def _write_request(self, request: WriteRequest) -> None:
        signal = self.config.signals_by_tag[request.tag]
        write_kind = signal.effective_write_kind
        write_address = signal.effective_write_pdu_address
        LOGGER.info(
            "modbus write tag=%s value=%s kind=%s fc=%s ref=%s pdu=%s source=%s unit_id=%s",
            signal.tag,
            request.value,
            write_kind,
            signal.write_function_code,
            signal.effective_write_reference,
            write_address,
            request.source,
            self.config.controller.unit_id,
        )

        if write_kind == "coil":
            result = _call_modbus(
                self._client.write_coil,
                address=write_address,
                value=bool(request.value),
                slave=self.config.controller.unit_id,
            )
            try:
                self._raise_on_error(result)
                LOGGER.info("modbus write ok tag=%s value=%s", signal.tag, bool(request.value))
                self.state.write_result(signal.tag, bool(request.value), ok=True)
            except Exception as exc:  # noqa: BLE001
                LOGGER.exception("modbus write error tag=%s value=%s error=%s", signal.tag, request.value, exc)
                self.state.write_result(signal.tag, request.value, ok=False, error=str(exc))
            return

        if write_kind == "holding_register":
            result = _call_modbus(
                self._client.write_register,
                address=write_address,
                value=_encode_register(int(request.value), signal.data_type),
                slave=self.config.controller.unit_id,
            )
            try:
                self._raise_on_error(result)
                LOGGER.info("modbus write ok tag=%s value=%s", signal.tag, request.value)
                self.state.write_result(signal.tag, request.value, ok=True)
            except Exception as exc:  # noqa: BLE001
                LOGGER.exception("modbus write error tag=%s value=%s error=%s", signal.tag, request.value, exc)
                self.state.write_result(signal.tag, request.value, ok=False, error=str(exc))
            return

        self.state.write_result(
            signal.tag,
            request.value,
            ok=False,
            error=f"Escritura no soportada para tabla {signal.kind}; write_kind={write_kind}",
        )


class SimulationPoller:
    """Genera valores locales para validar UI/API sin conexión al PLC."""

    def __init__(self, config: AppConfig, state: RuntimeState):
        self.config = config
        self.state = state
        self._stop = threading.Event()
        self._thread: threading.Thread | None = None
        self._t0 = time.monotonic()

    def start(self) -> None:
        LOGGER.warning("simulation poller start; no hay tráfico Modbus")
        self._thread = threading.Thread(target=self._run, name="simulation-poller", daemon=True)
        self._thread.start()
        self.state.add_event("simulation", "Modo simulación activo; no hay tráfico Modbus", level="warning")

    def stop(self) -> None:
        self._stop.set()
        if self._thread:
            self._thread.join(timeout=2)

    def _run(self) -> None:
        interval_s = max(self.config.polling.interval_ms / 1000.0, 0.1)
        while not self._stop.is_set():
            self.state.mark_poll_start()
            t = time.monotonic() - self._t0
            updates: dict[str, Any] = {
                "eNvCamAsp": int(2500 + 900 * math.sin(t / 13.0)),
                "eNvRes": int(3300 + 1200 * math.sin(t / 31.0)),
                "eTurb": int(20 + 5 * math.sin(t / 7.0)),
                "bRFF": True,
            }
            for pump in range(1, 6):
                running = (int(t / 8) + pump) % 5 < 2
                fault = random.random() < 0.005
                updates.update(
                    {
                        f"eB{pump}Hs": 1000 + pump * 100 + int(t / 60),
                        f"bB{pump}RTU": True,
                        f"bB{pump}Aut": pump != 5,
                        f"bB{pump}Ok": not fault,
                        f"bB{pump}EMar": running,
                        f"bB{pump}InE": False,
                        f"bB{pump}Falla": fault,
                        f"bB{pump}Arndo": running,
                    }
                )
            for tag, signal in self.config.signals_by_tag.items():
                if signal.table == "analog_setpoints" and signal.default is not None:
                    updates[tag] = signal.default
            self.state.update_values(updates, quality="good")

            # En simulación no hay cliente Modbus que confirme la escritura.
            # Si el modo operativo está en write_enabled, aplicamos la cola sobre
            # el espejo local para que el emulador de campo pueda escribir
            # yNvCamAsp/yNvRes con el mismo comportamiento observable que tendría
            # una confirmación de escritura del PLC.
            if self.state.writes_enabled():
                for request in self.state.drain_writes():
                    self.state.write_result(request.tag, request.value, ok=True)

            self.state.update_connection(connected=True, last_error=None)
            self.state.mark_poll_success()
            time.sleep(interval_s)
