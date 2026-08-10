from __future__ import annotations

from dataclasses import asdict, dataclass
from pathlib import Path
from threading import Lock
from typing import Any

DISABLED = "disabled"
ENABLED = "enabled"
VALID_INJECTION_MODES = {DISABLED, ENABLED}
DEFAULT_INJECTION_MODE_PATH = Path(__file__).resolve().parents[2] / "runtime" / "injection_mode.txt"


@dataclass(frozen=True)
class InjectionModeSnapshot:
    mode: str
    enabled: bool
    path: str
    error: str | None = None


class InjectionModeStore:
    """Persiste exclusivamente la habilitacion de tags y*."""

    def __init__(
        self,
        *,
        path: str | Path | None = None,
    ):
        self.path = Path(path) if path is not None else DEFAULT_INJECTION_MODE_PATH
        self._lock = Lock()
        with self._lock:
            self._ensure_file_unlocked()

    def _ensure_file_unlocked(self) -> None:
        self.path.parent.mkdir(parents=True, exist_ok=True)
        if not self.path.exists():
            self._persist_mode_unlocked(DISABLED)

    def _persist_mode_unlocked(self, mode: str) -> None:
        tmp = self.path.with_suffix(self.path.suffix + ".tmp")
        tmp.write_text(f"{mode}\n", encoding="utf-8")
        tmp.replace(self.path)

    def _read_mode_unlocked(self) -> tuple[str, str | None]:
        try:
            raw = self.path.read_text(encoding="utf-8").strip()
        except OSError as exc:
            return DISABLED, f"No se pudo leer {self.path}: {exc}"
        mode = raw.splitlines()[0].strip() if raw else ""
        if mode in VALID_INJECTION_MODES:
            return mode, None
        return DISABLED, f"Modo invalido en {self.path}: {mode!r}"

    def _snapshot_unlocked(self) -> InjectionModeSnapshot:
        self._ensure_file_unlocked()
        mode, error = self._read_mode_unlocked()

        return InjectionModeSnapshot(
            mode=mode,
            enabled=mode == ENABLED,
            path=str(self.path),
            error=error,
        )

    def is_enabled(self) -> bool:
        return bool(self.snapshot()["enabled"])

    def snapshot(self) -> dict[str, Any]:
        with self._lock:
            return asdict(self._snapshot_unlocked())

    def set_mode(self, mode: str) -> dict[str, Any]:
        normalized = mode.strip()
        if normalized not in VALID_INJECTION_MODES:
            valid = ", ".join(sorted(VALID_INJECTION_MODES))
            raise ValueError(f"Modo de inyeccion invalido: {mode!r}. Validos: {valid}")

        with self._lock:
            self._ensure_file_unlocked()
            self._persist_mode_unlocked(normalized)
            return asdict(self._snapshot_unlocked())
