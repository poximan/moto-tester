from __future__ import annotations

import json
import logging
import os
import threading
import time
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
    preferred = Path(os.getenv("LOG_DIR", "/runtime/logs"))
    try:
        preferred.mkdir(parents=True, exist_ok=True)
        return preferred
    except OSError:
        fallback = Path.cwd() / "runtime" / "logs"
        fallback.mkdir(parents=True, exist_ok=True)
        return fallback


LOG_DIR = _resolve_log_dir()
LOGGER = logging.getLogger("field-emulator")
LOGGER.setLevel(logging.INFO)
_LOG_PATH = LOG_DIR / "field-emulator.log"
if not any(isinstance(h, logging.FileHandler) and Path(h.baseFilename) == _LOG_PATH for h in LOGGER.handlers):
    _handler = logging.FileHandler(_LOG_PATH, encoding="utf-8")
    _handler.setFormatter(
        logging.Formatter(
            "%(asctime)s.%(msecs)03d %(levelname)s [%(name)s] %(message)s",
            datefmt="%Y-%m-%d %H:%M:%S",
        )
    )
    LOGGER.addHandler(_handler)
LOGGER.propagate = True


def _env_bool(name: str, default: bool) -> bool:
    raw = os.getenv(name)
    if raw is None or raw == "":
        return default
    return raw.strip().lower() in {"1", "true", "yes", "y", "on", "si", "sí"}


def _env_float(name: str, default: float) -> float:
    raw = os.getenv(name)
    if raw is None or raw == "":
        return default
    return float(raw)


def _env_int(name: str, default: int) -> int:
    raw = os.getenv(name)
    if raw is None or raw == "":
        return default
    return int(raw)


def _clamp(value: float, lower: float, upper: float) -> float:
    lo = min(lower, upper)
    hi = max(lower, upper)
    return max(lo, min(hi, value))


def _num(value: Any, fallback: float) -> float:
    try:
        if isinstance(value, dict):
            value = value.get("value")
        if value is None:
            return fallback
        return float(value)
    except (TypeError, ValueError):
        return fallback


def _bit(value: Any) -> bool:
    if isinstance(value, dict):
        value = value.get("value")
    if isinstance(value, bool):
        return value
    if isinstance(value, (int, float)):
        return value != 0
    if isinstance(value, str):
        return value.strip().lower() in {"1", "true", "on", "yes", "si", "sí"}
    return False


class ValveBody(BaseModel):
    inlet_open_pct: float | None = Field(default=None, ge=0, le=100)
    outlet_open_pct: float | None = Field(default=None, ge=0, le=100)


class ControlBody(ValveBody):
    mode: Literal["manual", "automatic"] | None = None
    season_position_pct: float | None = Field(default=None, ge=0, le=100)


