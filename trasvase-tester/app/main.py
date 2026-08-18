from __future__ import annotations

import asyncio
from pathlib import Path
from typing import Any

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles

from .adapters.emulator_client import EmulatorClient
from .access import EdgeAccessGuard
from .capabilities.diagnostics.diagnostics_api import DiagnosticsApi
from .capabilities.diagnostics.diagnostics_service import DiagnosticsService
from .capabilities.injection.injection_api import InjectionApi
from .capabilities.injection.injection_service import InjectionService
from .capabilities.overview.overview_api import OverviewApi
from .capabilities.overview.overview_service import OverviewService
from .capabilities.process.process_api import ProcessApi
from .capabilities.process.process_service import ProcessService
from .capabilities.production.production_api import ProductionApi
from .capabilities.production.production_service import ProductionService
from .capabilities.pumps.pumps_api import PumpsApi
from .capabilities.pumps.pumps_service import PumpsService
from .config import AppConfig, load_config
from .control.snapshot_hub import SnapshotHub
from .injection_mode import InjectionModeStore
from .logging_utils import configure_file_logger
from .modbus_client import ModbusPoller, SimulationPoller
from .polling_control import PollingControlStore
from .pump_control import PumpControlStore
from .state import RuntimeState


APP_DIR = Path(__file__).resolve().parent
FRONTEND_DIR = APP_DIR.parent / "frontend"
LOGGER = configure_file_logger("trasvase.web", "trasvase-tester.log")

config: AppConfig = load_config()
injection_mode = InjectionModeStore()
access_guard = EdgeAccessGuard(config.runtime.internal_emulator_token)
polling_control = PollingControlStore(
    default_sample_rate_ms=config.polling.interval_ms
)
pump_controls = PumpControlStore()
state = RuntimeState(config, injection_mode, polling_control, pump_controls)
poller: ModbusPoller | SimulationPoller
if config.runtime.simulation_mode:
    poller = SimulationPoller(config, state)
else:
    poller = ModbusPoller(config, state)
emulator_client = EmulatorClient(config.runtime.field_emulator_url)


async def produce_stream_snapshot() -> dict[str, Any]:
    emulator = await asyncio.to_thread(emulator_client.safe_state)
    return {
        "type": "state",
        "snapshot": state.snapshot(),
        "emulator": emulator,
    }


snapshot_hub = SnapshotHub(
    interval_s=max(config.polling.interval_ms / 1000.0, 0.2),
    producer=produce_stream_snapshot,
)
app = FastAPI(
    title="Trasvase Tester",
    version="0.1.0",
    description=(
        "Web + master Modbus/TCP para visualizar y probar la frontera "
        "de emulación de bombas de trasvase."
    ),
)
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=False,
    allow_methods=["*"],
    allow_headers=["*"],
)

overview_service = OverviewService(config, state, LOGGER)
app.include_router(
    OverviewApi(
        overview_service,
        snapshot_hub,
        access_guard.require_edge,
    ).router
)
app.include_router(DiagnosticsApi(DiagnosticsService(state)).router)
app.include_router(
    InjectionApi(
        InjectionService(config, state, LOGGER),
        access_guard.require_edge,
        access_guard.require_edge_or_emulator,
    ).router
)
app.include_router(
    ProcessApi(
        ProcessService(emulator_client),
        access_guard.require_edge,
    ).router
)
app.include_router(
    PumpsApi(
        PumpsService(config, state, LOGGER),
        access_guard.require_edge,
    ).router
)
app.include_router(
    ProductionApi(
        ProductionService(config, state),
        access_guard.require_edge,
    ).router
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


app.mount("/", StaticFiles(directory=FRONTEND_DIR, html=True), name="frontend")
