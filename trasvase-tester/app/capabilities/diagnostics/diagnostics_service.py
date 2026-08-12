from __future__ import annotations

from typing import Any

from ...logging_utils import log_dir, tail_file
from ...state import RuntimeState


class DiagnosticsService:
    def __init__(self, state: RuntimeState):
        self.state = state

    def events(self) -> dict[str, Any]:
        return {"events": self.state.snapshot()["events"]}

    def diagnostics(self) -> dict[str, Any]:
        snapshot = self.state.snapshot()
        return {
            "connection": snapshot["connection"],
            "injection_mode": snapshot["injection_mode"],
            "modbus_polling": snapshot["modbus_polling"],
            "controller": snapshot["controller"],
            "log_dir": str(log_dir()),
            "events": snapshot["events"][:25],
        }

    def logs(self) -> dict[str, Any]:
        base = log_dir()
        files = []
        for path in sorted(base.glob("*.log")):
            try:
                stat = path.stat()
            except OSError:
                continue
            files.append(
                {
                    "name": path.stem,
                    "filename": path.name,
                    "path": str(path),
                    "size_bytes": stat.st_size,
                    "modified_at": stat.st_mtime,
                }
            )
        return {"log_dir": str(base), "files": files}

    def read_log(self, log_name: str, lines: int) -> dict[str, Any]:
        safe_name = log_name.replace("/", "").replace(chr(92), "")
        if safe_name.endswith(".log"):
            safe_name = safe_name[:-4]
        path = log_dir() / f"{safe_name}.log"
        return {
            "name": safe_name,
            "filename": path.name,
            "path": str(path),
            "exists": path.exists(),
            "lines": tail_file(path, lines),
        }
