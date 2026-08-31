import sys
import time
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "field-emulator"))

from field_emulator.main import FieldEmulator
from field_emulator.history import LevelHistoryStore
from field_emulator.simulation import daily_consumption_pct, seasonal_inlet_pct, simulated_clock


def configure_runtime_files(monkeypatch, tmp_path):
    monkeypatch.setenv("FIELD_EMULATOR_STATE_FILE", str(tmp_path / "state.json"))
    monkeypatch.setenv("FIELD_EMULATOR_HISTORY_FILE", str(tmp_path / "history.csv"))


def test_inlet_valve_writes_yNvCamAsp_and_outlet_valve_writes_yNvRes(monkeypatch, tmp_path):
    configure_runtime_files(monkeypatch, tmp_path)
    monkeypatch.setenv("FIELD_EMULATOR_INLET_RATE_PER_S", "90")
    monkeypatch.setenv("FIELD_EMULATOR_CONSUMPTION_RATE_PER_S", "90")
    monkeypatch.setenv("FIELD_EMULATOR_PUMP_RATE_PER_S", "12")
    emu = FieldEmulator()
    emu.state["manual_inlet_open_pct"] = 100
    emu.state["manual_outlet_open_pct"] = 100
    emu.state["yNvCamAsp"] = 1000
    emu.state["yNvRes"] = 3000
    emu._last_tick = time.time() - 1.0

    snap = {
        "timestamp": 1,
        "connection": {"connected": True},
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

    assert posts == [
        (
            "/api/injection",
            {
                "values": {"yNvCamAsp": 1090, "yNvRes": 2910},
                "source": "field-emulator",
            },
        )
    ]
    assert emu.state["last_write_values"] == {
        "yNvCamAsp": 1090,
        "yNvRes": 2910,
    }


def test_field_emulator_initializes_from_genuine_feedback_not_y_memory(monkeypatch, tmp_path):
    configure_runtime_files(monkeypatch, tmp_path)
    monkeypatch.setenv("FIELD_EMULATOR_CONSUMPTION_RATE_PER_S", "0")
    monkeypatch.setenv("FIELD_EMULATOR_PUMP_RATE_PER_S", "0")
    emu = FieldEmulator()
    emu.state["yNvCamAsp"] = None
    emu.state["yNvRes"] = None
    emu._last_tick = time.time() - 1.0

    snap = {
        "timestamp": 1,
        "connection": {"connected": True},
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

    assert posts[0][1]["values"] == {"yNvCamAsp": 1234, "yNvRes": 4321}


def test_four_pumps_slightly_beat_maximum_consumption_by_default(monkeypatch, tmp_path):
    configure_runtime_files(monkeypatch, tmp_path)
    monkeypatch.setenv("FIELD_EMULATOR_PUMP_RATE_PER_S", "12")
    monkeypatch.delenv("FIELD_EMULATOR_CONSUMPTION_RATE_PER_S", raising=False)
    monkeypatch.setenv("FIELD_EMULATOR_INLET_RATE_PER_S", "0")
    emu = FieldEmulator()
    assert emu.consumption_rate == pytest.approx(45.6)
    emu.state["manual_inlet_open_pct"] = 0
    emu.state["manual_outlet_open_pct"] = 100
    emu.state["yNvCamAsp"] = 2000
    emu.state["yNvRes"] = 3000
    emu._last_tick = time.time() - 1.0

    snap = {
        "timestamp": 1,
        "connection": {"connected": True},
        "injection_mode": {"enabled": True},
        "values": {
            "gCamFn": {"value": 0},
            "gCamRb": {"value": 4000},
            "gResFn": {"value": -1},
            "gResSp": {"value": 6000},
            "bB1EMar": {"value": True},
            "bB2EMar": {"value": True},
            "bB3EMar": {"value": True},
            "bB4EMar": {"value": True},
            "bB5EMar": {"value": False},
        },
    }
    posts = []
    emu._get_json = lambda path: snap
    emu._post_json = lambda path, payload: posts.append((path, payload)) or {"ok": True}

    emu._tick()

    assert 3000 < posts[0][1]["values"]["yNvRes"] <= 3003


def test_field_emulator_pauses_writes_while_plc_is_disconnected(monkeypatch, tmp_path):
    configure_runtime_files(monkeypatch, tmp_path)
    emu = FieldEmulator()
    emu.state["yNvCamAsp"] = 1000
    emu.state["yNvRes"] = 3000
    emu._last_tick = time.time() - 1.0
    emu._get_json = lambda path: {
        "timestamp": 1,
        "connection": {"connected": False},
        "injection_mode": {"enabled": True},
        "values": {},
    }
    posts = []
    emu._post_json = lambda path, payload: posts.append((path, payload)) or {"ok": True}

    emu._tick()

    assert posts == []
    assert emu.state["yNvCamAsp"] == 1000
    assert emu.state["yNvRes"] == 3000
    assert emu.state["last_error"] == "PLC desconectado; emulacion pausada"


def test_seasonal_curve_matches_solstices_and_equinoxes():
    assert seasonal_inlet_pct(0) == pytest.approx(20)
    assert seasonal_inlet_pct(25) == pytest.approx(60)
    assert seasonal_inlet_pct(50) == pytest.approx(100)
    assert seasonal_inlet_pct(75) == pytest.approx(60)
    assert seasonal_inlet_pct(100) == pytest.approx(20)


def test_simulated_clock_compresses_one_day_into_one_real_hour():
    start = 123 * 3600
    assert simulated_clock(start).hour == pytest.approx(0)
    assert simulated_clock(start + 900).hour == pytest.approx(6)
    assert simulated_clock(start + 1800).hour == pytest.approx(12)
    assert simulated_clock(start + 3599).hour > 23.9
    assert simulated_clock(start + 3600).day_index == 124


def test_daily_consumption_is_deterministic_and_peaks_near_key_hours():
    day = 456_789
    assert daily_consumption_pct(6, day) == daily_consumption_pct(6, day)
    assert daily_consumption_pct(6, day) > daily_consumption_pct(2, day)
    assert daily_consumption_pct(12, day) > daily_consumption_pct(17, day)
    assert daily_consumption_pct(21, day) > daily_consumption_pct(17, day)


def test_daily_consumption_has_no_jumps_between_peaks_and_valleys():
    day = 456_789
    epsilon = 0.000001
    transition_hours = (
        2.0, 3.5, 4.0, 6.0, 8.0, 9.0, 10.0, 12.0,
        14.0, 15.0, 17.0, 18.5, 19.0, 21.0, 23.0,
    )
    for transition_hour in transition_hours:
        before = daily_consumption_pct(transition_hour - epsilon, day)
        after = daily_consumption_pct(transition_hour + epsilon, day)
        assert before == pytest.approx(after, abs=0.001)

    end_of_day = daily_consumption_pct(24.0 - epsilon, day)
    start_of_next_day = daily_consumption_pct(epsilon, day + 1)
    assert end_of_day == pytest.approx(start_of_next_day, abs=0.001)


def test_history_samples_every_30_seconds_and_keeps_requested_window(tmp_path):
    store = LevelHistoryStore(tmp_path / "levels.csv", sample_interval_s=30, retention_simulated_days=2)
    assert store.record(10_000, 100, 200)
    assert not store.record(10_029, 101, 201)
    assert store.record(10_030, 102, 202)
    assert store.record(10_000 + 2 * 3600 + 1, 103, 203)

    snapshot = store.snapshot()
    assert snapshot["sample_interval_s"] == 30
    assert snapshot["retention_simulated_days"] == 2
    assert len(snapshot["points"]) == 2
    assert (tmp_path / "levels.csv").read_text(encoding="utf-8").startswith("timestamp_real,")
