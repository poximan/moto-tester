import sys
from pathlib import Path

import pytest
import yaml

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "trasvase-tester"))

from app.config import load_config
from app.injection_mode import DISABLED, ENABLED, InjectionModeStore
from app.logging_utils import tail_file
from app.modbus_client import ModbusPoller
from app.polling_control import PollingControlStore
from app.pump_control import PumpControlStore
from app.state import RuntimeState


RUNTIME_SECTIONS = {"server", "controller", "polling", "safety", "runtime"}
SERVICE_DIR = Path("trasvase-tester")
SERVICE_APP = SERVICE_DIR / "app"
SERVICE_FRONTEND = SERVICE_DIR / "frontend"
FIELD_EMULATOR_DIR = Path("field-emulator")


def test_default_config_map():
    cfg = load_config("config/default.yaml")
    assert cfg.controller.host == "10.10.9.122"
    assert cfg.controller.port == 502
    assert cfg.controller.unit_id == 10
    assert cfg.polling.interval_ms == 2000
    assert cfg.polling.max_stale_ms == 5000
    assert not hasattr(cfg.runtime, "edge_auth_verify_url")
    assert cfg.tables["analog_reads"].start_pdu == 0
    assert cfg.signals_by_tag["eNvCamAsp"].reference == 30001
    assert cfg.signals_by_tag["gResFn"].default == -1
    assert cfg.signals_by_tag["bB5Falla"].pdu_address == 4171
    assert cfg.signals_by_tag["bB5Arndo"].pdu_address == 4172
    assert cfg.signals_by_tag["cB5Mr"].pdu_address == 6161


