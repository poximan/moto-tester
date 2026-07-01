from __future__ import annotations

from dataclasses import asdict, dataclass
from pathlib import Path
from threading import Lock

READ_ONLY = "read_only"
WRITE_ENABLED = "write_enabled"
VALID_WRITE_MODES = {READ_ONLY, WRITE_ENABLED}
DEFAULT_WRITE_MODE_PATH = Path(__file__).resolve().parents[1] / "runtime" / "write_mode.txt"


@dataclass(frozen=True)
class WriteModeSnapshot:
    mode: str
    write_enabled: bool
    path: str
    error: str | None = None


class WriteModeStore:
    """Persistencia simple del modo de escritura en un archivo de texto.

    El archivo contiene un único valor: ``read_only`` o ``write_enabled``.
    Cualquier contenido inválido falla cerrado y se interpreta como ``read_only``.
    """

    def __init__(self, path: str | Path | None = None):
        self.path = Path(path) if path is not None else DEFAULT_WRITE_MODE_PATH
        self._lock = Lock()
        self._ensure_file()

    def _ensure_file(self) -> None:
        self.path.parent.mkdir(parents=True, exist_ok=True)
        if not self.path.exists():
            self.path.write_text(f"{READ_ONLY}\n", encoding="utf-8")

    def _read_mode_unlocked(self) -> tuple[str, str | None]:
        self._ensure_file()
        try:
            raw = self.path.read_text(encoding="utf-8").strip()
        except OSError as exc:
            return READ_ONLY, f"No se pudo leer {self.path}: {exc}"

        mode = raw.splitlines()[0].strip() if raw else ""
        if mode in VALID_WRITE_MODES:
            return mode, None
        return READ_ONLY, f"Modo inválido en {self.path}: {mode!r}. Falla cerrado en read_only."

    def get_mode(self) -> str:
        with self._lock:
            mode, _error = self._read_mode_unlocked()
            return mode

    def is_write_enabled(self) -> bool:
        return self.get_mode() == WRITE_ENABLED

    def snapshot(self) -> dict[str, str | bool | None]:
        with self._lock:
            mode, error = self._read_mode_unlocked()
            return asdict(
                WriteModeSnapshot(
                    mode=mode,
                    write_enabled=mode == WRITE_ENABLED,
                    path=str(self.path),
                    error=error,
                )
            )

    def set_mode(self, mode: str) -> dict[str, str | bool | None]:
        normalized = mode.strip()
        if normalized not in VALID_WRITE_MODES:
            valid = ", ".join(sorted(VALID_WRITE_MODES))
            raise ValueError(f"Modo de escritura inválido: {mode!r}. Válidos: {valid}")

        with self._lock:
            self._ensure_file()
            tmp = self.path.with_suffix(self.path.suffix + ".tmp")
            tmp.write_text(f"{normalized}\n", encoding="utf-8")
            tmp.replace(self.path)
            return asdict(
                WriteModeSnapshot(
                    mode=normalized,
                    write_enabled=normalized == WRITE_ENABLED,
                    path=str(self.path),
                    error=None,
                )
            )
