import sys
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "field-emulator"))

from field_emulator.main import FieldEmulator


def test_inlet_valve_writes_yNvCamAsp_and_outlet_valve_writes_yNvRes(monkeypatch):
    monkeypatch.setenv("FIELD_EMULATOR_INLET_RATE_PER_S", "90")
    monkeypatch.setenv("FIELD_EMULATOR_OUTLET_RATE_PER_S", "90")
    monkeypatch.setenv("FIELD_EMULATOR_PUMP_RATE_PER_S", "12")
    emu = FieldEmulator()
    emu.state["inlet_open_pct"] = 100
    emu.state["outlet_open_pct"] = 100
    emu.state["yNvCamAsp"] = 1000
    emu.state["yNvRes"] = 3000
    emu._last_tick = time.time() - 1.0

    snap = {
        "timestamp": 1,
        "injection_mode": {"enabled": True},
        "values": {
            "gCamFn": {"value": 0},
            "gCamRb": {"value": 4000},
            "gResFn": {"value": -1},
            "gResSp": {"value": 6000},
            "bB1EMar": {"value": False},
            "bB2EMar": {"value": False},
            "bB3EMar": {"value": False},
            "bB4EMar": {"value": False},
            "bB5EMar": {"value": False},
        },
    }
    posts = []
    emu._get_json = lambda path: snap
    emu._post_json = lambda path, payload: posts.append((path, payload)) or {"ok": True}

    emu._tick()

    assert posts[0][1]["values"] == {"yNvCamAsp": 1090}
    assert posts[1][1]["values"] == {"yNvRes": 2910}
    assert emu.state["last_write_values"] == {
        "yNvCamAsp": 1090,
        "yNvRes": 2910,
    }


def test_field_emulator_initializes_from_genuine_feedback_not_y_memory(monkeypatch):
    monkeypatch.setenv("FIELD_EMULATOR_INLET_RATE_PER_S", "0")
    monkeypatch.setenv("FIELD_EMULATOR_OUTLET_RATE_PER_S", "0")
    monkeypatch.setenv("FIELD_EMULATOR_PUMP_RATE_PER_S", "0")
    emu = FieldEmulator()
    emu.state["yNvCamAsp"] = None
    emu.state["yNvRes"] = None
    emu._last_tick = time.time() - 1.0

    snap = {
        "timestamp": 1,
        "injection_mode": {"enabled": True},
        "values": {
            "gCamFn": {"value": 0},
            "gCamRb": {"value": 4000},
            "gResFn": {"value": -1},
            "gResSp": {"value": 6000},
            "eNvCamAsp": {"value": 1234},
            "eNvRes": {"value": 4321},
            "yNvCamAsp": {"value": 3999},
            "yNvRes": {"value": 1},
            "bB1EMar": {"value": False},
            "bB2EMar": {"value": False},
            "bB3EMar": {"value": False},
            "bB4EMar": {"value": False},
            "bB5EMar": {"value": False},
        },
    }
    posts = []
    emu._get_json = lambda path: snap
    emu._post_json = lambda path, payload: posts.append((path, payload)) or {"ok": True}

    emu._tick()

    assert posts[0][1]["values"] == {"yNvCamAsp": 1234}
    assert posts[1][1]["values"] == {"yNvRes": 4321}


def test_reservoir_valve_50_balances_three_running_pumps_by_default(monkeypatch, tmp_path):
    monkeypatch.setenv("FIELD_EMULATOR_PUMP_RATE_PER_S", "12")
    monkeypatch.delenv("FIELD_EMULATOR_OUTLET_RATE_PER_S", raising=False)
    monkeypatch.setenv("FIELD_EMULATOR_INLET_RATE_PER_S", "0")
    monkeypatch.setenv("FIELD_EMULATOR_STATE_FILE", str(tmp_path / "state.json"))
    emu = FieldEmulator()
    assert emu.outlet_rate == 72
    emu.state["inlet_open_pct"] = 0
    emu.state["outlet_open_pct"] = 50
    emu.state["yNvCamAsp"] = 2000
    emu.state["yNvRes"] = 3000
    emu._last_tick = time.time() - 1.0

    snap = {
        "timestamp": 1,
        "injection_mode": {"enabled": True},
        "values": {
            "gCamFn": {"value": 0},
            "gCamRb": {"value": 4000},
            "gResFn": {"value": -1},
            "gResSp": {"value": 6000},
            "bB1EMar": {"value": True},
            "bB2EMar": {"value": True},
            "bB3EMar": {"value": True},
            "bB4EMar": {"value": False},
            "bB5EMar": {"value": False},
        },
    }
    posts = []
    emu._get_json = lambda path: snap
    emu._post_json = lambda path, payload: posts.append((path, payload)) or {"ok": True}

    emu._tick()

    assert posts[1][1]["values"] == {"yNvRes": 3000}