def test_exchange_map_matches_the_four_sca_tables():
    cfg = load_config("config/default.yaml")

    expected_rows = {
        "analog_reads": {
            "eNvCamAsp": 0, "eNvRes": 1, "eTurb": 2,
            "eB1Hs": 9, "eB2Hs": 13, "eB3Hs": 17, "eB4Hs": 21, "eB5Hs": 25,
        },
        "analog_setpoints": {
            "gResSp": 0, "gResRb": 1, "gResAt": 2,
            "gResParA": 4, "gResParB": 5, "gResParC": 6, "gResParD": 7,
            "gResArrA": 9, "gResArrB": 10, "gResArrC": 11, "gResArrD": 12,
            "gResBj": 14, "gResFn": 15,
            "gCamRb": 18, "gCamAt": 19, "gCamBj": 20, "gCamFn": 21,
            "yNvCamAsp": 27, "yNvRes": 28, "yTurb": 29,
            "yB1Hs": 30, "yB2Hs": 31, "yB3Hs": 32, "yB4Hs": 33, "yB5Hs": 34,
        },
        "digital_commands": {
            "cB1Aut": 0, "cB1Mr": 1, "cB2Aut": 4, "cB2Mr": 5,
            "cB3Aut": 8, "cB3Mr": 9, "cB4Aut": 12, "cB4Mr": 13,
            "cB5Aut": 16, "cB5Mr": 17,
            "yRFF": 23, "yResNvAtP": 24, "yResNvBjP": 25,
            "yCAspNvAtP": 26, "yCAspNvBjP": 27,
            "yB1RTU": 28, "yB1EMar": 29, "yB1Falla": 30,
            "yB2RTU": 31, "yB2EMar": 32, "yB2Falla": 33,
            "yB3RTU": 34, "yB3EMar": 35, "yB3Falla": 36,
            "yB4RTU": 37, "yB4EMar": 38, "yB4Falla": 39,
            "yB5RTU": 40, "yB5EMar": 41, "yB5Falla": 42,
        },
    }
    expected_digital_rows = {
        "bRFF": 0,
        "bResFR": 4,
        "bResRb": 5, "bResAt": 6, "bResBj": 7, "bResNvAtP": 8, "bResNvBjP": 9,
        "bCAspRb": 14, "bCAspAt": 15, "bCAspBj": 16,
        "bCAspNvAtP": 17, "bCAspNvBjP": 18,
    }
    pump_signal_offsets = (
        (0, "RTU"), (1, "Aut"), (2, "Ok"), (3, "EMar"), (5, "Falla"), (6, "Arndo"),
    )
    for pump, start in enumerate((26, 37, 48, 59, 70), start=1):
        for offset, suffix in pump_signal_offsets:
            expected_digital_rows[f"bB{pump}{suffix}"] = start + offset
    expected_rows["digital_reads"] = expected_digital_rows

    for table_name, tags in expected_rows.items():
        table = cfg.tables[table_name]
        actual = {signal.tag: signal.row for signal in table.signals}
        assert actual == tags
        assert len(set(actual.values())) == len(actual)
        for signal in table.signals:
            assert signal.reference == table.start_ref + signal.row
            assert signal.pdu_address == table.start_pdu + signal.row
            assert signal.value_class == table.value_class
            assert signal.positive_logic == table.positive_logic

    expected_mapped_values = {
        "eNvCamAsp": "iNvCamAsp", "eNvRes": "iNvRes", "eTurb": "iTurb",
        **{f"eB{pump}Hs": f"B{pump}Hs" for pump in range(1, 6)},
        "bRFF": "iRFF",
        "bResFR": "ResFR",
        "bResRb": "ResRb", "bResAt": "ResAt", "bResBj": "ResBj",
        "bResNvAtP": "ResNvAtP", "bResNvBjP": "ResNvBjP",
        "bCAspRb": "CAspRb", "bCAspAt": "CAspAt", "bCAspBj": "CAspBj",
        "bCAspNvAtP": "CAspNvAtP", "bCAspNvBjP": "CAspNvBjP",
    }
    for pump in range(1, 6):
        expected_mapped_values.update({
            f"bB{pump}RTU": f"iB{pump}RTU",
            f"bB{pump}Aut": f"B{pump}Aut",
            f"bB{pump}Ok": f"B{pump}Ok",
            f"bB{pump}EMar": f"iB{pump}EMar",
            f"bB{pump}Falla": f"iB{pump}Falla",
            f"bB{pump}Arndo": f"mB{pump}Arr",
        })
    actual_mapped_values = {
        tag: signal.mapped_value
        for tag, signal in cfg.signals_by_tag.items()
        if signal.mapped_value is not None
    }
    assert actual_mapped_values == expected_mapped_values

    expected_tables = {
        "analog_reads": (0, "input_register", "mval", None, 30001, 26),
        "analog_setpoints": (1, "holding_register", "iprm", None, 42049, 35),
        "digital_reads": (2, "discrete_input", "mbit", True, 14097, 77),
        "digital_commands": (3, "coil", "bit", True, 6145, 43),
    }
    assert set(cfg.tables) == set(expected_tables)
    for table_name, expected in expected_tables.items():
        table = cfg.tables[table_name]
        actual = (
            table.exchange_id,
            table.kind,
            table.value_class,
            table.positive_logic,
            table.start_ref,
            table.count,
        )
        assert actual == expected

    expected_parameter_defaults = {
        "gResSp": 6000, "gResRb": 5000, "gResAt": 4700,
        "gResParA": 4500, "gResParB": 4300, "gResParC": 4100, "gResParD": 3900,
        "gResArrA": 1500, "gResArrB": 1200, "gResArrC": 1100, "gResArrD": 1000,
        "gResBj": 600, "gResFn": -1,
        "gCamRb": 4000, "gCamAt": 3500, "gCamBj": 600, "gCamFn": 0,
        "yNvCamAsp": 0, "yNvRes": 0, "yTurb": 0,
        "yB1Hs": 0, "yB2Hs": 0, "yB3Hs": 0, "yB4Hs": 0, "yB5Hs": 0,
    }
    actual_parameter_defaults = {
        signal.tag: signal.default
        for signal in cfg.tables["analog_setpoints"].signals
    }
    assert actual_parameter_defaults == expected_parameter_defaults

    assert cfg.signals_by_tag["gResSp"].label == "Reserva nivel superior"
    assert cfg.signals_by_tag["gResFn"].label == "Reserva fondo"
    assert cfg.signals_by_tag["gCamFn"].label == "Cámara fondo"
    assert cfg.signals_by_tag["bRFF"].label == "Relé de falta de fase"
    assert cfg.signals_by_tag["bResFR"].label == "Reserva fuera de rango"
    for pump in range(1, 6):
        assert cfg.signals_by_tag[f"bB{pump}Arndo"].label == f"Bomba {pump} arrancando"


def test_yaml_has_no_runtime_parameters():
    raw = yaml.safe_load(Path("config/default.yaml").read_text(encoding="utf-8"))
    assert not (RUNTIME_SECTIONS & set(raw))


