from __future__ import annotations

import os
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

import yaml

from .addressing import (
    AddressingMode,
    TableKind,
    function_code_for,
    pdu_to_reference,
    reference_to_pdu,
)


_ENV_LOADED = False
_TRUE_VALUES = {"1", "true", "yes", "y", "on", "si", "sí"}
_FALSE_VALUES = {"0", "false", "no", "n", "off"}


def _load_dotenv() -> None:
    """Carga .env como única fuente de parámetros runtime para ejecución local.

    En Docker Compose esas mismas variables entran por env_file. No se toman
    valores de default.yaml para parámetros de ejecución.
    """
    global _ENV_LOADED
    if _ENV_LOADED:
        return
    _ENV_LOADED = True

    repo_root = Path(__file__).resolve().parents[1]
    candidates = [Path.cwd() / ".env", repo_root / ".env"]
    env_path = next((candidate for candidate in candidates if candidate.exists()), None)
    if env_path is None:
        return

    for line_no, line in enumerate(env_path.read_text(encoding="utf-8").splitlines(), start=1):
        stripped = line.strip()
        if not stripped or stripped.startswith("#"):
            continue
        if "=" not in stripped:
            raise ValueError(f"Línea inválida en {env_path}:{line_no}: {line!r}")
        key, value = stripped.split("=", 1)
        key = key.strip()
        value = value.strip().strip('"').strip("'")
        if not key:
            raise ValueError(f"Clave vacía en {env_path}:{line_no}")
        os.environ[key] = value


def _env_required(name: str) -> str:
    raw = os.getenv(name)
    if raw is None or raw == "":
        raise RuntimeError(f"Falta parámetro obligatorio en .env: {name}")
    return raw.strip()


def _env_bool(name: str) -> bool:
    raw = _env_required(name).lower()
    if raw in _TRUE_VALUES:
        return True
    if raw in _FALSE_VALUES:
        return False
    raise ValueError(f"Valor booleano inválido para {name}: {raw!r}")


def _env_int(name: str) -> int:
    return int(_env_required(name))


def _env_float(name: str) -> float:
    return float(_env_required(name))


@dataclass(frozen=True)
class Signal:
    table: str
    kind: TableKind
    row: int
    tag: str
    label: str
    mapped_value: str | None
    reference: int
    pdu_address: int
    data_type: str | None = None
    writable: bool = False
    default: int | bool | float | None = None
    facade: bool = False
    write_kind: TableKind | None = None
    write_reference: int | None = None
    write_pdu_address: int | None = None
    injects_tag: str | None = None
    injection_group: str | None = None

    @property
    def function_code(self) -> str:
        return function_code_for(self.kind)

    @property
    def effective_write_kind(self) -> TableKind:
        return self.write_kind or self.kind

    @property
    def effective_write_pdu_address(self) -> int:
        return self.write_pdu_address if self.write_pdu_address is not None else self.pdu_address

    @property
    def effective_write_reference(self) -> int:
        return self.write_reference if self.write_reference is not None else self.reference

    @property
    def write_function_code(self) -> str | None:
        if not self.writable:
            return None
        return function_code_for(self.effective_write_kind)


@dataclass(frozen=True)
class TableDefinition:
    name: str
    label: str
    kind: TableKind
    start_ref: int
    start_pdu: int
    count: int
    writable: bool
    data_type: str | None
    optional: bool = False
    signals: list[Signal] = field(default_factory=list)


@dataclass(frozen=True)
class ControllerConfig:
    host: str
    port: int
    unit_id: int
    timeout_s: float
    reconnect_backoff_s: float


@dataclass(frozen=True)
class ServerConfig:
    host: str
    port: int


@dataclass(frozen=True)
class PollingConfig:
    interval_ms: int
    max_stale_ms: int


@dataclass(frozen=True)
class RuntimeConfig:
    simulation_mode: bool
    field_emulator_url: str


@dataclass(frozen=True)
class AppConfig:
    project: dict[str, Any]
    server: ServerConfig
    controller: ControllerConfig
    polling: PollingConfig
    runtime: RuntimeConfig
    addressing_mode: AddressingMode
    tables: dict[str, TableDefinition]
    signals_by_tag: dict[str, Signal]
    raw: dict[str, Any]

    @property
    def writable_signals(self) -> dict[str, Signal]:
        return {tag: signal for tag, signal in self.signals_by_tag.items() if signal.writable}

    @property
    def facade_signals(self) -> dict[str, Signal]:
        return {tag: signal for tag, signal in self.signals_by_tag.items() if signal.facade}


def _resolve_write_address(
    *,
    signal_raw: dict[str, Any],
    read_kind: TableKind,
    read_reference: int,
    read_pdu_address: int,
    addressing_mode: AddressingMode,
) -> tuple[TableKind | None, int | None, int | None]:
    write_kind = signal_raw.get("write_kind")
    if write_kind is None:
        return None, None, None

    if "write_ref" in signal_raw:
        write_reference = int(signal_raw["write_ref"])
        write_pdu_address = reference_to_pdu(write_reference, write_kind, addressing_mode)
        return write_kind, write_reference, write_pdu_address

    # Alias por mismo PDU: útil para escribir por FC05/FC06 la memoria que se observa
    # como 1x/3x en la fachada del PLC.
    write_pdu_address = read_pdu_address
    write_reference = pdu_to_reference(write_pdu_address, write_kind, addressing_mode)
    return write_kind, write_reference, write_pdu_address


