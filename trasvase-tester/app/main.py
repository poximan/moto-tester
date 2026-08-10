from __future__ import annotations

import asyncio
import json
import logging
import urllib.error
import urllib.request
from pathlib import Path
from typing import Any

from fastapi import Depends, FastAPI, HTTPException, Request, WebSocket, WebSocketDisconnect
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles

from .config import AppConfig, load_config
from .auth import RequestAuthenticator
from .control.snapshot_hub import SnapshotHub
from .modbus_client import ModbusPoller, SimulationPoller
from .models import (
    CommandBody,
    EmulatorValveBody,
    FacadeBody,
    GenericWriteBody,
    PollingControlBody,
    PumpCommandBody,
    WriteModeBody,
)
from .polling_control import PollingControlStore
from .state import RuntimeState
from .write_mode import WriteModeStore
from .logging_utils import configure_file_logger, log_dir, tail_file

APP_DIR = Path(__file__).resolve().parent
FRONTEND_DIR = APP_DIR.parent / "frontend"
LOGGER = configure_file_logger("trasvase.web", "trasvase-tester.log")

config: AppConfig = load_config()
write_mode = WriteModeStore(
    interlock_path=config.runtime.write_interlock_file,
    lease_seconds=config.runtime.write_enable_lease_seconds,
)
request_authenticator = RequestAuthenticator(
    config.runtime.edge_auth_verify_url,
    config.runtime.internal_emulator_token,
)
polling_control = PollingControlStore(default_sample_rate_ms=config.polling.interval_ms)
state = RuntimeState(config, write_mode, polling_control)
poller: ModbusPoller | SimulationPoller
if config.runtime.simulation_mode:
    poller = SimulationPoller(config, state)
else:
    poller = ModbusPoller(config, state)

app = FastAPI(
    title="Trasvase Tester",
    version="0.1.0",
    description="Web + master Modbus/TCP para visualizar y probar la frontera de emulación de bombas de trasvase.",
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=False,
    allow_methods=["*"],
    allow_headers=["*"],
)

def require_operator(request: Request) -> None:
    request_authenticator.require_operator(request)


def require_operator_or_emulator(request: Request) -> None:
    request_authenticator.require_operator_or_emulator(request)


def _emulator_request(method: str, path: str, payload: dict[str, Any] | None = None) -> dict[str, Any]:
    url = f"{config.runtime.field_emulator_url.rstrip('/')}{path}"
    data = None if payload is None else json.dumps(payload).encode("utf-8")
    headers = {"Content-Type": "application/json"} if payload is not None else {}
    req = urllib.request.Request(url, data=data, method=method, headers=headers)
    try:
        with urllib.request.urlopen(req, timeout=3) as response:  # noqa: S310 - URL de servicio interno por .env
            return json.loads(response.read().decode("utf-8"))
    except urllib.error.HTTPError as exc:
        detail = exc.read().decode("utf-8", errors="replace")
        raise HTTPException(status_code=exc.code, detail=detail) from exc
    except Exception as exc:  # noqa: BLE001
        raise HTTPException(status_code=502, detail=f"Servicio experto no disponible: {exc}") from exc


def _emulator_state_safe() -> dict[str, Any]:
    try:
        return _emulator_request("GET", "/state")
    except HTTPException as exc:
        return {"last_error": str(exc.detail)}
    except Exception as exc:  # noqa: BLE001
        return {"last_error": f"Servicio experto no disponible: {exc}"}


async def _produce_stream_snapshot() -> dict[str, Any]:
    emulator = await asyncio.to_thread(_emulator_state_safe)
    return {
        "type": "state",
        "snapshot": state.snapshot(),
        "emulator": emulator,
    }


snapshot_hub = SnapshotHub(
    interval_s=max(config.polling.interval_ms / 1000.0, 0.2),
    producer=_produce_stream_snapshot,
)


@app.on_event("startup")
async def on_startup() -> None:
    LOGGER.info("startup web/modbus service")
    poller.start()
    snapshot_hub.start()


@app.on_event("shutdown")
async def on_shutdown() -> None:
    LOGGER.info("shutdown web/modbus service")
    await snapshot_hub.stop()
    poller.stop()


@app.get("/api/health")
def health() -> dict[str, Any]:
    snap = state.snapshot()
    return {
        "ok": True,
        "connected": snap["connection"].get("connected", False),
        "mode": snap["connection"].get("mode"),
        "write_mode": snap["write_mode"].get("mode"),
        "write_enabled": snap["write_mode"].get("write_enabled"),
        "modbus_polling": snap["modbus_polling"],
        "last_error": snap["connection"].get("last_error"),
    }