def test_exchange_map_rejects_invalid_base_duplicate_rows_and_negative_logic(tmp_path):
    source = Path("config/default.yaml")

    invalid_base = yaml.safe_load(source.read_text(encoding="utf-8"))
    invalid_base["tables"]["digital_reads"]["start_ref"] = 14098
    invalid_base_path = tmp_path / "invalid-base.yaml"
    invalid_base_path.write_text(yaml.safe_dump(invalid_base), encoding="utf-8")
    with pytest.raises(ValueError, match="Base invalida en digital_reads"):
        load_config(invalid_base_path)

    duplicate_row = yaml.safe_load(source.read_text(encoding="utf-8"))
    duplicate_row["tables"]["digital_reads"]["signals"][1]["row"] = 0
    duplicate_row_path = tmp_path / "duplicate-row.yaml"
    duplicate_row_path.write_text(yaml.safe_dump(duplicate_row), encoding="utf-8")
    with pytest.raises(ValueError, match="Fila duplicada en digital_reads: 0"):
        load_config(duplicate_row_path)

    negative_logic = yaml.safe_load(source.read_text(encoding="utf-8"))
    negative_logic["tables"]["digital_commands"]["positive_logic"] = False
    negative_logic_path = tmp_path / "negative-logic.yaml"
    negative_logic_path.write_text(yaml.safe_dump(negative_logic), encoding="utf-8")
    with pytest.raises(ValueError, match="debe declarar positive_logic=true"):
        load_config(negative_logic_path)


def test_env_example_has_no_global_or_temporal_write_flags():
    env = Path(".env.example").read_text(encoding="utf-8")
    assert "PLC_WRITE_ENABLED" not in env
    assert "ALLOW_REGISTER_WRITES" not in env
    assert "ALLOW_FACADE_WRITES" not in env
    assert "WRITE_MODE" not in env
    assert "INJECTION_ENABLE_LEASE_SECONDS" not in env
    assert "EDGE_AUTH_VERIFY_URL" not in env


def test_compose_uses_env_file_and_runtime_volume():
    compose = Path("docker-compose.yml").read_text(encoding="utf-8")
    assert "env_file:" in compose
    assert "./runtime:/app/runtime" in compose
    assert "POLL_INTERVAL_MS" not in compose
    assert "MODBUS_HOST" not in compose
    assert "PLC_WRITE_ENABLED" not in compose
    assert "SIMULATION_MODE" not in compose
    assert "ports:" not in compose


def test_no_run_scripts():
    assert not Path("run.sh").exists()
    assert not Path("run.bat").exists()


def test_injection_mode_file_is_created_disabled_by_default(tmp_path):
    mode_file = tmp_path / "runtime" / "injection_mode.txt"
    store = InjectionModeStore(path=mode_file)

    assert mode_file.exists()
    assert mode_file.read_text(encoding="utf-8").strip() == DISABLED
    assert store.snapshot()["mode"] == DISABLED


def test_injection_mode_store_remembers_the_last_value_after_restart(tmp_path):
    path = tmp_path / "injection_mode.txt"
    store = InjectionModeStore(path=path)
    assert store.snapshot()["mode"] == DISABLED
    assert store.snapshot()["enabled"] is False

    store.set_mode(ENABLED)
    assert path.read_text(encoding="utf-8").strip() == ENABLED
    assert store.snapshot()["enabled"] is True

    restarted_enabled = InjectionModeStore(path=path)
    assert restarted_enabled.snapshot()["mode"] == ENABLED
    assert restarted_enabled.snapshot()["enabled"] is True

    restarted_enabled.set_mode(DISABLED)
    restarted_disabled = InjectionModeStore(path=path)
    assert restarted_disabled.snapshot()["mode"] == DISABLED
    assert restarted_disabled.snapshot()["enabled"] is False


def test_only_y_tags_depend_on_injection_mode(tmp_path):
    cfg = load_config("config/default.yaml")
    injection_mode = InjectionModeStore(path=tmp_path / "injection_mode.txt")
    polling = PollingControlStore(tmp_path / "modbus_polling.json")
    controls = PumpControlStore(tmp_path / "pump_controls.json")
    state = RuntimeState(cfg, injection_mode, polling, controls)

    for function_code in ("01", "02", "03", "04"):
        polling.update(function_code, enabled=False)

    assert cfg.signals_by_tag["gResSp"].writable is True
    assert state.enqueue_write("gResSp", 5000)["queued"] is True
    assert state.enqueue_write("cB1Aut", True)["queued"] is True

    disabled = state.enqueue_injections({"yNvRes": 3200})["yNvRes"]
    assert disabled["queued"] is False
    assert disabled["reason"] == "injection_mode=disabled"

    injection_mode.set_mode(ENABLED)
    assert state.enqueue_injections({"yNvRes": 3200})["yNvRes"]["queued"] is True