def load_config(path: str | Path | None = None) -> AppConfig:
    _load_dotenv()

    config_path = Path(path or "config/default.yaml")
    if not config_path.exists():
        alt = Path(__file__).resolve().parents[1] / config_path
        if alt.exists():
            config_path = alt
    if not config_path.exists():
        raise FileNotFoundError(f"No se encontró mapa Modbus: {config_path}")

    with config_path.open("r", encoding="utf-8") as f:
        raw: dict[str, Any] = yaml.safe_load(f)

    forbidden_runtime_sections = {"server", "controller", "polling", "safety", "runtime"}.intersection(raw)
    if forbidden_runtime_sections:
        sections = ", ".join(sorted(forbidden_runtime_sections))
        raise ValueError(
            f"config/default.yaml debe contener solo mapa/estructura. "
            f"Parámetros runtime detectados: {sections}. Moverlos a .env."
        )

    addressing_mode: AddressingMode = raw.get("addressing", {}).get("mode", "modicon_reference")

    controller = ControllerConfig(
        host=_env_required("MODBUS_HOST"),
        port=_env_int("MODBUS_PORT"),
        unit_id=_env_int("MODBUS_UNIT_ID"),
        timeout_s=_env_float("MODBUS_TIMEOUT_S"),
        reconnect_backoff_s=_env_float("MODBUS_RECONNECT_BACKOFF_S"),
    )

    server = ServerConfig(
        host=_env_required("WEB_HOST"),
        port=_env_int("WEB_PORT"),
    )

    polling = PollingConfig(
        interval_ms=_env_int("POLL_INTERVAL_MS"),
        max_stale_ms=_env_int("POLL_MAX_STALE_MS"),
    )


    runtime = RuntimeConfig(
        simulation_mode=_env_bool("SIMULATION_MODE"),
        field_emulator_url=os.getenv("FIELD_EMULATOR_URL", "http://field-emulator:8090").strip(),
    )

    tables: dict[str, TableDefinition] = {}
    signals_by_tag: dict[str, Signal] = {}

    for table_name, table_raw in raw.get("tables", {}).items():
        kind: TableKind = table_raw["kind"]
        start_ref = int(table_raw.get("start_ref", 0))
        count = int(table_raw.get("count", 0))
        if count == 0:
            start_pdu = 0
        else:
            start_pdu = reference_to_pdu(start_ref, kind, addressing_mode)
        table_writable = bool(table_raw.get("writable", False))
        data_type = table_raw.get("data_type")
        optional = bool(table_raw.get("optional", False))
        table_signals: list[Signal] = []

        for signal_raw in table_raw.get("signals", []):
            row = int(signal_raw["row"])
            if row < 0:
                raise ValueError(f"Fila inválida en {table_name}.{signal_raw.get('tag')}: {row}")
            if count and row >= count:
                raise ValueError(
                    f"Fila {row} de {table_name}.{signal_raw.get('tag')} excede count={count}"
                )
            tag = str(signal_raw["tag"])
            reference = start_ref + row if count else row
            pdu_address = reference_to_pdu(reference, kind, addressing_mode) if count else row
            write_kind, write_reference, write_pdu_address = _resolve_write_address(
                signal_raw=signal_raw,
                read_kind=kind,
                read_reference=reference,
                read_pdu_address=pdu_address,
                addressing_mode=addressing_mode,
            )
            signal = Signal(
                table=table_name,
                kind=kind,
                row=row,
                tag=tag,
                label=str(signal_raw.get("label", tag)),
                mapped_value=signal_raw.get("mapped_value"),
                reference=reference,
                pdu_address=pdu_address,
                data_type=signal_raw.get("data_type", data_type),
                writable=bool(signal_raw.get("writable", table_writable)),
                default=signal_raw.get("default"),
                facade=bool(signal_raw.get("facade", table_name.startswith("facade_"))),
                write_kind=write_kind,
                write_reference=write_reference,
                write_pdu_address=write_pdu_address,
                injects_tag=signal_raw.get("injects_tag"),
                injection_group=signal_raw.get("injection_group"),
            )
            if tag in signals_by_tag:
                raise ValueError(f"Tag duplicado en mapa Modbus: {tag}")
            signals_by_tag[tag] = signal
            table_signals.append(signal)

        tables[table_name] = TableDefinition(
            name=table_name,
            label=str(table_raw.get("label", table_name)),
            kind=kind,
            start_ref=start_ref,
            start_pdu=start_pdu,
            count=count,
            writable=table_writable,
            data_type=data_type,
            optional=optional,
            signals=table_signals,
        )

    return AppConfig(
        project=raw.get("project", {}),
        server=server,
        controller=controller,
        polling=polling,
        runtime=runtime,
        addressing_mode=addressing_mode,
        tables=tables,
        signals_by_tag=signals_by_tag,
        raw=raw,
    )