@app.get("/api/snapshot")
def snapshot() -> dict[str, Any]:
    return state.snapshot()




@app.websocket("/ws/stream")
async def websocket_stream(websocket: WebSocket) -> None:
    await websocket.accept()
    revision = -1
    try:
        while True:
            revision, stream_snapshot = await snapshot_hub.wait_next(revision)
            await websocket.send_json(stream_snapshot)
    except WebSocketDisconnect:
        return


@app.get("/api/config")
def api_config() -> dict[str, Any]:
    return {
        "project": config.project,
        "controller": {
            "host": config.controller.host,
            "port": config.controller.port,
            "unit_id": config.controller.unit_id,
            "timeout_s": config.controller.timeout_s,
        },
        "server": {"host": config.server.host, "port": config.server.port},
        "polling": {
            "interval_ms": config.polling.interval_ms,
            "max_stale_ms": config.polling.max_stale_ms,
        },
        "addressing_mode": config.addressing_mode,
        "write_mode": state.write_mode_snapshot(),
        "modbus_polling": state.polling_control_snapshot(),
        "field_emulator_url": config.runtime.field_emulator_url,
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
                        "row": s.row,
                        "tag": s.tag,
                        "label": s.label,
                        "mapped_value": s.mapped_value,
                        "reference": s.reference,
                        "pdu_address": s.pdu_address,
                        "function_code": s.function_code,
                        "writable": s.writable,
                        "facade": s.facade,
                        "write_kind": s.write_kind,
                        "write_reference": s.write_reference,
                        "write_pdu_address": s.write_pdu_address,
                        "write_function_code": s.write_function_code,
                        "injects_tag": s.injects_tag,
                        "injection_group": s.injection_group,
                        "data_type": s.data_type,
                        "default": s.default,
                    }
                    for s in table.signals
                ],
            }
            for name, table in config.tables.items()
        },
    }


@app.get("/api/events")
def events() -> dict[str, Any]:
    return {"events": state.snapshot()["events"]}


@app.get("/api/diagnostics")
def diagnostics() -> dict[str, Any]:
    snap = state.snapshot()
    return {
        "connection": snap["connection"],
        "write_mode": snap["write_mode"],
        "modbus_polling": snap["modbus_polling"],
        "controller": snap["controller"],
        "log_dir": str(log_dir()),
        "events": snap["events"][:25],
    }


@app.get("/api/logs")
def logs_index() -> dict[str, Any]:
    base = log_dir()
    files = []
    for path in sorted(base.glob("*.log")):
        try:
            stat = path.stat()
        except OSError:
            continue
        files.append(
            {
                "name": path.stem,
                "filename": path.name,
                "path": str(path),
                "size_bytes": stat.st_size,
                "modified_at": stat.st_mtime,
            }
        )
    return {"log_dir": str(base), "files": files}


@app.get("/api/logs/{log_name}")
def logs_read(log_name: str, lines: int = 300) -> dict[str, Any]:
    safe = log_name.replace("/", "").replace("\\", "")
    if safe.endswith(".log"):
        safe = safe[:-4]
    path = log_dir() / f"{safe}.log"
    return {
        "name": safe,
        "filename": path.name,
        "path": str(path),
        "exists": path.exists(),
        "lines": tail_file(path, lines),
    }


@app.get("/api/write-mode")
def get_write_mode() -> dict[str, Any]:
    return state.write_mode_snapshot()


@app.put("/api/write-mode")
def set_write_mode(
    body: WriteModeBody,
    _authorized: None = Depends(require_operator),
) -> dict[str, Any]:
    LOGGER.warning("write_mode request mode=%s source=%s", body.mode, body.source)
    try:
        snapshot = state.set_write_mode(body.mode, source=body.source)
    except PermissionError as exc:
        raise HTTPException(status_code=403, detail=str(exc)) from exc
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    return {"ok": True, **snapshot}


@app.get("/api/modbus-polling")
def get_modbus_polling() -> dict[str, Any]:
    return state.polling_control_snapshot()


@app.put("/api/modbus-polling/{function_code}")
def set_modbus_polling(
    function_code: str,
    body: PollingControlBody,
    _authorized: None = Depends(require_operator),
) -> dict[str, Any]:
    LOGGER.info(
        "polling control request fc=%s enabled=%s sample_rate_ms=%s source=%s",
        function_code,
        body.enabled,
        body.sample_rate_ms,
        body.source,
    )
    try:
        snapshot = state.update_polling_control(
            function_code,
            enabled=body.enabled,
            sample_rate_ms=body.sample_rate_ms,
            source=body.source,
        )
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    return {"ok": True, **snapshot}


