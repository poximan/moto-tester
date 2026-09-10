from __future__ import annotations

import json
import math
from copy import deepcopy
from contextlib import contextmanager
import logging
from logging.handlers import RotatingFileHandler
from moto_time import PresentationFormatter
import os
import threading
from moto_time import clock
import urllib.error
import urllib.request
from pathlib import Path
from typing import Any, Literal

from fastapi import FastAPI, HTTPException, Query
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel, Field

from .history import LevelHistoryStore
from .simulation import daily_consumption_pct, seasonal_inlet_pct, simulated_clock


def _resolve_log_dir() -> Path:
    target = Path("/runtime/logs")
    target.mkdir(parents=True, exist_ok=True)
    return target


LOGGER = logging.getLogger("field-emulator")
_LOG_PATH: Path | None = None


def configure_logging() -> None:
    global _LOG_PATH
    _LOG_PATH = _resolve_log_dir() / "field-emulator.log"
    LOGGER.setLevel(logging.INFO)
    if not any(isinstance(handler, logging.FileHandler) and Path(handler.baseFilename) == _LOG_PATH
               for handler in LOGGER.handlers):
        handler = RotatingFileHandler(_LOG_PATH, maxBytes=10_000_000, backupCount=3, encoding="utf-8")
        handler.setFormatter(PresentationFormatter(
            "%(asctime)s.%(msecs)03d %(levelname)s [%(name)s] %(message)s",
            datefmt="%Y-%m-%d %H:%M:%S",
        ))
        LOGGER.addHandler(handler)
    LOGGER.propagate = True


def _required(name: str) -> str:
    value = os.environ.get(name, "").strip()
    if not value:
        raise ValueError(f"Falta configuracion obligatoria: {name}")
    return value


def _env_float(name: str) -> float:
    value = float(_required(name))
    if not math.isfinite(value) or value < 0:
        raise ValueError(f"Configuracion numerica invalida: {name}")
    return value


def _env_int(name: str) -> int:
    value = int(_required(name))
    if value <= 0:
        raise ValueError(f"Configuracion debe ser positiva: {name}")
    return value


def _clamp(value: float, lower: float, upper: float) -> float:
    lo = min(lower, upper)
    hi = max(lower, upper)
    return max(lo, min(hi, value))


class ValveBody(BaseModel):
    inlet_open_pct: float | None = Field(default=None, ge=0, le=100)
    outlet_open_pct: float | None = Field(default=None, ge=0, le=100)


class ControlBody(ValveBody):
    mode: Literal["manual", "automatic"] | None = None
    season_position_pct: float | None = Field(default=None, ge=0, le=100)


