from __future__ import annotations

import csv
import threading
import time
from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Any

from .simulation import SIMULATED_DAY_REAL_SECONDS, simulated_clock


CSV_HEADER = (
    "timestamp_real",
    "simulated_day_index",
    "simulated_hour",
    "chamber_level",
    "reserve_level",
)


@dataclass(frozen=True)
class LevelHistoryPoint:
    timestamp_real: float
    simulated_day_index: int
    simulated_hour: float
    chamber_level: float
    reserve_level: float

    def as_dict(self) -> dict[str, float | int]:
        return asdict(self)


class LevelHistoryStore:
    def __init__(
        self,
        path: Path,
        sample_interval_s: float = 30.0,
        retention_simulated_days: int = 180,
    ) -> None:
        self.path = path
        self.sample_interval_s = max(1.0, sample_interval_s)
        self.retention_simulated_days = max(1, retention_simulated_days)
        self.retention_real_s = self.retention_simulated_days * SIMULATED_DAY_REAL_SECONDS
        self._lock = threading.RLock()
        self._points: list[LevelHistoryPoint] = []
        self._revision = 0
        self._last_compaction_at = 0.0
        self._load()

    def _load(self) -> None:
        if not self.path.exists():
            return
        try:
            with self.path.open("r", encoding="utf-8", newline="") as handle:
                reader = csv.DictReader(handle)
                self._points = [
                    LevelHistoryPoint(
                        timestamp_real=float(row["timestamp_real"]),
                        simulated_day_index=int(row["simulated_day_index"]),
                        simulated_hour=float(row["simulated_hour"]),
                        chamber_level=float(row["chamber_level"]),
                        reserve_level=float(row["reserve_level"]),
                    )
                    for row in reader
                ]
            if self._points:
                if self._trim(time.time()):
                    self._rewrite()
                self._revision = len(self._points)
        except (OSError, KeyError, TypeError, ValueError, csv.Error):
            self._points = []
            try:
                self._rewrite()
            except OSError:
                pass

    def record(self, timestamp: float, chamber_level: float, reserve_level: float) -> bool:
        with self._lock:
            if self._points and timestamp - self._points[-1].timestamp_real < self.sample_interval_s:
                return False
            clock = simulated_clock(timestamp)
            point = LevelHistoryPoint(
                timestamp_real=timestamp,
                simulated_day_index=clock.day_index,
                simulated_hour=clock.hour,
                chamber_level=chamber_level,
                reserve_level=reserve_level,
            )
            self._append(point)
            self._points.append(point)
            self._revision += 1
            removed = self._trim(timestamp)
            if removed and timestamp - self._last_compaction_at >= SIMULATED_DAY_REAL_SECONDS:
                self._rewrite()
                self._last_compaction_at = timestamp
            return True

    def _append(self, point: LevelHistoryPoint) -> None:
        self.path.parent.mkdir(parents=True, exist_ok=True)
        needs_header = not self.path.exists() or self.path.stat().st_size == 0
        with self.path.open("a", encoding="utf-8", newline="") as handle:
            writer = csv.writer(handle)
            if needs_header:
                writer.writerow(CSV_HEADER)
            writer.writerow(
                (
                    f"{point.timestamp_real:.3f}",
                    point.simulated_day_index,
                    f"{point.simulated_hour:.6f}",
                    f"{point.chamber_level:.3f}",
                    f"{point.reserve_level:.3f}",
                )
            )

    def _trim(self, timestamp: float) -> bool:
        cutoff = timestamp - self.retention_real_s
        first_valid = 0
        while first_valid < len(self._points) and self._points[first_valid].timestamp_real < cutoff:
            first_valid += 1
        if first_valid:
            del self._points[:first_valid]
            return True
        return False

    def _rewrite(self) -> None:
        self.path.parent.mkdir(parents=True, exist_ok=True)
        temporary = self.path.with_suffix(self.path.suffix + ".tmp")
        with temporary.open("w", encoding="utf-8", newline="") as handle:
            writer = csv.writer(handle)
            writer.writerow(CSV_HEADER)
            for point in self._points:
                writer.writerow(
                    (
                        f"{point.timestamp_real:.3f}",
                        point.simulated_day_index,
                        f"{point.simulated_hour:.6f}",
                        f"{point.chamber_level:.3f}",
                        f"{point.reserve_level:.3f}",
                    )
                )
        temporary.replace(self.path)

    def metadata(self) -> dict[str, Any]:
        with self._lock:
            return {
                "revision": self._revision,
                "sample_interval_s": self.sample_interval_s,
                "retention_simulated_days": self.retention_simulated_days,
                "stored_points": len(self._points),
                "file": str(self.path),
            }

    def snapshot(self, max_points: int = 2400) -> dict[str, Any]:
        with self._lock:
            points = self._downsample(self._points, max(2, max_points))
            return {
                **self.metadata(),
                "points": [point.as_dict() for point in points],
            }

    @staticmethod
    def _downsample(points: list[LevelHistoryPoint], max_points: int) -> list[LevelHistoryPoint]:
        if len(points) <= max_points:
            return list(points)
        last_index = len(points) - 1
        indexes = {
            round(slot * last_index / (max_points - 1))
            for slot in range(max_points)
        }
        return [points[index] for index in sorted(indexes)]