@app.post("/api/command")
def command(
    body: CommandBody,
    _authorized: None = Depends(require_operator),
) -> dict[str, Any]:
    signal = config.signals_by_tag.get(body.tag)
    if signal is None:
        raise HTTPException(status_code=404, detail=f"Tag no definido: {body.tag}")
    if signal.table != "digital_commands" or signal.facade:
        raise HTTPException(status_code=400, detail="Este endpoint solo acepta comandos digitales reales cB#")
    try:
        result = state.enqueue_write(body.tag, body.value, source=body.source)
    except PermissionError as exc:
        raise HTTPException(status_code=403, detail=str(exc)) from exc
    except (BufferError, ValueError) as exc:
        raise HTTPException(status_code=409, detail=str(exc)) from exc
    return {"ok": True, "tag": body.tag, "value": body.value, **result}


@app.post("/api/pumps/{pump_id}/command")
def pump_command(
    pump_id: int,
    body: PumpCommandBody,
    _authorized: None = Depends(require_operator),
) -> dict[str, Any]:
    LOGGER.info("pump command pump=%s aut=%s mr=%s source=%s", pump_id, body.aut, body.mr, body.source)
    if pump_id < 1 or pump_id > 5:
        raise HTTPException(status_code=404, detail="pump_id debe estar entre 1 y 5")
    requested: dict[str, bool] = {}
    if body.aut is not None:
        requested[f"cB{pump_id}Aut"] = bool(body.aut)
    if body.mr is not None:
        requested[f"cB{pump_id}Mr"] = bool(body.mr)
    try:
        results = state.enqueue_writes(requested, source=body.source)
    except PermissionError as exc:
        raise HTTPException(status_code=403, detail=str(exc)) from exc
    except (BufferError, ValueError) as exc:
        raise HTTPException(status_code=409, detail=str(exc)) from exc
    return {"ok": True, "pump_id": pump_id, "results": results}


@app.post("/api/write")
def generic_write(
    body: GenericWriteBody,
    _authorized: None = Depends(require_operator),
) -> dict[str, Any]:
    signal = config.signals_by_tag.get(body.tag)
    if signal is None:
        raise HTTPException(status_code=404, detail=f"Tag no definido: {body.tag}")
    if not signal.writable:
        raise HTTPException(status_code=403, detail=f"{body.tag} no está definido como escribible")
    try:
        result = state.enqueue_write(body.tag, body.value, source=body.source)
    except PermissionError as exc:
        raise HTTPException(status_code=403, detail=str(exc)) from exc
    except (BufferError, ValueError) as exc:
        raise HTTPException(status_code=409, detail=str(exc)) from exc
    return {"ok": True, "tag": body.tag, "value": body.value, **result}


def _apply_injection(body: FacadeBody) -> dict[str, Any]:
    LOGGER.info("injection request source=%s values=%s", body.source, body.values)
    for tag in body.values:
        signal = config.signals_by_tag.get(tag)
        if signal is None:
            raise HTTPException(status_code=404, detail=f"Tag de inyección no definido: {tag}")
        if not signal.writable or not signal.facade:
            raise HTTPException(status_code=403, detail=f"{tag} no pertenece a inyección escribible")
    try:
        written = state.enqueue_writes(body.values, source=body.source)
    except PermissionError as exc:
        raise HTTPException(status_code=403, detail=str(exc)) from exc
    except (BufferError, ValueError) as exc:
        raise HTTPException(status_code=409, detail=str(exc)) from exc
    return {"ok": True, "results": written}


@app.post("/api/injection")
def injection(
    body: FacadeBody,
    _authorized: None = Depends(require_operator_or_emulator),
) -> dict[str, Any]:
    return _apply_injection(body)


@app.post("/api/facade")
def facade_compat(
    body: FacadeBody,
    _authorized: None = Depends(require_operator_or_emulator),
) -> dict[str, Any]:
    return _apply_injection(body)


@app.get("/api/emulator/state")
def emulator_state() -> dict[str, Any]:
    return _emulator_request("GET", "/state")


@app.put("/api/emulator/valves")
def emulator_valves(
    body: EmulatorValveBody,
    _authorized: None = Depends(require_operator),
) -> dict[str, Any]:
    payload = {k: v for k, v in body.model_dump().items() if v is not None}
    return _emulator_request("PUT", "/valves", payload)


app.mount("/", StaticFiles(directory=FRONTEND_DIR, html=True), name="frontend")
