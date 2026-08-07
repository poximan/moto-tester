import sys
from pathlib import Path

import yaml

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "trasvase-tester"))

from app.config import load_config
from app.polling_control import PollingControlStore
from app.write_mode import READ_ONLY, WRITE_ENABLED, WriteModeStore


RUNTIME_SECTIONS = {"server", "controller", "polling", "safety", "runtime"}
SERVICE_DIR = Path("trasvase-tester")
SERVICE_APP = SERVICE_DIR / "app"
FIELD_EMULATOR_DIR = Path("field-emulator")


def test_default_config_map():
    cfg = load_config("config/default.yaml")
    assert cfg.controller.host == "10.10.9.122"
    assert cfg.controller.port == 502
    assert cfg.controller.unit_id == 10
    assert cfg.polling.interval_ms == 2000
    assert cfg.polling.max_stale_ms == 5000
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
        "bResRb": 5, "bResAt": 6, "bResBj": 7, "bResNvAtP": 8, "bResNvBjP": 9,
        "bCAspRb": 14, "bCAspAt": 15, "bCAspBj": 16,
        "bCAspNvAtP": 17, "bCAspNvBjP": 18,
    }
    for pump, start in enumerate((26, 37, 48, 59, 70), start=1):
        for offset, suffix in enumerate(("RTU", "Aut", "Ok", "EMar", "InE", "Falla", "Arndo")):
            expected_digital_rows[f"bB{pump}{suffix}"] = start + offset
    expected_rows["digital_reads"] = expected_digital_rows

    for table_name, tags in expected_rows.items():
        actual = {signal.tag: signal.row for signal in cfg.tables[table_name].signals}
        assert actual == tags

    expected_mapped_values = {
        "eNvCamAsp": "iNvCamAsp", "eNvRes": "iNvRes", "eTurb": "iTurb",
        **{f"eB{pump}Hs": f"B{pump}Hs" for pump in range(1, 6)},
        "bRFF": "iRFF",
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
            f"bB{pump}InE": f"B{pump}InE",
            f"bB{pump}Falla": f"iB{pump}Falla",
            f"bB{pump}Arndo": f"mB{pump}Arr",
        })
    actual_mapped_values = {
        tag: signal.mapped_value
        for tag, signal in cfg.signals_by_tag.items()
        if signal.mapped_value is not None
    }
    assert actual_mapped_values == expected_mapped_values


def test_yaml_has_no_runtime_parameters():
    raw = yaml.safe_load(Path("config/default.yaml").read_text(encoding="utf-8"))
    assert not (RUNTIME_SECTIONS & set(raw))


def test_env_example_has_no_write_mode_or_write_enable_flags():
    env = Path(".env.example").read_text(encoding="utf-8")
    assert "PLC_WRITE_ENABLED" not in env
    assert "ALLOW_REGISTER_WRITES" not in env
    assert "ALLOW_FACADE_WRITES" not in env
    assert "WRITE_MODE" not in env


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


def test_write_mode_file_is_created_read_only_by_default(tmp_path):
    mode_file = tmp_path / "runtime" / "write_mode.txt"
    interlock_file = tmp_path / "runtime" / "write_interlock.txt"
    store = WriteModeStore(
        path=mode_file,
        interlock_path=interlock_file,
        lease_seconds=60,
    )

    assert mode_file.exists()
    assert interlock_file.read_text(encoding="utf-8").strip() == "disarmed"
    assert mode_file.read_text(encoding="utf-8").strip() == READ_ONLY
    assert store.snapshot()["mode"] == READ_ONLY