class FieldEmulator:
    def __init__(self, time_provider=clock) -> None:
        self.clock = time_provider
        self.api_url = _required("TESTER_API_URL").rstrip("/")
        self.internal_token = _required("INTERNAL_EMULATOR_TOKEN")
        self.interval_ms = _env_int("FIELD_EMULATOR_INTERVAL_MS")
        self.pump_rate = _env_float("FIELD_EMULATOR_PUMP_RATE_PER_S")
        # El consumo maximo equivale a 3,8 bombas. Cuatro bombas superan
        # el pico por un 5% sin que el emulador decida cuales deben arrancar.
        self.consumption_rate = _env_float(
            "FIELD_EMULATOR_CONSUMPTION_RATE_PER_S"
        )
        self.inlet_rate = _env_float("FIELD_EMULATOR_INLET_RATE_PER_S")
        self.state_path = Path(os.getenv("FIELD_EMULATOR_STATE_FILE", "/runtime/field_emulator_state.json"))
        self.history = LevelHistoryStore(
            Path(os.getenv("FIELD_EMULATOR_HISTORY_FILE", "/runtime/field_emulator_level_history.csv")),
            sample_interval_s=_env_float("FIELD_EMULATOR_HISTORY_INTERVAL_S"),
            time_provider=self.clock,
            retention_simulated_days=_env_int("FIELD_EMULATOR_HISTORY_SIMULATED_DAYS"),
        )
        self._lock = threading.RLock()
        self._stop = threading.Event()
        self._thread: threading.Thread | None = None
        self._last_tick = self.clock.monotonic_seconds()
        self._consecutive_api_errors = 0
        self._last_plc_connected: bool | None = None
        self.state: dict[str, Any] = self._initial_state()
        self._load_state_file()
        LOGGER.info(
            "field emulator init api_url=%s interval_ms=%s inlet_rate=%s consumption_rate=%s pump_rate=%s state_file=%s history_file=%s",
            self.api_url,
            self.interval_ms,
            self.inlet_rate,
            self.consumption_rate,
            self.pump_rate,
            self.state_path,
            self.history.path,
        )

    def _initial_state(self) -> dict[str, Any]:
        inlet = _env_float("FIELD_EMULATOR_INLET_OPEN_PCT")
        outlet = _env_float("FIELD_EMULATOR_OUTLET_OPEN_PCT")
        season = _env_float("FIELD_EMULATOR_SEASON_POSITION_PCT")
        if any(value > 100 for value in (inlet, outlet, season)):
            raise ValueError("Porcentajes iniciales fuera de rango")
        return {
            "control_mode": "manual",
            "season_position_pct": season,
            "manual_inlet_open_pct": inlet,
            "manual_outlet_open_pct": outlet,
            "inlet_open_pct": inlet,
            "outlet_open_pct": outlet,
            "yNvCamAsp": None,
            "yNvRes": None,
            "pump_count": 0,
            "bounds": {},
            "last_snapshot_at": None,
            "last_write_at": None,
            "last_write_values": {},
            "last_error": None,
            "updated_at": self.clock.epoch_seconds(),
        }

    def _load_state_file(self) -> None:
        if not self.state_path.exists():
            return
        raw = json.loads(self.state_path.read_text(encoding="utf-8"))
        expected = set(self._persisted_state())
        if not isinstance(raw, dict) or set(raw) != expected:
            raise ValueError(f"Contrato de estado invalido: {self.state_path}")
        if raw["control_mode"] not in {"manual", "automatic"}:
            raise ValueError("Modo de emulador invalido")
        for key in expected - {"control_mode"}:
            value = raw[key]
            if key in {"yNvCamAsp", "yNvRes"} and value is None:
                continue
            if isinstance(value, bool) or not isinstance(value, (int, float)) or not math.isfinite(value):
                raise ValueError(f"Estado de emulador invalido: {key}")
            if key.endswith("pct") and not 0 <= value <= 100:
                raise ValueError(f"Porcentaje fuera de rango: {key}")
        self.state.update(raw)

    def _persisted_state(self) -> dict[str, Any]:
        keys = ("control_mode", "season_position_pct", "manual_inlet_open_pct",
                "manual_outlet_open_pct", "inlet_open_pct", "outlet_open_pct", "yNvCamAsp", "yNvRes")
        return {key: self.state[key] for key in keys}

    @contextmanager
    def _state_change(self):
        previous = deepcopy(self.state)
        try:
            yield
        except Exception:
            self.state = previous
            raise

    def _save_state_file(self) -> None:
        self.state_path.parent.mkdir(parents=True, exist_ok=True)
        tmp = self.state_path.with_suffix(".json.tmp")
        with tmp.open("w", encoding="utf-8") as handle:
            json.dump(self._persisted_state(), handle, indent=2, allow_nan=False)
            handle.flush()
            os.fsync(handle.fileno())
        tmp.replace(self.state_path)

    def start(self) -> None:
        if self._thread and self._thread.is_alive():
            return
        LOGGER.info("field emulator start")
        self._thread = threading.Thread(target=self._run, name="field-emulator", daemon=True)
        self._thread.start()

    def stop(self) -> None:
        LOGGER.info("field emulator stop")
        self._stop.set()
        if self._thread:
            self._thread.join(timeout=3)

    def snapshot(self) -> dict[str, Any]:
        with self._lock:
            self._apply_control(self.clock.epoch_seconds())
            return {
                **self.state,
                "api_url": self.api_url,
                "interval_ms": self.interval_ms,
                "rates": {
                    "inlet_per_s": self.inlet_rate,
                    "consumption_per_s": self.consumption_rate,
                    "pump_per_s": self.pump_rate,
                },
                "history": self.history.metadata(),
            }

    def set_valves(self, body: ValveBody) -> dict[str, Any]:
        LOGGER.info("valve request inlet=%s outlet=%s", body.inlet_open_pct, body.outlet_open_pct)
        with self._lock, self._state_change():
            if body.inlet_open_pct is not None:
                self.state["manual_inlet_open_pct"] = _clamp(float(body.inlet_open_pct), 0, 100)
            if body.outlet_open_pct is not None:
                self.state["manual_outlet_open_pct"] = _clamp(float(body.outlet_open_pct), 0, 100)
            self._apply_control(self.clock.epoch_seconds())
            self.state["updated_at"] = self.clock.epoch_seconds()
            self._save_state_file()
            return self.snapshot()

    def set_control(self, body: ControlBody) -> dict[str, Any]:
        LOGGER.info(
            "control request mode=%s season=%s inlet=%s outlet=%s",
            body.mode,
            body.season_position_pct,
            body.inlet_open_pct,
            body.outlet_open_pct,
        )
        with self._lock, self._state_change():
            if body.mode is not None:
                self.state["control_mode"] = body.mode
            if body.season_position_pct is not None:
                self.state["season_position_pct"] = float(body.season_position_pct)
            if body.inlet_open_pct is not None:
                self.state["manual_inlet_open_pct"] = float(body.inlet_open_pct)
            if body.outlet_open_pct is not None:
                self.state["manual_outlet_open_pct"] = float(body.outlet_open_pct)
            self._apply_control(self.clock.epoch_seconds())
            self.state["updated_at"] = self.clock.epoch_seconds()
            self._save_state_file()
            return self.snapshot()

    def _apply_control(self, now: float) -> None:
        clock = simulated_clock(now)
        mode = self.state["control_mode"]
        if mode == "automatic":
            inlet = seasonal_inlet_pct(float(self.state["season_position_pct"]))
            outlet = daily_consumption_pct(clock.hour, clock.day_index)
        else:
            inlet = float(self.state["manual_inlet_open_pct"])
            outlet = float(self.state["manual_outlet_open_pct"])
        self.state["inlet_open_pct"] = _clamp(inlet, 0, 100)
        self.state["outlet_open_pct"] = _clamp(outlet, 0, 100)
        self.state["simulated_clock"] = clock.as_dict()

    def _run(self) -> None:
        while not self._stop.is_set():
            try:
                self._tick()
                if self._consecutive_api_errors:
                    LOGGER.info("field emulator api recovered after %s failed ticks", self._consecutive_api_errors)
                self._consecutive_api_errors = 0
            except urllib.error.HTTPError as exc:
                try:
                    payload = json.loads(exc.read().decode("utf-8"))
                    detail = payload.get("detail", str(exc)) if isinstance(payload, dict) else str(payload)
                except (json.JSONDecodeError, UnicodeDecodeError):
                    detail = str(exc)
                self._record_api_error(f"HTTP {exc.code}: {detail}")
            except (urllib.error.URLError, TimeoutError, ConnectionRefusedError) as exc:
                self._record_api_error(str(exc))
            except Exception as exc:  # noqa: BLE001
                LOGGER.exception("field emulator tick error: %s", exc)
                with self._lock:
                    self.state["last_error"] = f"{type(exc).__name__}: {exc}"
                    self.state["updated_at"] = self.clock.epoch_seconds()
            self.clock.sleep(max(self.interval_ms / 1000.0, 0.1))

    def _record_api_error(self, error: str) -> None:
        self._consecutive_api_errors += 1
        if self._consecutive_api_errors in {1, 2, 3} or self._consecutive_api_errors % 30 == 0:
            LOGGER.warning(
                "field emulator api error api_url=%s error=%s consecutive=%s",
                self.api_url,
                error,
                self._consecutive_api_errors,
            )
        with self._lock:
            self.state["last_error"] = f"API no disponible: {error}"
            self.state["updated_at"] = self.clock.epoch_seconds()

    def _get_json(self, path: str) -> dict[str, Any]:
        req = urllib.request.Request(f"{self.api_url}{path}", method="GET")
        with urllib.request.urlopen(req, timeout=5) as response:  # noqa: S310 - URL de servicio declarada en despliegue
            return json.loads(response.read().decode("utf-8"))

    def _post_json(self, path: str, payload: dict[str, Any]) -> dict[str, Any]:
        data = json.dumps(payload).encode("utf-8")
        req = urllib.request.Request(
            f"{self.api_url}{path}",
            data=data,
            method="POST",
            headers={
                "Content-Type": "application/json",
                "X-Internal-Emulator-Token": self.internal_token,
            },
        )
        with urllib.request.urlopen(req, timeout=5) as response:  # noqa: S310
            return json.loads(response.read().decode("utf-8"))

    def _tick(self) -> None:
        now = self.clock.epoch_seconds()
        tick = self.clock.monotonic_seconds()
        dt = _clamp(tick - self._last_tick, 0.0, 5.0)
        self._last_tick = tick
        snap = self._get_json("/api/snapshot")
        values = snap["values"]
        injection_enabled = snap["injection_mode"]["enabled"]
        plc_connected = snap["connection"]["connected"]
        if not isinstance(injection_enabled, bool) or not isinstance(plc_connected, bool):
            raise ValueError("Snapshot con modos invalidos")
        if not plc_connected:
            raise ValueError("PLC desconectado; emulacion pausada")
        required_tags = ["gCamFn", "gCamRb", "gResFn", "gResSp", "eNvCamAsp", "eNvRes"]
        required_tags += [f"bB{idx}EMar" for idx in range(1, 6)]
        confirmed = {}
        for tag in required_tags:
            signal = values.get(tag)
            if not isinstance(signal, dict) or signal.get("quality") != "good":
                raise ValueError(f"Senal no confirmada o vencida: {tag}")
            value = signal.get("value")
            if not isinstance(value, (int, float)) or not math.isfinite(value):
                raise ValueError(f"Senal invalida: {tag}")
            if tag.startswith("b") and value not in (0, 1):
                raise ValueError(f"Senal digital invalida: {tag}")
            confirmed[tag] = value
        pump_count = sum(bool(confirmed[f"bB{idx}EMar"]) for idx in range(1, 6))

        if plc_connected != self._last_plc_connected:
            if plc_connected:
                LOGGER.info("PLC connection recovered; field writes resumed")
            else:
                LOGGER.warning("PLC disconnected; field writes paused")
            self._last_plc_connected = plc_connected

        with self._lock, self._state_change():
            self._apply_control(now)
            cam_previous = self.state.get("yNvCamAsp")
            res_previous = self.state.get("yNvRes")
            inlet_open = float(self.state["inlet_open_pct"])
            outlet_open = float(self.state["outlet_open_pct"])
            self.state["injection_enabled"] = injection_enabled

        cam_floor = confirmed["gCamFn"]
        cam_ceiling = confirmed["gCamRb"]
        res_floor = confirmed["gResFn"]
        res_ceiling = confirmed["gResSp"]

        if cam_floor >= cam_ceiling or res_floor >= res_ceiling:
            raise ValueError("Limites de nivel inconsistentes; emulacion pausada")

        if not injection_enabled:
            with self._lock, self._state_change():
                self.state.update(
                    {
                        "yNvCamAsp": None,
                        "yNvRes": None,
                        "pump_count": pump_count,
                        "bounds": {
                            "yNvCamAsp": {"floor": cam_floor, "ceiling": cam_ceiling},
                            "yNvRes": {"floor": res_floor, "ceiling": res_ceiling},
                        },
                        "last_snapshot_at": snap.get("timestamp"),
                        "last_error": None if plc_connected else "PLC desconectado; emulacion pausada",
                        "updated_at": self.clock.epoch_seconds(),
                    }
                )
                self._save_state_file()
            if plc_connected:
                chamber_read = confirmed["eNvCamAsp"]
                reserve_read = confirmed["eNvRes"]
                self.history.record(now, chamber_read, reserve_read)
            return

        # Las y* son solo area de escritura hacia el controlador. Para iniciar o
        # re-sincronizar el modelo se toma feedback genuino e*/b*, nunca la
        # memoria y* reservada para inyeccion.
        cam = confirmed["eNvCamAsp"] if cam_previous is None else float(cam_previous)
        res = confirmed["eNvRes"] if res_previous is None else float(res_previous)

        pumped_flow = pump_count * self.pump_rate
        consumption_flow = (outlet_open / 100.0) * self.consumption_rate
        cam = _clamp(
            cam + ((inlet_open / 100.0) * self.inlet_rate - pumped_flow) * dt,
            cam_floor,
            cam_ceiling,
        )
        res = _clamp(
            res + (pumped_flow - consumption_flow) * dt,
            res_floor,
            res_ceiling,
        )

        write_values = {
            "yNvCamAsp": int(round(cam)),
            "yNvRes": int(round(res)),
        }
        write_response = self._post_json(
            "/api/injection",
            {"values": write_values, "source": "field-emulator"},
        )

        if write_response.get("errors") or write_response.get("ok") is False:
            raise ValueError("El controlador rechazo la inyeccion")

        with self._lock, self._state_change():
            self.state.update(
                {
                    "yNvCamAsp": write_values["yNvCamAsp"],
                    "yNvRes": write_values["yNvRes"],
                    "last_write_values": write_values,
                    "last_write_results": write_response.get("results", {}),
                    "last_write_errors": {},
                    "pump_count": pump_count,
                    "bounds": {
                        "yNvCamAsp": {"floor": cam_floor, "ceiling": cam_ceiling},
                        "yNvRes": {"floor": res_floor, "ceiling": res_ceiling},
                    },
                    "last_snapshot_at": snap.get("timestamp"),
                    "last_write_at": self.clock.epoch_seconds(),
                    "last_error": None,
                    "updated_at": self.clock.epoch_seconds(),
                }
            )
            self._save_state_file()
        self.history.record(
            now,
            confirmed["eNvCamAsp"],
            confirmed["eNvRes"],
        )