def test_field_emulator_keeps_only_its_latest_pending_levels(tmp_path):
    cfg = load_config("config/default.yaml")
    injection_mode = InjectionModeStore(path=tmp_path / "injection_mode.txt")
    injection_mode.set_mode(ENABLED)
    state = RuntimeState(
        cfg,
        injection_mode,
        PollingControlStore(tmp_path / "modbus_polling.json"),
        PumpControlStore(tmp_path / "pump_controls.json"),
    )
    state.drain_writes()

    state.enqueue_injections(
        {"yNvCamAsp": 1000, "yNvRes": 2000},
        source="field-emulator",
    )
    state.enqueue_injections(
        {"yNvCamAsp": 1100, "yNvRes": 2100},
        source="field-emulator",
    )

    writes = state.drain_writes()
    assert [(write.tag, write.value) for write in writes] == [
        ("yNvCamAsp", 1100),
        ("yNvRes", 2100),
    ]


def test_field_emulator_levels_keep_their_turn_while_one_write_is_in_flight(tmp_path):
    cfg = load_config("config/default.yaml")
    injection_mode = InjectionModeStore(path=tmp_path / "injection_mode.txt")
    injection_mode.set_mode(ENABLED)
    state = RuntimeState(
        cfg,
        injection_mode,
        PollingControlStore(tmp_path / "modbus_polling.json"),
        PumpControlStore(tmp_path / "pump_controls.json"),
    )
    state.drain_writes()

    state.enqueue_injections(
        {"yNvCamAsp": 1000, "yNvRes": 2000},
        source="field-emulator",
    )
    chamber_write = state.next_write()
    assert chamber_write is not None
    assert (chamber_write.tag, chamber_write.value) == ("yNvCamAsp", 1000)

    state.enqueue_injections(
        {"yNvCamAsp": 1100, "yNvRes": 2100},
        source="field-emulator",
    )
    state.complete_write(chamber_write)

    reserve_write = state.next_write()
    assert reserve_write is not None
    assert (reserve_write.tag, reserve_write.value) == ("yNvRes", 2100)

    state.enqueue_injections(
        {"yNvCamAsp": 1200, "yNvRes": 2200},
        source="field-emulator",
    )
    state.complete_write(reserve_write)

    next_chamber_write = state.next_write()
    assert next_chamber_write is not None
    assert (next_chamber_write.tag, next_chamber_write.value) == ("yNvCamAsp", 1200)
    state.complete_write(next_chamber_write)

    next_reserve_write = state.next_write()
    assert next_reserve_write is not None
    assert (next_reserve_write.tag, next_reserve_write.value) == ("yNvRes", 2200)


def test_write_stays_pending_until_it_is_completed(tmp_path):
    cfg = load_config("config/default.yaml")
    state = RuntimeState(
        cfg,
        InjectionModeStore(path=tmp_path / "injection_mode.txt"),
        PollingControlStore(tmp_path / "modbus_polling.json"),
        PumpControlStore(tmp_path / "pump_controls.json"),
    )
    state.drain_writes()
    state.enqueue_write("gResSp", 5000, source="web")

    pending = state.next_write()
    assert pending is not None
    assert state.next_write() is pending
    assert state.snapshot()["write_queue"] == {"depth": 1, "capacity": 200}

    state.complete_write(pending)
    assert state.next_write() is None


def test_modbus_connection_failure_does_not_remove_the_pending_write(tmp_path, monkeypatch):
    cfg = load_config("config/default.yaml")
    state = RuntimeState(
        cfg,
        InjectionModeStore(path=tmp_path / "injection_mode.txt"),
        PollingControlStore(tmp_path / "modbus_polling.json"),
        PumpControlStore(tmp_path / "pump_controls.json"),
    )
    state.drain_writes()
    state.enqueue_write("gResSp", 5000, source="web")
    pending = state.next_write()
    poller = ModbusPoller(cfg, state)
    poller._client = object()

    def fail_write(request):
        raise ConnectionError("PLC no disponible")

    monkeypatch.setattr(poller, "_write_request", fail_write)

    with pytest.raises(ConnectionError, match="PLC no disponible"):
        poller._process_writes()

    assert state.next_write() is pending


def test_log_tail_reads_only_the_requested_final_lines(tmp_path):
    log_path = tmp_path / "service.log"
    log_path.write_text("".join(f"line {index}\n" for index in range(1000)), encoding="utf-8")

    assert tail_file(log_path, max_lines=3) == ["line 997", "line 998", "line 999"]


