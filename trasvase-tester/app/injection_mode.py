from __future__ import annotations

from dataclasses import asdict, dataclass
from pathlib import Path
from threading import Lock
from typing import Any, Callable

from .time_provider import monotonic_seconds

DISABLED = "disabled"
ENABLED = "enabled"
VALID_INJECTION_MODES = {DISABLED, ENABLED}
DEFAULT_INJECTION_MODE_PATH = Path(__file__).resolve().parents[2] / "runtime" / "injection_mode.txt"


@dataclass(frozen=True)
class InjectionModeSnapshot:
    mode: str
    enabled: bool
    path: str
    lease_expires_in_s: int | None
    error: str | None = None


class InjectionModeStore:
    """Gobierna exclusivamente la habilitacion temporal de tags y*."""

    def __init__(
        self,
        *,
        path: str | Path | None = None,
        lease_seconds: int,
        monotonic_provider: Callable[[], float] = monotonic_seconds,
    ):
        if lease_seconds < 60:
            raise ValueError("lease_seconds debe ser al menos 60")
        self.path = Path(path) if path is not None else DEFAULT_INJECTION_MODE_PATH
        self.lease_seconds = lease_seconds
        self._monotonic = monotonic_provider
        self._lease_deadline: float | None = None
        self._lock = Lock()
        with self._lock:
            self._ensure_file_unlocked()
            self._persist_mode_unlocked(DISABLED)

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
        remaining: int | None = None

        if mode == ENABLED:
            if self._lease_deadline is None:
                error = error or "Habilitacion sin lease vigente; cierre automatico en disabled"
                self._persist_mode_unlocked(DISABLED)
                mode = DISABLED
            else:
                remaining_float = self._lease_deadline - self._monotonic()
                if remaining_float <= 0:
                    error = error or "Lease de inyeccion vencido; cierre automatico en disabled"
                    self._persist_mode_unlocked(DISABLED)
                    self._lease_deadline = None
                    mode = DISABLED
                else:
                    remaining = max(1, int(remaining_float))

        return InjectionModeSnapshot(
            mode=mode,
            enabled=mode == ENABLED,
            path=str(self.path),
            lease_expires_in_s=remaining,
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
            if normalized == ENABLED:
                self._lease_deadline = self._monotonic() + self.lease_seconds
            else:
                self._lease_deadline = None
            self._persist_mode_unlocked(normalized)
            return asdict(self._snapshot_unlocked())
