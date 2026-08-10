from __future__ import annotations

import json
import logging
import os
import threading
import time
import urllib.error
import urllib.request
from pathlib import Path
from typing import Any

from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel, Field


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


class PumpEmarBody(BaseModel):
    enabled: bool


class FieldEmulator:
    def __init__(self) -> None:
        self.api_url = os.getenv("TESTER_API_URL", "http://trasvase-tester:8080").rstrip("/")
        self.internal_token = os.environ["INTERNAL_EMULATOR_TOKEN"]
        self.interval_ms = _env_int("FIELD_EMULATOR_INTERVAL_MS", 1000)
        self.inlet_rate = _env_float("FIELD_EMULATOR_INLET_RATE_PER_S", 90.0)
        self.pump_rate = _env_float("FIELD_EMULATOR_PUMP_RATE_PER_S", 12.0)
        # Salida a 100% = 6 bombas-equivalentes. Así, con 3 bombas en marcha
        # y válvula de reserva al 50%, el caudal de salida empata el ingreso.
        self.outlet_rate = _env_float("FIELD_EMULATOR_OUTLET_RATE_PER_S", self.pump_rate * 6.0)
        self.state_path = Path(os.getenv("FIELD_EMULATOR_STATE_FILE", "/runtime/field_emulator_state.json"))
        self._lock = threading.RLock()
        self._stop = threading.Event()
        self._thread: threading.Thread | None = None
        self._last_tick = time.time()
        self._consecutive_api_errors = 0
        self.state: dict[str, Any] = self._initial_state()
        self._load_state_file()
        LOGGER.info(
            "field emulator init api_url=%s interval_ms=%s inlet_rate=%s outlet_rate=%s pump_rate=%s state_file=%s",
            self.api_url,
            self.interval_ms,
            self.inlet_rate,
            self.outlet_rate,
            self.pump_rate,
            self.state_path,
        )

    def _initial_state(self) -> dict[str, Any]:
        return {
            "inlet_open_pct": _env_float("FIELD_EMULATOR_INLET_OPEN_PCT", 0.0),
            "outlet_open_pct": _env_float("FIELD_EMULATOR_OUTLET_OPEN_PCT", 0.0),
            "yNvCamAsp": None,
            "yNvRes": None,
            "generate_emar": {str(pump): False for pump in range(1, 6)},
            "last_emar_values": {},
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
                for key in ["inlet_open_pct", "outlet_open_pct", "yNvCamAsp", "yNvRes"]:
                    if key in raw:
                        self.state[key] = raw[key]
                generate_emar = raw.get("generate_emar")
                if isinstance(generate_emar, dict):
                    expected = {str(pump) for pump in range(1, 6)}
                    if set(generate_emar) != expected or not all(isinstance(value, bool) for value in generate_emar.values()):
                        raise ValueError("generate_emar debe contener booleanos para las bombas 1..5")
                    self.state["generate_emar"] = generate_emar
        except Exception as exc:  # noqa: BLE001
            self.state["last_error"] = f"No se pudo leer estado persistido: {exc}"

    def _save_state_file(self) -> None:
        try:
            self.state_path.parent.mkdir(parents=True, exist_ok=True)
            data = {
                "inlet_open_pct": self.state["inlet_open_pct"],
                "outlet_open_pct": self.state["outlet_open_pct"],
                "yNvCamAsp": self.state["yNvCamAsp"],
                "yNvRes": self.state["yNvRes"],
                "generate_emar": self.state["generate_emar"],
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
            return {
                **self.state,
                "api_url": self.api_url,
                "interval_ms": self.interval_ms,
                "rates": {
                    "inlet_per_s": self.inlet_rate,
                    "outlet_per_s": self.outlet_rate,
                    "pump_per_s": self.pump_rate,
                },
            }

    def set_valves(self, body: ValveBody) -> dict[str, Any]:
        LOGGER.info("valve request inlet=%s outlet=%s", body.inlet_open_pct, body.outlet_open_pct)
        with self._lock:
            if body.inlet_open_pct is not None:
                self.state["inlet_open_pct"] = _clamp(float(body.inlet_open_pct), 0, 100)
            if body.outlet_open_pct is not None:
                self.state["outlet_open_pct"] = _clamp(float(body.outlet_open_pct), 0, 100)
            self.state["updated_at"] = time.time()
            self._save_state_file()
            return self.snapshot()

    def set_generate_emar(self, pump_id: int, enabled: bool) -> dict[str, Any]:
        if pump_id < 1 or pump_id > 5:
            raise ValueError("pump_id debe estar entre 1 y 5")
        LOGGER.info("generate EMar request pump=%s enabled=%s", pump_id, enabled)
        with self._lock:
            self.state["generate_emar"][str(pump_id)] = enabled
            self.state["last_emar_values"].pop(f"yB{pump_id}EMar", None)
            self.state["updated_at"] = time.time()
            self._save_state_file()
            return self.snapshot()

    def _run(self) -> None:
        while not self._stop.is_set():
            try:
                self._tick()
                if self._consecutive_api_errors:
                    LOGGER.info("field emulator api recovered after %s failed ticks", self._consecutive_api_errors)
                self._consecutive_api_errors = 0
            except (urllib.error.URLError, TimeoutError, ConnectionRefusedError) as exc:
                self._consecutive_api_errors += 1
                # Durante arranque Docker es normal que el servicio web todavía
                # no acepte conexiones aunque DNS ya resuelva el nombre del
                # contenedor. No volcamos stack trace para este caso esperado.
                if self._consecutive_api_errors in {1, 2, 3} or self._consecutive_api_errors % 30 == 0:
                    LOGGER.warning(
                        "field emulator api not ready api_url=%s error=%s consecutive=%s",
                        self.api_url,
                        exc,
                        self._consecutive_api_errors,
                    )
                with self._lock:
                    self.state["last_error"] = f"API no disponible: {exc}"
                    self.state["updated_at"] = time.time()
            except Exception as exc:  # noqa: BLE001
                LOGGER.exception("field emulator tick error: %s", exc)
                with self._lock:
                    self.state["last_error"] = f"{type(exc).__name__}: {exc}"
                    self.state["updated_at"] = time.time()
            time.sleep(max(self.interval_ms / 1000.0, 0.1))

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
        pump_count = sum(1 for idx in range(1, 6) if _bit(values.get(f"bB{idx}EMar")))

        with self._lock:
            cam_previous = self.state.get("yNvCamAsp")
            res_previous = self.state.get("yNvRes")
            inlet_open = float(self.state["inlet_open_pct"])
            outlet_open = float(self.state["outlet_open_pct"])
            generate_emar = dict(self.state["generate_emar"])
            last_emar_values = dict(self.state["last_emar_values"])
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
                        "last_error": None,
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

        cam = _clamp(cam + (inlet_open / 100.0) * self.inlet_rate * dt - pump_count * self.pump_rate * dt, cam_floor, cam_ceiling)
        res = _clamp(res + pump_count * self.pump_rate * dt - (outlet_open / 100.0) * self.outlet_rate * dt, res_floor, res_ceiling)

        write_values = {
            "yNvCamAsp": int(round(cam)),
            "yNvRes": int(round(res)),
        }
        for pump_id in range(1, 6):
            tag = f"yB{pump_id}EMar"
            if generate_emar[str(pump_id)]:
                next_value = _bit(values.get(f"bB{pump_id}Arndo"))
                if last_emar_values.get(tag) != next_value:
                    write_values[tag] = next_value
        # Escritura simétrica e independiente: la válvula de ingreso gobierna
        # yNvCamAsp y la válvula de salida gobierna yNvRes. Se envía cada tag
        # por separado para que una falla puntual no oculte cuál variable no se
        # pudo escribir.
        write_results: dict[str, Any] = {}
        write_errors: dict[str, str] = {}
        for tag, value in write_values.items():
            try:
                LOGGER.info("field write request tag=%s value=%s", tag, value)
                write_results[tag] = self._post_json(
                    "/api/injection",
                    {"values": {tag: value}, "source": "field-emulator"},
                )
                LOGGER.info("field write queued tag=%s value=%s result=%s", tag, value, write_results[tag])
            except Exception as exc:  # noqa: BLE001 - queremos registrar el tag exacto que falló
                LOGGER.exception("field write error tag=%s value=%s error=%s", tag, value, exc)
                write_errors[tag] = f"{type(exc).__name__}: {exc}"

        with self._lock:
            self.state.update(
                {
                    "yNvCamAsp": write_values["yNvCamAsp"],
                    "yNvRes": write_values["yNvRes"],
                    "last_write_values": write_values,
                    "last_write_results": write_results,
                    "last_write_errors": write_errors,
                    "pump_count": pump_count,
                    "bounds": {
                        "yNvCamAsp": {"floor": cam_floor, "ceiling": cam_ceiling},
                        "yNvRes": {"floor": res_floor, "ceiling": res_ceiling},
                    },
                    "last_snapshot_at": snap.get("timestamp"),
                    "last_write_at": time.time(),
                    "last_error": "; ".join(f"{tag}: {err}" for tag, err in write_errors.items()) if write_errors else None,
                    "updated_at": time.time(),
                }
            )
            for tag, value in write_values.items():
                if tag.startswith("yB") and tag.endswith("EMar") and tag not in write_errors:
                    self.state["last_emar_values"][tag] = value
            self._save_state_file()


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


@app.put("/pumps/{pump_id}/generate-emar")
def generate_emar(pump_id: int, body: PumpEmarBody) -> dict[str, Any]:
    try:
        return emulator.set_generate_emar(pump_id, body.enabled)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