emulator: FieldEmulator | None = None
app = FastAPI(title="Field Emulator", version="0.1.0")
app.add_middleware(CORSMiddleware, allow_origins=["*"], allow_methods=["*"], allow_headers=["*"])


@app.on_event("startup")
def startup() -> None:
    global emulator
    configure_logging()
    emulator = FieldEmulator()
    emulator.start()


@app.on_event("shutdown")
def shutdown() -> None:
    if emulator is not None:
        emulator.stop()


@app.get("/health")
def health() -> dict[str, Any]:
    snap = emulator.snapshot()
    return {"ok": True, "last_error": snap["last_error"], "injection_enabled": snap.get("injection_enabled")}


@app.get("/state")
def state() -> dict[str, Any]:
    return emulator.snapshot()


@app.put("/valves")
def valves(body: ValveBody) -> dict[str, Any]:
    try:
        return emulator.set_valves(body)
    except (urllib.error.URLError, TimeoutError) as exc:
        raise HTTPException(status_code=502, detail=str(exc)) from exc


@app.put("/control")
def control(body: ControlBody) -> dict[str, Any]:
    return emulator.set_control(body)


@app.get("/history")
def history(max_points: int = Query(default=2400, ge=2, le=25_000)) -> dict[str, Any]:
    return emulator.history.snapshot(max_points=max_points)

@app.get("/api/v1/logs")
def logs() -> dict[str, Any]:
    from collections import deque
    with _LOG_PATH.open(encoding="utf-8") as handle:
        return {"name": "field-emulator", "lines": [line.rstrip("\n") for line in deque(handle, maxlen=300)]}
