from __future__ import annotations

import logging
import os
from pathlib import Path


def runtime_root() -> Path:
    raw = os.getenv("RUNTIME_DIR")
    if raw:
        return Path(raw)
    # repo/trasvase-tester/app/logging_utils.py -> repo/runtime.
    return Path(__file__).resolve().parents[2] / "runtime"


def log_dir() -> Path:
    path = Path(os.getenv("LOG_DIR", str(runtime_root() / "logs")))
    path.mkdir(parents=True, exist_ok=True)
    return path


def configure_file_logger(name: str, filename: str, level: int = logging.INFO) -> logging.Logger:
    logger = logging.getLogger(name)
    logger.setLevel(level)
    logger.propagate = True

    target = log_dir() / filename
    target.parent.mkdir(parents=True, exist_ok=True)

    # Idempotente frente a reload/imports dobles de Uvicorn.
    for handler in logger.handlers:
        if isinstance(handler, logging.FileHandler) and Path(handler.baseFilename) == target:
            return logger

    handler = logging.FileHandler(target, encoding="utf-8")
    handler.setLevel(level)
    handler.setFormatter(
        logging.Formatter(
            "%(asctime)s.%(msecs)03d %(levelname)s [%(name)s] %(message)s",
            datefmt="%Y-%m-%d %H:%M:%S",
        )
    )
    logger.addHandler(handler)
    return logger


def tail_file(path: Path, max_lines: int = 300) -> list[str]:
    if max_lines < 1:
        max_lines = 1
    if max_lines > 5000:
        max_lines = 5000
    if not path.exists() or not path.is_file():
        return []
    with path.open("r", encoding="utf-8", errors="replace") as f:
        lines = f.readlines()
    return [line.rstrip("\n") for line in lines[-max_lines:]]
