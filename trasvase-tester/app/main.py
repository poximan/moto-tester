from __future__ import annotations

import asyncio
import json
import logging
import urllib.error
import urllib.request
from pathlib import Path
from typing import Any

from fastapi import FastAPI, HTTPException, WebSocket, WebSocketDisconnect
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse
from fastapi.staticfiles import StaticFiles

from .config import AppConfig, load_config
from .modbus_client import ModbusPoller, SimulationPoller
from .models import CommandBody, EmulatorValveBody, FacadeBody, GenericWriteBody, PumpCommandBody, WriteModeBody
from .state import RuntimeState
from .write_mode import WriteModeStore
from .logging_utils import configure_file_logger, log_dir, tail_file

APP_DIR = Path(__file__).resolve().parent
STATIC_DIR = APP_DIR / "static"
LOGGER = configure_file_logger("trasvase.web", "trasvase-tester.log")

config: AppConfig = load_config()
write_mode = WriteModeStore()
state = RuntimeState(config, write_mode)
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

app.mount("/static", StaticFiles(directory=STATIC_DIR), name="static")


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


@app.on_event("startup")
def on_startup() -> None:
    LOGGER.info("startup web/modbus service")
    poller.start()


@app.on_event("shutdown")
def on_shutdown() -> None:
    LOGGER.info("shutdown web/modbus service")
    poller.stop()


@app.get("/", include_in_schema=False)
def index() -> FileResponse:
    return FileResponse(STATIC_DIR / "index.html")


@app.get("/api/health")
def health() -> dict[str, Any]:
    snap = state.snapshot()
    return {
        "ok": True,
        "connected": snap["connection"].get("connected", False),
        "mode": snap["connection"].get("mode"),
        "write_mode": snap["write_mode"].get("mode"),
        "write_enabled": snap["write_mode"].get("write_enabled"),
        "last_error": snap["connection"].get("last_error"),
    }


@app.get("/api/snapshot")
def snapshot() -> dict[str, Any]:
    return state.snapshot()




@app.websocket("/ws/stream")
async def websocket_stream(websocket: WebSocket) -> None:
    await websocket.accept()
    interval_s = max(config.polling.interval_ms / 1000.0, 0.2)
    try:
        while True:
            emulator = await asyncio.to_thread(_emulator_state_safe)
            await websocket.send_json(
                {
                    "type": "state",
                    "snapshot": state.snapshot(),
                    "emulator": emulator,
                }
            )
            await asyncio.sleep(interval_s)
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
def set_write_mode(body: WriteModeBody) -> dict[str, Any]:
    LOGGER.warning("write_mode request mode=%s source=%s", body.mode, body.source)
    try:
        snapshot = state.set_write_mode(body.mode, source=body.source)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    return {"ok": True, **snapshot}


@app.post("/api/command")
def command(body: CommandBody) -> dict[str, Any]:
    signal = config.signals_by_tag.get(body.tag)
    if signal is None:
        raise HTTPException(status_code=404, detail=f"Tag no definido: {body.tag}")
    if signal.table != "digital_commands" or signal.facade:
        raise HTTPException(status_code=400, detail="Este endpoint solo acepta comandos digitales reales cB#")
    try:
        result = state.enqueue_write(body.tag, bool(body.value), source=body.source)
    except PermissionError as exc:
        raise HTTPException(status_code=403, detail=str(exc)) from exc
    return {"ok": True, "tag": body.tag, "value": bool(body.value), **result}


@app.post("/api/pumps/{pump_id}/command")
def pump_command(pump_id: int, body: PumpCommandBody) -> dict[str, Any]:
    LOGGER.info("pump command pump=%s aut=%s mr=%s source=%s", pump_id, body.aut, body.mr, body.source)
    if pump_id < 1 or pump_id > 5:
        raise HTTPException(status_code=404, detail="pump_id debe estar entre 1 y 5")
    results: dict[str, Any] = {}
    if body.aut is not None:
        tag = f"cB{pump_id}Aut"
        results[tag] = state.enqueue_write(tag, bool(body.aut), source=body.source)
    if body.mr is not None:
        tag = f"cB{pump_id}Mr"
        results[tag] = state.enqueue_write(tag, bool(body.mr), source=body.source)
    return {"ok": True, "pump_id": pump_id, "results": results}


@app.post("/api/write")
def generic_write(body: GenericWriteBody) -> dict[str, Any]:
    signal = config.signals_by_tag.get(body.tag)
    if signal is None:
        raise HTTPException(status_code=404, detail=f"Tag no definido: {body.tag}")
    if not signal.writable:
        raise HTTPException(status_code=403, detail=f"{body.tag} no está definido como escribible")
    try:
        result = state.enqueue_write(body.tag, body.value, source=body.source)
    except PermissionError as exc:
        raise HTTPException(status_code=403, detail=str(exc)) from exc
    return {"ok": True, "tag": body.tag, "value": body.value, **result}


@app.post("/api/injection")
def injection(body: FacadeBody) -> dict[str, Any]:
    LOGGER.info("injection request source=%s values=%s", body.source, body.values)
    written: dict[str, Any] = {}
    for tag, value in body.values.items():
        signal = config.signals_by_tag.get(tag)
        if signal is None:
            raise HTTPException(status_code=404, detail=f"Tag de inyección no definido: {tag}")
        if not signal.writable or not signal.facade:
            raise HTTPException(status_code=403, detail=f"{tag} no pertenece a inyección escribible")
        written[tag] = state.enqueue_write(tag, value, source=body.source)
    return {"ok": True, "results": written}


@app.post("/api/facade")
def facade_compat(body: FacadeBody) -> dict[str, Any]:
    return injection(body)


@app.get("/api/emulator/state")
def emulator_state() -> dict[str, Any]:
    return _emulator_request("GET", "/state")


@app.put("/api/emulator/valves")
def emulator_valves(body: EmulatorValveBody) -> dict[str, Any]:
    payload = {k: v for k, v in body.model_dump().items() if v is not None}
    return _emulator_request("PUT", "/valves", payload)