def test_write_mode_store_requires_interlock_and_lease(tmp_path):
    path = tmp_path / "write_mode.txt"
    interlock_path = tmp_path / "write_interlock.txt"
    now = [100.0]
    store = WriteModeStore(
        path=path,
        interlock_path=interlock_path,
        lease_seconds=60,
        monotonic_provider=lambda: now[0],
    )
    assert store.snapshot()["mode"] == READ_ONLY
    assert store.snapshot()["write_enabled"] is False

    try:
        store.set_mode(WRITE_ENABLED)
    except PermissionError:
        pass
    else:
        raise AssertionError("Un interlock desarmado debe impedir la escritura")

    interlock_path.write_text("armed\n", encoding="utf-8")
    store.set_mode(WRITE_ENABLED)
    assert path.read_text(encoding="utf-8").strip() == WRITE_ENABLED
    assert store.snapshot()["write_enabled"] is True

    now[0] += 61
    snap = store.snapshot()
    assert snap["mode"] == READ_ONLY
    assert snap["write_enabled"] is False
    assert snap["error"]

    restarted = WriteModeStore(
        path=path,
        interlock_path=interlock_path,
        lease_seconds=60,
    )
    assert restarted.snapshot()["mode"] == READ_ONLY


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
        "digital_reads": ("SCA - lectura DI [2]", 46, 0),
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
        "yB1Aut", "yB1Ok", "yB1InE",
        "yB2Aut", "yB2Ok", "yB2InE",
        "yB3Aut", "yB3Ok", "yB3InE",
        "yB4Aut", "yB4Ok", "yB4InE",
        "yB5Aut", "yB5Ok", "yB5InE",
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
    assert cfg.signals_by_tag["bB1InE"].row == 30
    assert cfg.signals_by_tag["bB1Arndo"].row == 32
    assert cfg.signals_by_tag["bB5InE"].row == 74
    assert cfg.signals_by_tag["bB5Arndo"].row == 76


def test_polling_excludes_injection_memory_from_reads():
    cfg = load_config("config/default.yaml")
    analog = cfg.tables["analog_setpoints"]
    digital = cfg.tables["digital_commands"]

    analog_poll_count = max(s.row for s in analog.signals if not s.facade) + 1
    digital_poll_count = max(s.row for s in digital.signals if not s.facade) + 1

    assert analog_poll_count == 22
    assert digital_poll_count == 18
    assert not any(s.tag.startswith("y") for s in analog.signals if not s.facade)
    assert not any(s.tag.startswith("y") for s in digital.signals if not s.facade)

    source = (SERVICE_APP / "modbus_client.py").read_text(encoding="utf-8")
    assert "return [sig for sig in table.signals if not sig.facade]" in source
    assert "La lectura periódica no incluye la zona y*" not in source
    assert "feedback oficial" in source


def test_ui_has_sca_tables_and_two_injection_tables():
    html = (SERVICE_APP / "static/index.html").read_text(encoding="utf-8")
    js = (SERVICE_APP / "static/app.js").read_text(encoding="utf-8")

    assert "Mapa Modbus de producción" not in html
    assert "sca-table-grid" in html
    assert "analog-injection-body" in html
    assert "digital-injection-body" in html
    assert "facade-body" not in html
    assert "/api/injection" in js
    assert "scaTableOrder" in js
    assert "SCA - lectura AN [0]" not in html  # se renderiza desde config/API


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
    assert "COPY trasvase-tester ./trasvase-tester" in app_dockerfile
    assert "COPY field-emulator ./field-emulator" in field_emulator_dockerfile


def test_pump_assets_are_packaged():
    asset_dir = SERVICE_APP / "static/assets"
    assert (asset_dir / "pump_gray.png").exists()
    assert (asset_dir / "pump_red.png").exists()
    assert (asset_dir / "pump_blue.png").exists()
    assert (asset_dir / "pump_green.png").exists()


def test_mode_section_removed_and_topbar_toggle_used():
    html = (SERVICE_APP / "static/index.html").read_text(encoding="utf-8")
    js = (SERVICE_APP / "static/app.js").read_text(encoding="utf-8")
    assert "mode-card" not in html
    assert "write-mode-detail" not in html
    assert "toggleWriteMode" in js
    assert 'id="write-pill"' in html


