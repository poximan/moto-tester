from __future__ import annotations

import json
import re
from pathlib import Path
from threading import Lock
from typing import Any, Literal, cast


EmarMode = Literal["disabled", "automatic", "forced"]
EMAR_DISABLED: EmarMode = "disabled"
EMAR_AUTOMATIC: EmarMode = "automatic"
EMAR_FORCED: EmarMode = "forced"
VALID_EMAR_MODES = {EMAR_DISABLED, EMAR_AUTOMATIC, EMAR_FORCED}
DEFAULT_PUMP_CONTROL_PATH = (
    Path(__file__).resolve().parents[2] / "runtime" / "pump_controls.json"
)
PUMP_RTU_TAG = re.compile(r"^yB(?P<pump>[1-5])RTU$")
PUMP_EMAR_TAG = re.compile(r"^yB(?P<pump>[1-5])EMar$")


def _default_controls() -> dict[str, dict[str, bool | EmarMode]]:
    return {
        str(pump): {"rtu": False, "emar_mode": EMAR_DISABLED}
        for pump in range(1, 6)
    }


class PumpControlStore:
    """Persiste las posiciones compartidas de los controles de bomba."""

    def __init__(self, path: str | Path | None = None):
        self.path = Path(path) if path is not None else DEFAULT_PUMP_CONTROL_PATH
        self._lock = Lock()
        self._controls = self._load_or_create()

    def _load_or_create(self) -> dict[str, dict[str, bool | EmarMode]]:
        self.path.parent.mkdir(parents=True, exist_ok=True)
        if not self.path.exists():
            controls = _default_controls()
            self._write_unlocked(controls)
            return controls
        try:
            payload = json.loads(self.path.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError) as exc:
            raise ValueError(f"Controles de bomba invalidos en {self.path}: {exc}") from exc
        return self._validate(payload)

    @staticmethod
    def _validate(payload: Any) -> dict[str, dict[str, bool | EmarMode]]:
        expected_pumps = {str(pump) for pump in range(1, 6)}
        if not isinstance(payload, dict) or set(payload) != expected_pumps:
            raise ValueError("Los controles deben definir exactamente las bombas 1 a 5")
        controls: dict[str, dict[str, bool | EmarMode]] = {}
        for pump in sorted(expected_pumps):
            item = payload[pump]
            if not isinstance(item, dict) or set(item) != {"rtu", "emar_mode"}:
                raise ValueError(f"La bomba {pump} debe definir rtu y emar_mode")
            if not isinstance(item["rtu"], bool):
                raise ValueError(f"El control rtu de la bomba {pump} debe ser booleano")
            mode = item["emar_mode"]
            if not isinstance(mode, str) or mode not in VALID_EMAR_MODES:
                valid = ", ".join(sorted(VALID_EMAR_MODES))
                raise ValueError(f"emar_mode de la bomba {pump} debe ser uno de: {valid}")
            controls[pump] = {
                "rtu": item["rtu"],
                "emar_mode": cast(EmarMode, mode),
            }
        return controls

    def _write_unlocked(
        self,
        controls: dict[str, dict[str, bool | EmarMode]],
    ) -> None:
        tmp = self.path.with_suffix(self.path.suffix + ".tmp")
        tmp.write_text(
            json.dumps(controls, ensure_ascii=False, indent=2) + "\n",
            encoding="utf-8",
        )
        tmp.replace(self.path)

    def initial_values(self) -> dict[str, bool]:
        with self._lock:
            values = {
                f"yB{pump}RTU": bool(item["rtu"])
                for pump, item in self._controls.items()
            }
            values.update(
                {
                    f"yB{pump}EMar": item["emar_mode"] == EMAR_FORCED
                    for pump, item in self._controls.items()
                }
            )
            return values

    def emar_modes(self) -> dict[int, EmarMode]:
        with self._lock:
            return {
                int(pump): cast(EmarMode, item["emar_mode"])
                for pump, item in self._controls.items()
            }

    def update_rtu_tags(self, values: dict[str, bool | int]) -> None:
        updates: list[tuple[str, bool]] = []
        for tag, value in values.items():
            match = PUMP_RTU_TAG.fullmatch(tag)
            if match is not None:
                updates.append((match.group("pump"), bool(value)))
        if not updates:
            return

        with self._lock:
            next_controls = {
                pump: dict(item) for pump, item in self._controls.items()
            }
            for pump, value in updates:
                next_controls[pump]["rtu"] = value
            self._write_unlocked(next_controls)
            self._controls = next_controls

    def set_emar_mode(self, pump_id: int, mode: str) -> EmarMode:
        if pump_id < 1 or pump_id > 5:
            raise KeyError("pump_id debe estar entre 1 y 5")
        if mode not in VALID_EMAR_MODES:
            valid = ", ".join(sorted(VALID_EMAR_MODES))
            raise ValueError(f"Modo EMar invalido: {mode!r}. Validos: {valid}")
        normalized = cast(EmarMode, mode)
        with self._lock:
            next_controls = {
                pump: dict(item) for pump, item in self._controls.items()
            }
            next_controls[str(pump_id)]["emar_mode"] = normalized
            self._write_unlocked(next_controls)
            self._controls = next_controls
        return normalized
