from __future__ import annotations

import json
import time
from pathlib import Path
from threading import Lock
from typing import Any


FUNCTION_CODES = ("01", "02", "03", "04")
DEFAULT_SAMPLE_RATE_MS = 2000
MIN_SAMPLE_RATE_MS = 250
MAX_SAMPLE_RATE_MS = 3_600_000
DEFAULT_POLLING_CONTROL_PATH = (
    Path(__file__).resolve().parents[2] / "runtime" / "modbus_polling.json"
)


def _default_settings(sample_rate_ms: int) -> dict[str, dict[str, int | bool]]:
    return {
        function_code: {
            "enabled": True,
            "sample_rate_ms": sample_rate_ms,
        }
        for function_code in FUNCTION_CODES
    }


class PollingControlStore:
    """Configuracion persistente y estado operativo de las lecturas FC1 a FC4."""

    def __init__(
        self,
        path: str | Path | None = None,
        default_sample_rate_ms: int = DEFAULT_SAMPLE_RATE_MS,
    ):
        self.path = Path(path) if path is not None else DEFAULT_POLLING_CONTROL_PATH
        self._lock = Lock()
        self.default_sample_rate_ms = self._validate_sample_rate(default_sample_rate_ms)
        self._settings = self._load_or_create()
        self._revision = 0
        self._status: dict[str, dict[str, Any]] = {
            function_code: {
                "last_attempt_at": None,
                "last_success_at": None,
                "last_error": None,
                "poll_count": 0,
                "error_count": 0,
            }
            for function_code in FUNCTION_CODES
        }

    def _load_or_create(self) -> dict[str, dict[str, int | bool]]:
        self.path.parent.mkdir(parents=True, exist_ok=True)
        if not self.path.exists():
            settings = _default_settings(self.default_sample_rate_ms)
            self._write_unlocked(settings)
            return settings

        try:
            payload = json.loads(self.path.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError) as exc:
            raise ValueError(f"Configuracion Modbus invalida en {self.path}: {exc}") from exc
        return self._validate_settings(payload)

    @staticmethod
    def _validate_sample_rate(value: Any) -> int:
        if isinstance(value, bool):
            raise ValueError("sample_rate_ms debe ser un numero entero")
        sample_rate_ms = int(value)
        if not MIN_SAMPLE_RATE_MS <= sample_rate_ms <= MAX_SAMPLE_RATE_MS:
            raise ValueError(
                f"sample_rate_ms debe estar entre {MIN_SAMPLE_RATE_MS} y "
                f"{MAX_SAMPLE_RATE_MS} ms"
            )
        return sample_rate_ms

    @classmethod
    def _validate_settings(cls, payload: Any) -> dict[str, dict[str, int | bool]]:
        if not isinstance(payload, dict) or set(payload) != set(FUNCTION_CODES):
            expected = ", ".join(f"FC{int(fc)}" for fc in FUNCTION_CODES)
            raise ValueError(f"La configuracion debe definir exactamente {expected}")

        validated: dict[str, dict[str, int | bool]] = {}
        for function_code in FUNCTION_CODES:
            item = payload.get(function_code)
            if not isinstance(item, dict) or set(item) != {"enabled", "sample_rate_ms"}:
                raise ValueError(
                    f"FC{int(function_code)} debe definir enabled y sample_rate_ms"
                )
            enabled = item["enabled"]
            if not isinstance(enabled, bool):
                raise ValueError(f"enabled de FC{int(function_code)} debe ser booleano")
            validated[function_code] = {
                "enabled": enabled,
                "sample_rate_ms": cls._validate_sample_rate(item["sample_rate_ms"]),
            }
        return validated

    def _write_unlocked(self, settings: dict[str, dict[str, int | bool]]) -> None:
        tmp = self.path.with_suffix(self.path.suffix + ".tmp")
        tmp.write_text(
            json.dumps(settings, ensure_ascii=False, indent=2) + "\n",
            encoding="utf-8",
        )
        tmp.replace(self.path)

    @staticmethod
    def normalize_function_code(function_code: str) -> str:
        normalized = function_code.strip().upper().removeprefix("FC")
        if normalized.isdigit():
            normalized = f"{int(normalized):02d}"
        if normalized not in FUNCTION_CODES:
            raise ValueError(f"Funcion de lectura invalida: {function_code!r}")
        return normalized

    def snapshot(self) -> dict[str, Any]:
        with self._lock:
            functions = {
                function_code: {
                    **self._settings[function_code],
                    **self._status[function_code],
                }
                for function_code in FUNCTION_CODES
            }
            return {
                "path": str(self.path),
                "revision": self._revision,
                "functions": functions,
            }

    def update(
        self,
        function_code: str,
        *,
        enabled: bool | None = None,
        sample_rate_ms: int | None = None,
    ) -> dict[str, Any]:
        normalized = self.normalize_function_code(function_code)
        if enabled is None and sample_rate_ms is None:
            raise ValueError("Debe informar enabled o sample_rate_ms")

        with self._lock:
            next_settings = {
                code: dict(values) for code, values in self._settings.items()
            }
            if enabled is not None:
                if not isinstance(enabled, bool):
                    raise ValueError("enabled debe ser booleano")
                next_settings[normalized]["enabled"] = enabled
            if sample_rate_ms is not None:
                next_settings[normalized]["sample_rate_ms"] = self._validate_sample_rate(
                    sample_rate_ms
                )
            self._write_unlocked(next_settings)
            self._settings = next_settings
            self._revision += 1
            return {
                "function_code": normalized,
                **self._settings[normalized],
                **self._status[normalized],
                "revision": self._revision,
                "path": str(self.path),
            }

    def mark_attempt(self, function_code: str) -> None:
        normalized = self.normalize_function_code(function_code)
        with self._lock:
            item = self._status[normalized]
            item["last_attempt_at"] = time.time()
            item["poll_count"] += 1

    def mark_success(self, function_code: str) -> None:
        normalized = self.normalize_function_code(function_code)
        with self._lock:
            item = self._status[normalized]
            item["last_success_at"] = time.time()
            item["last_error"] = None

    def mark_error(self, function_code: str, error: str) -> None:
        normalized = self.normalize_function_code(function_code)
        with self._lock:
            item = self._status[normalized]
            item["last_error"] = error
            item["error_count"] += 1