def test_modbus_polling_defaults_and_persists_by_function_code(tmp_path):
    path = tmp_path / "runtime" / "modbus_polling.json"
    store = PollingControlStore(path)

    snapshot = store.snapshot()
    assert set(snapshot["functions"]) == {"01", "02", "03", "04"}
    assert all(item["enabled"] for item in snapshot["functions"].values())
    assert all(item["sample_rate_ms"] == 2000 for item in snapshot["functions"].values())

    store.update("FC2", enabled=False, sample_rate_ms=3500)
    reloaded = PollingControlStore(path).snapshot()
    assert reloaded["functions"]["02"]["enabled"] is False
    assert reloaded["functions"]["02"]["sample_rate_ms"] == 3500


def test_modbus_polling_rejects_incomplete_persisted_config(tmp_path):
    path = tmp_path / "modbus_polling.json"
    path.write_text('{"01": {"enabled": true, "sample_rate_ms": 2000}}', encoding="utf-8")

    try:
        PollingControlStore(path)
    except ValueError as exc:
        assert "exactamente" in str(exc)
    else:
        raise AssertionError("Una configuracion incompleta debe fallar al iniciar")


def test_injection_lives_only_inside_setpoints_and_commands():
    cfg = load_config("config/default.yaml")

    assert set(cfg.tables) == {
        "analog_reads",
        "analog_setpoints",
        "digital_reads",
        "digital_commands",
    }
    assert cfg.tables["analog_reads"].start_ref == 30001
    assert cfg.tables["analog_reads"].count == 26
    assert cfg.tables["digital_reads"].start_ref == 14097
    assert cfg.tables["digital_reads"].count == 77

    assert cfg.tables["analog_setpoints"].start_ref == 42049
    assert cfg.tables["analog_setpoints"].count == 35
    assert cfg.signals_by_tag["yNvCamAsp"].table == "analog_setpoints"
    assert cfg.signals_by_tag["yNvCamAsp"].row == 27
    assert cfg.signals_by_tag["yNvCamAsp"].reference == 42076
    assert cfg.signals_by_tag["yNvCamAsp"].pdu_address == 2075
    assert cfg.signals_by_tag["yNvCamAsp"].facade is True
    assert cfg.signals_by_tag["yB5Hs"].row == 34
    assert cfg.signals_by_tag["yB5Hs"].reference == 42083

    assert cfg.tables["digital_commands"].start_ref == 6145
    assert cfg.tables["digital_commands"].count == 43
    assert cfg.signals_by_tag["yRFF"].table == "digital_commands"
    assert cfg.signals_by_tag["yRFF"].row == 23
    assert cfg.signals_by_tag["yRFF"].reference == 6168
    assert cfg.signals_by_tag["yRFF"].pdu_address == 6167
    assert cfg.signals_by_tag["yRFF"].facade is True
    assert cfg.signals_by_tag["yB5Falla"].row == 42
    assert cfg.signals_by_tag["yB5Falla"].reference == 6187
    assert cfg.signals_by_tag["yB5Falla"].pdu_address == 6186


def test_sca_table_labels_and_production_counts_only():
    cfg = load_config("config/default.yaml")
    expected = {
        "analog_reads": ("SCA - lectura AN [0]", 8, 0),
        "analog_setpoints": ("SCA - consigna AN [1]", 17, 8),
        "digital_reads": ("SCA - lectura DI [2]", 42, 0),
        "digital_commands": ("SCA - comando DI [3]", 10, 20),
    }
    for table_name, (label, production_count, injection_count) in expected.items():
        table = cfg.tables[table_name]
        assert table.label == label
        assert len([s for s in table.signals if not s.facade]) == production_count
        assert len([s for s in table.signals if s.facade]) == injection_count


def test_removed_exchange_tags_are_not_defined():
    cfg = load_config("config/default.yaml")
    removed = {
        "yResRb", "yResAt", "yResBj",
        "yCAspRb", "yCAspAt", "yCAspBj",
        "yB1Aut", "yB1Ok",
        "yB2Aut", "yB2Ok",
        "yB3Aut", "yB3Ok",
        "yB4Aut", "yB4Ok",
        "yB5Aut", "yB5Ok",
        "yB1Bypass", "yB2Bypass", "yB3Bypass", "yB4Bypass", "yB5Bypass",
        "bB1Bypass", "bB2Bypass", "bB3Bypass", "bB4Bypass", "bB5Bypass",
        "bB1Arr", "bB2Arr", "bB3Arr", "bB4Arr", "bB5Arr",
    }
    assert not (removed & set(cfg.signals_by_tag))


