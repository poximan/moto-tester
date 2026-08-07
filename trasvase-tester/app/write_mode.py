from __future__ import annotations

from dataclasses import asdict, dataclass
from pathlib import Path
from threading import Lock
from typing import Any, Callable

from .time_provider import monotonic_seconds

READ_ONLY = "read_only"
WRITE_ENABLED = "write_enabled"
VALID_WRITE_MODES = {READ_ONLY, WRITE_ENABLED}
INTERLOCK_ARMED = "armed"
INTERLOCK_DISARMED = "disarmed"
DEFAULT_WRITE_MODE_PATH = Path(__file__).resolve().parents[2] / "runtime" / "write_mode.txt"


@dataclass(frozen=True)
class WriteModeSnapshot:
    mode: str
    write_enabled: bool
    path: str
    interlock_path: str
    interlock_armed: bool
    lease_expires_in_s: int | None
    error: str | None = None


class WriteModeStore:
    """Control fail-closed con interlock local y habilitacion temporal."""

    def __init__(
        self,
        *,
        path: str | Path | None = None,
        interlock_path: str | Path,
        lease_seconds: int,
        monotonic_provider: Callable[[], float] = monotonic_seconds,
    ):
        if lease_seconds < 60:
            raise ValueError("lease_seconds debe ser al menos 60")
        self.path = Path(path) if path is not None else DEFAULT_WRITE_MODE_PATH
        self.interlock_path = Path(interlock_path)
        self.lease_seconds = lease_seconds
        self._monotonic = monotonic_provider
        self._lease_deadline: float | None = None
        self._lock = Lock()
        with self._lock:
            self._ensure_files_unlocked()
            self._persist_mode_unlocked(READ_ONLY)

    def _ensure_files_unlocked(self) -> None:
        self.path.parent.mkdir(parents=True, exist_ok=True)
        self.interlock_path.parent.mkdir(parents=True, exist_ok=True)
        if not self.path.exists():
            self._persist_mode_unlocked(READ_ONLY)
        if not self.interlock_path.exists():
            self.interlock_path.write_text(f"{INTERLOCK_DISARMED}\n", encoding="utf-8")

    def _persist_mode_unlocked(self, mode: str) -> None:
        tmp = self.path.with_suffix(self.path.suffix + ".tmp")
        tmp.write_text(f"{mode}\n", encoding="utf-8")
        tmp.replace(self.path)

    def _read_mode_unlocked(self) -> tuple[str, str | None]:
        try:
            raw = self.path.read_text(encoding="utf-8").strip()
        except OSError as exc:
            return READ_ONLY, f"No se pudo leer {self.path}: {exc}"
        mode = raw.splitlines()[0].strip() if raw else ""
        if mode in VALID_WRITE_MODES:
            return mode, None
        return READ_ONLY, f"Modo invalido en {self.path}: {mode!r}"

    def _read_interlock_unlocked(self) -> tuple[bool, str | None]:
        try:
            raw = self.interlock_path.read_text(encoding="utf-8").strip()
        except OSError as exc:
            return False, f"No se pudo leer {self.interlock_path}: {exc}"
        value = raw.splitlines()[0].strip() if raw else ""
        if value == INTERLOCK_ARMED:
            return True, None
        if value == INTERLOCK_DISARMED:
            return False, None
        return False, f"Interlock invalido en {self.interlock_path}: {value!r}"

    def _snapshot_unlocked(self) -> WriteModeSnapshot:
        self._ensure_files_unlocked()
        mode, mode_error = self._read_mode_unlocked()
        interlock_armed, interlock_error = self._read_interlock_unlocked()
        error = mode_error or interlock_error
        remaining: int | None = None

        if mode == WRITE_ENABLED:
            if not interlock_armed:
                error = error or "Interlock local desarmado; cierre automatico en read_only"
                self._persist_mode_unlocked(READ_ONLY)
                self._lease_deadline = None
                mode = READ_ONLY
            elif self._lease_deadline is None:
                error = error or "Habilitacion sin lease vigente; cierre automatico en read_only"
                self._persist_mode_unlocked(READ_ONLY)
                mode = READ_ONLY
            else:
                remaining_float = self._lease_deadline - self._monotonic()
                if remaining_float <= 0:
                    error = error or "Lease de escritura vencido; cierre automatico en read_only"
                    self._persist_mode_unlocked(READ_ONLY)
                    self._lease_deadline = None
                    mode = READ_ONLY
                else:
                    remaining = max(1, int(remaining_float))

        return WriteModeSnapshot(
            mode=mode,
            write_enabled=mode == WRITE_ENABLED,
            path=str(self.path),
            interlock_path=str(self.interlock_path),
            interlock_armed=interlock_armed,
            lease_expires_in_s=remaining,
            error=error,
        )

    def get_mode(self) -> str:
        return str(self.snapshot()["mode"])

    def is_write_enabled(self) -> bool:
        return bool(self.snapshot()["write_enabled"])

    def snapshot(self) -> dict[str, Any]:
        with self._lock:
            return asdict(self._snapshot_unlocked())

    def set_mode(self, mode: str) -> dict[str, Any]:
        normalized = mode.strip()
        if normalized not in VALID_WRITE_MODES:
            valid = ", ".join(sorted(VALID_WRITE_MODES))
            raise ValueError(f"Modo de escritura invalido: {mode!r}. Validos: {valid}")

        with self._lock:
            self._ensure_files_unlocked()
            if normalized == WRITE_ENABLED:
                interlock_armed, interlock_error = self._read_interlock_unlocked()
                if interlock_error is not None:
                    raise PermissionError(interlock_error)
                if not interlock_armed:
                    raise PermissionError(
                        f"Interlock local desarmado en {self.interlock_path}; se requiere el valor armed"
                    )
                self._lease_deadline = self._monotonic() + self.lease_seconds
            else:
                self._lease_deadline = None
            self._persist_mode_unlocked(normalized)
            return asdict(self._snapshot_unlocked())
