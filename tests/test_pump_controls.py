import logging
import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "trasvase-tester"))

from app.capabilities.pumps.pumps_service import PumpsService
from app.config import load_config
from app.injection_mode import InjectionModeStore
from app.polling_control import PollingControlStore
from app.pump_control import PumpControlStore
from app.state import RuntimeState


def build_service(tmp_path, *, drain_startup=True):
    config = load_config("config/default.yaml")
    state = RuntimeState(
        config,
        InjectionModeStore(path=tmp_path / "injection_mode.txt"),
        PollingControlStore(path=tmp_path / "modbus_polling.json"),
        PumpControlStore(path=tmp_path / "pump_controls.json"),
    )
    if drain_startup:
        state.drain_writes()
    return state, PumpsService(config, state, logging.getLogger("test.pumps"))


def test_disabled_and_forced_always_write_their_expected_y_value(tmp_path):
    state, service = build_service(tmp_path)
    assert state.injection_mode_snapshot()["enabled"] is False

    disabled = service.set_emar_mode(3, "disabled")
    forced = service.set_emar_mode(3, "forced")
    writes = state.drain_writes()

    assert disabled == {
        "ok": True,
        "pump_id": 3,
        "tag": "yB3EMar",
        "mode": "disabled",
        "value": False,
        "queued": True,
        "written": False,
    }
    assert forced == {
        "ok": True,
        "pump_id": 3,
        "tag": "yB3EMar",
        "mode": "forced",
        "value": True,
        "queued": True,
        "written": False,
    }
    assert [(write.tag, write.value) for write in writes] == [
        ("yB3EMar", False),
        ("yB3EMar", True),
    ]


def test_automatic_emar_follows_arndo_and_reasserts_the_output(tmp_path):
    state, service = build_service(tmp_path)
    state.update_values({"bB2Arndo": False})
    state.drain_writes()

    automatic = service.set_emar_mode(2, "automatic")
    selected_write = state.drain_writes()
    assert automatic["mode"] == "automatic"
    assert automatic["value"] is False
    assert [(write.tag, write.value) for write in selected_write] == [
        ("yB2EMar", False),
    ]

    state.update_values({"bB2Arndo": True})
    true_write = state.drain_writes()
    state.update_values({"bB2Arndo": True})
    repeated_true_write = state.drain_writes()
    state.update_values({"bB2Arndo": False})
    false_write = state.drain_writes()

    assert [(write.tag, write.value) for write in true_write] == [
        ("yB2EMar", True),
    ]
    assert [(write.tag, write.value) for write in repeated_true_write] == [
        ("yB2EMar", True),
    ]
    assert [(write.tag, write.value) for write in false_write] == [
        ("yB2EMar", False),
    ]


def test_constant_modes_are_reasserted_when_arndo_is_polled(tmp_path):
    state, service = build_service(tmp_path)
    service.set_emar_mode(1, "disabled")
    service.set_emar_mode(4, "forced")
    state.drain_writes()

    state.update_values({"bB1Arndo": True, "bB4Arndo": False})

    assert [(write.tag, write.value) for write in state.drain_writes()] == [
        ("yB1EMar", False),
        ("yB4EMar", True),
    ]


def test_pump_controls_are_shared_through_the_server_snapshot(tmp_path):
    state, service = build_service(tmp_path)

    state.enqueue_injections({"yB2RTU": True}, source="client-a")
    service.set_emar_mode(2, "forced")

    client_a = state.snapshot()
    client_b = state.snapshot()
    for snapshot in (client_a, client_b):
        assert snapshot["values"]["yB2RTU"]["value"] is True
        assert snapshot["values"]["yB2EMar"]["value"] is True
        assert snapshot["groups"]["pumps"][1]["emar_mode"] == "forced"


def test_pump_controls_survive_server_state_recreation(tmp_path):
    state, service = build_service(tmp_path)
    state.enqueue_injections({"yB4RTU": True}, source="client-a")
    service.set_emar_mode(4, "forced")

    recreated_state, _ = build_service(tmp_path)
    snapshot = recreated_state.snapshot()

    assert snapshot["values"]["yB4RTU"]["value"] is True
    assert snapshot["values"]["yB4EMar"]["value"] is True
    assert snapshot["groups"]["pumps"][3]["emar_mode"] == "forced"


def test_automatic_mode_survives_recreation_and_uses_the_next_arndo_value(tmp_path):
    _, service = build_service(tmp_path)
    service.set_emar_mode(5, "automatic")

    recreated_state, _ = build_service(tmp_path)
    assert recreated_state.snapshot()["groups"]["pumps"][4]["emar_mode"] == "automatic"

    recreated_state.update_values({"bB5Arndo": 1})
    assert [(write.tag, write.value) for write in recreated_state.drain_writes()] == [
        ("yB5EMar", True),
    ]


def test_persisted_modes_are_written_again_when_the_server_starts(tmp_path):
    state, service = build_service(tmp_path)
    service.set_emar_mode(4, "forced")
    state.drain_writes()

    recreated_state, _ = build_service(tmp_path, drain_startup=False)
    startup_values = {
        write.tag: write.value for write in recreated_state.drain_writes()
    }

    assert startup_values == {
        "yB1EMar": False,
        "yB2EMar": False,
        "yB3EMar": False,
        "yB4EMar": True,
        "yB5EMar": False,
    }


def test_generic_injection_cannot_override_emar_mode(tmp_path):
    state, _ = build_service(tmp_path)

    with pytest.raises(PermissionError, match="emar-mode"):
        state.enqueue_injections({"yB1EMar": True})