def test_injection_targets_are_explicit():
    cfg = load_config("config/default.yaml")
    assert cfg.signals_by_tag["yNvCamAsp"].table == "analog_setpoints"
    assert cfg.signals_by_tag["yNvCamAsp"].injects_tag == "eNvCamAsp"
    assert cfg.signals_by_tag["yNvCamAsp"].injection_group == "analog_reads"
    assert cfg.signals_by_tag["yB5Hs"].injects_tag == "eB5Hs"

    assert cfg.signals_by_tag["yRFF"].table == "digital_commands"
    assert cfg.signals_by_tag["yRFF"].injects_tag == "bRFF"
    assert cfg.signals_by_tag["yRFF"].injection_group == "digital_reads"
    assert cfg.signals_by_tag["yB5Falla"].injects_tag == "bB5Falla"
    assert cfg.signals_by_tag["bB1Arndo"].row == 32
    assert cfg.signals_by_tag["bB5Arndo"].row == 76


def test_polling_reads_every_declared_exchange_table_completely(tmp_path):
    cfg = load_config("config/default.yaml")
    state = RuntimeState(
        cfg,
        InjectionModeStore(path=tmp_path / "injection_mode.txt"),
        PollingControlStore(tmp_path / "modbus_polling.json"),
        PumpControlStore(tmp_path / "pump_controls.json"),
    )
    poller = ModbusPoller(cfg, state)

    class Response:
        def __init__(self, *, registers=None, bits=None):
            self.registers = registers
            self.bits = bits

        def isError(self):
            return False

    class RecordingClient:
        connected = True

        def __init__(self):
            self.calls = []

        def read_input_registers(self, *, address, count, **kwargs):
            self.calls.append(("input_register", address, count))
            return Response(registers=list(range(count)))

        def read_holding_registers(self, *, address, count, **kwargs):
            self.calls.append(("holding_register", address, count))
            return Response(registers=list(range(count)))

        def read_discrete_inputs(self, *, address, count, **kwargs):
            self.calls.append(("discrete_input", address, count))
            return Response(bits=[bool(index % 2) for index in range(count)])

        def read_coils(self, *, address, count, **kwargs):
            self.calls.append(("coil", address, count))
            return Response(bits=[bool(index % 2) for index in range(count)])

    client = RecordingClient()
    poller._client = client

    updates_by_table = {}
    for table in cfg.tables.values():
        updates = poller._read_table(table)
        updates_by_table[table.name] = updates
        assert set(updates) == {signal.tag for signal in table.signals}

    assert client.calls == [
        (table.kind, table.start_pdu, table.count)
        for table in cfg.tables.values()
    ]
    assert "yNvRes" in updates_by_table["analog_setpoints"]
    assert "yB5Falla" in updates_by_table["digital_commands"]
    assert "bResFR" in updates_by_table["digital_reads"]
    assert "bB1RTU" in updates_by_table["digital_reads"]
    assert "bB1Aut" in updates_by_table["digital_reads"]
    assert "bB5Arndo" in updates_by_table["digital_reads"]

    state.mark_table_error("analog_setpoints", "lectura incompleta")
    assert state.snapshot()["values"]["yNvRes"]["quality"] == "error"

    with pytest.raises(ValueError, match="Respuesta incompleta para analog_setpoints"):
        poller._require_complete_response(
            cfg.tables["analog_setpoints"],
            [0] * (cfg.tables["analog_setpoints"].count - 1),
            cfg.tables["analog_setpoints"].count,
        )


def test_ui_has_sca_tables_and_two_injection_tables():
    production = (SERVICE_FRONTEND / "src/components/ProductionTables.tsx").read_text(encoding="utf-8")
    injection = (SERVICE_FRONTEND / "src/components/InjectionPanel.tsx").read_text(encoding="utf-8")
    client = (SERVICE_FRONTEND / "src/TrasvaseApiClient.ts").read_text(encoding="utf-8")

    assert "TABLE_ORDER" in production
    assert '"analog_reads"' in production
    assert '"digital_commands"' in production
    assert 'table("analog_setpoints"' in injection
    assert 'table("digital_commands"' in injection
    assert '"api/injection"' in client


def test_frontend_uses_the_shared_react_foundation_without_tailwind():
    package = (SERVICE_FRONTEND / "package.json").read_text(encoding="utf-8")
    app = (SERVICE_FRONTEND / "src/App.tsx").read_text(encoding="utf-8")
    assert '"react": "19.2.8"' in package
    assert '"vite": "8.1.5"' in package
    assert '"@servicoop/frontend-foundation"' in package
    assert "tailwind" not in package.lower()
    assert "AppShell" in app