class FieldEmulator:
    def __init__(self) -> None:
        self.api_url = os.getenv("TESTER_API_URL", "http://trasvase-tester:8080").rstrip("/")
        self.internal_token = os.environ["INTERNAL_EMULATOR_TOKEN"]
        self.interval_ms = _env_int("FIELD_EMULATOR_INTERVAL_MS", 1000)
        self.pump_rate = _env_float("FIELD_EMULATOR_PUMP_RATE_PER_S", 12.0)
        # El consumo maximo equivale a 3,8 bombas. Cuatro bombas superan
        # el pico por un 5% sin que el emulador decida cuales deben arrancar.
        self.consumption_rate = _env_float(
            "FIELD_EMULATOR_CONSUMPTION_RATE_PER_S",
            self.pump_rate * 3.8,
        )
        self.inlet_rate = _env_float("FIELD_EMULATOR_INLET_RATE_PER_S", 45.0)
        self.state_path = Path(os.getenv("FIELD_EMULATOR_STATE_FILE", "/runtime/field_emulator_state.json"))
        self.history = LevelHistoryStore(
            Path(os.getenv("FIELD_EMULATOR_HISTORY_FILE", "/runtime/field_emulator_level_history.csv")),
            sample_interval_s=_env_float("FIELD_EMULATOR_HISTORY_INTERVAL_S", 30.0),
            retention_simulated_days=_env_int("FIELD_EMULATOR_HISTORY_SIMULATED_DAYS", 180),
        )
        self._lock = threading.RLock()
        self._stop = threading.Event()
        self._thread: threading.Thread | None = None
        self._last_tick = time.time()
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
        inlet = _env_float("FIELD_EMULATOR_INLET_OPEN_PCT", 0.0)
        outlet = _env_float("FIELD_EMULATOR_OUTLET_OPEN_PCT", 0.0)
        return {
            "control_mode": "manual",
            "season_position_pct": _env_float("FIELD_EMULATOR_SEASON_POSITION_PCT", 50.0),
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
            "updated_at": time.time(),
        }

    def _load_state_file(self) -> None:
        try:
            if self.state_path.exists():
                raw = json.loads(self.state_path.read_text(encoding="utf-8"))
                for key in [
                    "control_mode",
                    "season_position_pct",
                    "manual_inlet_open_pct",
                    "manual_outlet_open_pct",
                    "inlet_open_pct",
                    "outlet_open_pct",
                    "yNvCamAsp",
                    "yNvRes",
                ]:
                    if key in raw:
                        self.state[key] = raw[key]
                # Migración transparente del estado anterior, que sólo tenía
                # las aperturas efectivas.
                if "manual_inlet_open_pct" not in raw:
                    self.state["manual_inlet_open_pct"] = self.state["inlet_open_pct"]
                if "manual_outlet_open_pct" not in raw:
                    self.state["manual_outlet_open_pct"] = self.state["outlet_open_pct"]
        except Exception as exc:  # noqa: BLE001
            self.state["last_error"] = f"No se pudo leer estado persistido: {exc}"

    def _save_state_file(self) -> None:
        try:
            self.state_path.parent.mkdir(parents=True, exist_ok=True)
            data = {
                "control_mode": self.state["control_mode"],
                "season_position_pct": self.state["season_position_pct"],
                "manual_inlet_open_pct": self.state["manual_inlet_open_pct"],
                "manual_outlet_open_pct": self.state["manual_outlet_open_pct"],
                "inlet_open_pct": self.state["inlet_open_pct"],
                "outlet_open_pct": self.state["outlet_open_pct"],
                "yNvCamAsp": self.state["yNvCamAsp"],
                "yNvRes": self.state["yNvRes"],
            }
            tmp = self.state_path.with_suffix(".json.tmp")
            tmp.write_text(json.dumps(data, indent=2), encoding="utf-8")
            tmp.replace(self.state_path)
        except Exception as exc:  # noqa: BLE001
            self.state["last_error"] = f"No se pudo persistir estado: {exc}"

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
            self._apply_control(time.time())
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
        with self._lock:
            if body.inlet_open_pct is not None:
                self.state["manual_inlet_open_pct"] = _clamp(float(body.inlet_open_pct), 0, 100)
            if body.outlet_open_pct is not None:
                self.state["manual_outlet_open_pct"] = _clamp(float(body.outlet_open_pct), 0, 100)
            self._apply_control(time.time())
            self.state["updated_at"] = time.time()
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
        with self._lock:
            if body.mode is not None:
                self.state["control_mode"] = body.mode
            if body.season_position_pct is not None:
                self.state["season_position_pct"] = float(body.season_position_pct)
            if body.inlet_open_pct is not None:
                self.state["manual_inlet_open_pct"] = float(body.inlet_open_pct)
            if body.outlet_open_pct is not None:
                self.state["manual_outlet_open_pct"] = float(body.outlet_open_pct)
            self._apply_control(time.time())
            self.state["updated_at"] = time.time()
            self._save_state_file()
            return self.snapshot()

    def _apply_control(self, now: float) -> None:
        clock = simulated_clock(now)
        mode = self.state.get("control_mode", "manual")
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
                    self.state["updated_at"] = time.time()
            time.sleep(max(self.interval_ms / 1000.0, 0.1))

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
            self.state["updated_at"] = time.time()

    def _get_json(self, path: str) -> dict[str, Any]:
        req = urllib.request.Request(f"{self.api_url}{path}", method="GET")
        with urllib.request.urlopen(req, timeout=5) as response:  # noqa: S310 - trusted service URL from deployment env
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
        now = time.time()
        dt = _clamp(now - self._last_tick, 0.1, 5.0)
        self._last_tick = now
        snap = self._get_json("/api/snapshot")
        values = snap.get("values", {})
        injection_enabled = bool(snap.get("injection_mode", {}).get("enabled"))
        plc_connected = bool(snap.get("connection", {}).get("connected"))
        pump_count = sum(1 for idx in range(1, 6) if _bit(values.get(f"bB{idx}EMar")))

        if plc_connected != self._last_plc_connected:
            if plc_connected:
                LOGGER.info("PLC connection recovered; field writes resumed")
            else:
                LOGGER.warning("PLC disconnected; field writes paused")
            self._last_plc_connected = plc_connected

        with self._lock:
            self._apply_control(now)
            cam_previous = self.state.get("yNvCamAsp")
            res_previous = self.state.get("yNvRes")
            inlet_open = float(self.state["inlet_open_pct"])
            outlet_open = float(self.state["outlet_open_pct"])
            self.state["injection_enabled"] = injection_enabled

        cam_floor = _num(values.get("gCamFn"), 0)
        cam_ceiling = _num(values.get("gCamRb"), 4000)
        res_floor = _num(values.get("gResFn"), -1)
        res_ceiling = _num(values.get("gResSp"), 6000)

        if not injection_enabled:
            with self._lock:
                self.state.update(
                    {
                        "pump_count": pump_count,
                        "bounds": {
                            "yNvCamAsp": {"floor": cam_floor, "ceiling": cam_ceiling},
                            "yNvRes": {"floor": res_floor, "ceiling": res_ceiling},
                        },
                        "last_snapshot_at": snap.get("timestamp"),
                        "last_error": None if plc_connected else "PLC desconectado; emulacion pausada",
                        "updated_at": time.time(),
                    }
                )
                self._save_state_file()
            if plc_connected:
                chamber_read = _num(values.get("eNvCamAsp"), _num(cam_previous, cam_floor))
                reserve_read = _num(values.get("eNvRes"), _num(res_previous, res_floor))
                self.history.record(now, chamber_read, reserve_read)
            return

        if not plc_connected:
            with self._lock:
                self.state.update(
                    {
                        "pump_count": pump_count,
                        "last_snapshot_at": snap.get("timestamp"),
                        "last_error": "PLC desconectado; emulacion pausada",
                        "updated_at": time.time(),
                    }
                )
                self._save_state_file()
            return

        # Las y* son solo área de escritura hacia el controlador. Para iniciar o
        # re-sincronizar el modelo se toma feedback genuino e*/b*, nunca la
        # memoria y* reservada para inyección.
        cam = _num(cam_previous, _num(values.get("eNvCamAsp"), cam_floor))
        res = _num(res_previous, _num(values.get("eNvRes"), res_floor))

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

        with self._lock:
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
                    "last_write_at": time.time(),
                    "last_error": None,
                    "updated_at": time.time(),
                }
            )
            self._save_state_file()
        self.history.record(
            now,
            _num(values.get("eNvCamAsp"), float(write_values["yNvCamAsp"])),
            _num(values.get("eNvRes"), float(write_values["yNvRes"])),
        )


emulator = FieldEmulator()
app = FastAPI(title="Field Emulator", version="0.1.0")
app.add_middleware(CORSMiddleware, allow_origins=["*"], allow_methods=["*"], allow_headers=["*"])


@app.on_event("startup")
def startup() -> None:
    emulator.start()


@app.on_event("shutdown")
def shutdown() -> None:
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