def test_front_uses_websocket_stream_and_does_not_poll_refresh_snapshot():
    html = (SERVICE_APP / "static/index.html").read_text(encoding="utf-8")
    js = (SERVICE_APP / "static/app.js").read_text(encoding="utf-8")
    main = (SERVICE_APP / "main.py").read_text(encoding="utf-8")

    assert '/ws/stream' in js
    assert '@app.websocket("/ws/stream")' in main
    assert 'setInterval(refresh' not in js
    assert 'await refresh()' not in js
    assert 'entra por' not in html


def test_digital_injection_is_checkbox_without_extra_set_button():
    html = (SERVICE_APP / "static/index.html").read_text(encoding="utf-8")
    js = (SERVICE_APP / "static/app.js").read_text(encoding="utf-8")

    assert '<tbody id="digital-injection-body"></tbody>' in html
    assert '<th>Set</th><th></th>' not in html.split('digital-injection-body')[0].split('analog-injection-body')[-1]
    assert "onchange='sendInjection(\"${v.tag}\")'" in js
    assert 'if (v) updateInjectionInput(v)' not in js


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


def test_pump_cards_include_arr_emar_generation_and_specific_pills():
    js = (SERVICE_APP / "static/app.js").read_text(encoding="utf-8")
    html = (SERVICE_APP / "static/index.html").read_text(encoding="utf-8")

    assert "bB1Arndo" in Path("config/default.yaml").read_text(encoding="utf-8")
    assert "generar EMar" in js
    assert "processGenerateEmar" in js
    assert "yB${pump}EMar" in js
    assert "Automatico" in js
    assert "bB${pump}Arndo" not in js  # el tag llega agrupado como p.arr desde backend
    assert "PLC: sin datos" in html
    assert "Fuente: PLC" in html
    assert "RTU (0)" not in js
    assert "Tablero (1)" not in js


def test_logs_ui_and_api_are_present():
    html = (SERVICE_APP / "static/index.html").read_text(encoding="utf-8")
    js = (SERVICE_APP / "static/app.js").read_text(encoding="utf-8")
    main = (SERVICE_APP / "main.py").read_text(encoding="utf-8")
    assert "Diagnóstico y logs" in html
    assert "logs-view" in html
    assert "/api/logs" in js
    assert "@app.get(\"/api/logs\")" in main
    assert "@app.get(\"/api/logs/{log_name}\")" in main
    assert "@app.get(\"/api/diagnostics\")" in main
    assert "Ver diagnóstico" in html
    assert "Recargar archivo" in html
    assert "Listar logs" not in html


def test_ui_controls_each_read_function_code_and_sample_rate():
    html = (SERVICE_APP / "static/index.html").read_text(encoding="utf-8")
    js = (SERVICE_APP / "static/app.js").read_text(encoding="utf-8")
    main = (SERVICE_APP / "main.py").read_text(encoding="utf-8")

    for function_code in ("01", "02", "03", "04"):
        assert f'id="fc-toggle-{function_code}"' in html
        assert f'id="fc-rate-{function_code}"' in html
    assert 'value="2000"' in html
    assert "toggleFunctionCode" in js
    assert "setFunctionSampleRate" in js
    assert "api/modbus-polling" in js
    assert '@app.get("/api/modbus-polling")' in main
    assert '@app.put("/api/modbus-polling/{function_code}")' in main


def test_sca_window_title_shows_modbus_details():
    js = (SERVICE_APP / "static/app.js").read_text(encoding="utf-8")
    css = (SERVICE_APP / "static/styles.css").read_text(encoding="utf-8")

    assert "modbusTitleMeta" in js
    assert "FC${fc}" in js
    assert "inicio ${startRef}" in js
    assert "offset ${startPdu}" in js
    assert "prod 0..${lastProdRow}" in js
    assert "window-modbus-meta" in js
    assert ".window-modbus-meta" in css


def test_compose_waits_for_web_health_before_field_emulator():
    compose = Path("docker-compose.yml").read_text(encoding="utf-8")
    assert "healthcheck:" in compose
    assert "/api/health" in compose
    assert "condition: service_healthy" in compose
    # El web no debe depender del emulador: el emulador consume la API web.
    assert "trasvase-tester:\n    build:" in compose