def test_dockerfiles_are_next_to_services_not_root():
    assert not Path("Dockerfile").exists()
    assert not Path("app").exists()
    assert not Path("field_emulator").exists()
    assert (SERVICE_DIR / "Dockerfile").exists()
    assert (FIELD_EMULATOR_DIR / "Dockerfile").exists()
    compose = Path("docker-compose.yml").read_text(encoding="utf-8")
    app_dockerfile = (SERVICE_DIR / "Dockerfile").read_text(encoding="utf-8")
    field_emulator_dockerfile = (FIELD_EMULATOR_DIR / "Dockerfile").read_text(encoding="utf-8")
    assert "dockerfile: trasvase-tester/Dockerfile" in compose
    assert "dockerfile: field-emulator/Dockerfile" in compose
    assert "dockerfile: app/Dockerfile" not in compose
    assert "dockerfile: field_emulator/Dockerfile" not in compose
    assert "COPY runtime" not in app_dockerfile
    assert "FROM node:24.18.0-alpine AS frontend-builder" in app_dockerfile
    assert "trasvase-tester/app ./trasvase-tester/app" in app_dockerfile
    assert "COPY --from=frontend-builder" in app_dockerfile
    assert "field-emulator ./field-emulator" in field_emulator_dockerfile


def test_pump_assets_are_packaged():
    asset_dir = SERVICE_FRONTEND / "public/assets"
    assert (asset_dir / "pump_gray.png").exists()
    assert (asset_dir / "pump_red.png").exists()
    assert (asset_dir / "pump_blue.png").exists()
    assert (asset_dir / "pump_green.png").exists()


def test_injection_mode_is_controlled_from_the_react_status_header():
    app = (SERVICE_FRONTEND / "src/App.tsx").read_text(encoding="utf-8")
    header = (SERVICE_FRONTEND / "src/components/StatusHeader.tsx").read_text(encoding="utf-8")
    assert "mode-card" not in app
    assert "setInjectionMode" in app
    assert "snapshot.injection_mode.enabled" in header


def test_g_setpoints_are_always_editable_from_react():
    source = (SERVICE_FRONTEND / "src/components/ProductionTables.tsx").read_text(encoding="utf-8")
    client = (SERVICE_FRONTEND / "src/TrasvaseApiClient.ts").read_text(encoding="utf-8")
    assert 'signal.tag.startsWith("g") && signal.writable' in source
    assert "SetpointEditor" in source
    assert '"api/write"' in client


def test_front_uses_websocket_stream_and_does_not_poll_refresh_snapshot():
    stream = (SERVICE_FRONTEND / "src/TrasvaseStreamClient.ts").read_text(encoding="utf-8")
    client = (SERVICE_FRONTEND / "src/TrasvaseApiClient.ts").read_text(encoding="utf-8")
    overview_api = (
        SERVICE_APP / "capabilities/overview/overview_api.py"
    ).read_text(encoding="utf-8")

    assert '"ws/stream"' in client
    assert 'add_api_websocket_route("/ws/stream", self.stream)' in overview_api
    assert "setInterval" not in stream
    assert "new WebSocket" in stream


def test_digital_injection_is_checkbox_without_extra_set_button():
    source = (SERVICE_FRONTEND / "src/components/InjectionPanel.tsx").read_text(encoding="utf-8")
    assert 'name === "digital_commands"' in source
    assert 'type="checkbox"' in source
    assert "client.inject(signal.tag, event.target.checked)" in source


def test_modbus_points_match_ace3600_formula_ranges():
    from app.addressing import ace_reference

    cfg = load_config("config/default.yaml")
    expected = {
        "analog_reads": ("input_register", 0, 30001, 30026),
        "analog_setpoints": ("holding_register", 1, 42049, 42083),
        "digital_reads": ("discrete_input", 2, 14097, 14173),
        "digital_commands": ("coil", 3, 6145, 6187),
    }
    for table_name, (kind, z, first_ref, last_ref) in expected.items():
        table = cfg.tables[table_name]
        assert table.start_ref == first_ref
        assert ace_reference(kind, z, 0) == first_ref
        assert ace_reference(kind, z, table.count - 1) == last_ref

    assert cfg.signals_by_tag["yNvCamAsp"].reference == ace_reference("holding_register", 1, 27)
    assert cfg.signals_by_tag["yNvRes"].reference == ace_reference("holding_register", 1, 28)
    assert cfg.signals_by_tag["yRFF"].reference == ace_reference("coil", 3, 23)
    assert cfg.signals_by_tag["yB5Falla"].reference == ace_reference("coil", 3, 42)
    assert cfg.signals_by_tag["bResFR"].reference == ace_reference("discrete_input", 2, 4)


def test_pump_cards_include_arr_emar_generation_and_specific_pills():
    pump = (SERVICE_FRONTEND / "src/components/PumpCard.tsx").read_text(encoding="utf-8")
    injection = (SERVICE_FRONTEND / "src/components/InjectionPanel.tsx").read_text(encoding="utf-8")
    client = (SERVICE_FRONTEND / "src/TrasvaseApiClient.ts").read_text(encoding="utf-8")
    emulator = Path("field-emulator/field_emulator/main.py").read_text(encoding="utf-8")
    header = (SERVICE_FRONTEND / "src/components/StatusHeader.tsx").read_text(encoding="utf-8")

    assert "bB1Arndo" in Path("config/default.yaml").read_text(encoding="utf-8")
    assert "generar EMar" in pump
    assert "localStorage" not in pump
    assert 'type="radio"' in pump
    assert "Deshabilitado" in pump
    assert "Automático" in pump
    assert "Forzar" in pump
    assert "pump.emar_mode" in pump
    assert "setEmarMode" in client
    assert "api/pumps/${pump}/emar-mode" in client
    assert "^yB[1-5]EMar$" in injection
    assert "presenter.signalBoolean(pump.rtu)" in pump
    assert "presenter.signalBoolean(rtuSelection)" in pump
    assert 'indicator("RTU", rtuFeedback)' in pump
    assert '"bRFF": False' in (SERVICE_APP / "modbus_client.py").read_text(encoding="utf-8")
    assert '"bResFR": reserve_level < reserve_floor or reserve_level > reserve_superior' in (
        SERVICE_APP / "modbus_client.py"
    ).read_text(encoding="utf-8")
    assert "generate_emar" not in emulator
    assert 'values.get(f"bB{pump_id}Arndo")' not in emulator
    assert "Fuente: PLC" in header
    assert "RTU (0)" not in pump
    assert "Tablero (1)" not in pump


def test_logs_ui_and_api_are_present():
    panel = (SERVICE_FRONTEND / "src/components/LogsPanel.tsx").read_text(encoding="utf-8")
    client = (SERVICE_FRONTEND / "src/TrasvaseApiClient.ts").read_text(encoding="utf-8")
    api = (SERVICE_APP / "capabilities/diagnostics/diagnostics_api.py").read_text(encoding="utf-8")
    assert "Diagnóstico y logs" in panel
    assert '"api/logs"' in client
    assert '"/api/logs"' in api
    assert '"/api/logs/{log_name}"' in api
    assert '"/api/diagnostics"' in api
    assert "Ver diagnóstico" in panel
    assert "Recargar archivo" in panel


def test_ui_controls_each_read_function_code_and_sample_rate():
    header = (SERVICE_FRONTEND / "src/components/StatusHeader.tsx").read_text(encoding="utf-8")
    control = (SERVICE_FRONTEND / "src/components/PollingControl.tsx").read_text(encoding="utf-8")
    client = (SERVICE_FRONTEND / "src/TrasvaseApiClient.ts").read_text(encoding="utf-8")
    api = (SERVICE_APP / "capabilities/overview/overview_api.py").read_text(encoding="utf-8")

    for function_code in ("01", "02", "03", "04"):
        assert f'"{function_code}"' in header
    assert "sample_rate_ms" in control
    assert "3_600_000" in control
    assert "api/modbus-polling" in client
    assert '"/api/modbus-polling"' in api
    assert '"/api/modbus-polling/{function_code}"' in api


def test_sca_window_title_shows_modbus_details():
    source = (SERVICE_FRONTEND / "src/components/ProductionTables.tsx").read_text(encoding="utf-8")
    assert "FC{fc}" in source
    assert "inicio {table.start_ref}" in source
    assert "offset {table.start_pdu}" in source
    assert "prod 0..{lastRow}" in source


def test_compose_starts_web_before_field_emulator_without_periodic_probe():
    compose = Path("docker-compose.yml").read_text(encoding="utf-8")
    compose_data = yaml.safe_load(compose)
    dockerfile = (SERVICE_DIR / "Dockerfile").read_text(encoding="utf-8")
    assert "HEALTHCHECK" not in dockerfile
    assert "condition: service_started" in compose
    # El web no debe depender del emulador: el emulador consume la API web.
    assert "depends_on" not in compose_data["services"]["trasvase-tester"]
