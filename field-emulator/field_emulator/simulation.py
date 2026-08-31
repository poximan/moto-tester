from __future__ import annotations

import math
import random
from dataclasses import asdict, dataclass
from datetime import datetime, timezone


SIMULATED_DAY_REAL_SECONDS = 60 * 60
SIMULATED_HOURS_PER_DAY = 24.0


@dataclass(frozen=True)
class SimulatedClock:
    day_index: int
    day_key: str
    hour: float
    display_time: str

    def as_dict(self) -> dict[str, int | float | str]:
        return asdict(self)


def simulated_clock(timestamp: float) -> SimulatedClock:
    day_index = int(timestamp // SIMULATED_DAY_REAL_SECONDS)
    elapsed = timestamp - day_index * SIMULATED_DAY_REAL_SECONDS
    hour = (elapsed / SIMULATED_DAY_REAL_SECONDS) * SIMULATED_HOURS_PER_DAY
    simulated_seconds = int(hour * 60 * 60) % (24 * 60 * 60)
    hh, remainder = divmod(simulated_seconds, 60 * 60)
    mm, ss = divmod(remainder, 60)
    day_start = datetime.fromtimestamp(
        day_index * SIMULATED_DAY_REAL_SECONDS,
        tz=timezone.utc,
    )
    return SimulatedClock(
        day_index=day_index,
        day_key=day_start.strftime("%Y-%m-%dT%H:00Z"),
        hour=hour,
        display_time=f"{hh:02d}:{mm:02d}:{ss:02d}",
    )


def seasonal_inlet_pct(position_pct: float) -> float:
    """Curva anual sur: verano 20, equinoccios 60 e invierno 100."""
    position = max(0.0, min(100.0, position_pct))
    if position <= 50.0:
        progress = position / 50.0
    else:
        progress = (100.0 - position) / 50.0
    return 20.0 + 80.0 * (0.5 - 0.5 * math.cos(math.pi * progress))


_DEMAND_ANCHORS = (
    (0.0, 30.0),
    (2.0, 18.0),
    (3.5, 42.0),
    (4.0, 90.0),
    (6.0, 96.0),
    (8.0, 90.0),
    (9.0, 48.0),
    (10.0, 90.0),
    (12.0, 92.0),
    (14.0, 90.0),
    (15.0, 48.0),
    (17.0, 32.0),
    (18.5, 52.0),
    (19.0, 90.0),
    (21.0, 98.0),
    (23.0, 90.0),
    (24.0, 30.0),
)


def _cosine_interpolation(left: float, right: float, progress: float) -> float:
    eased = 0.5 - 0.5 * math.cos(math.pi * progress)
    return left + (right - left) * eased


def _base_daily_demand(hour: float) -> float:
    normalized = hour % 24.0
    for (left_hour, left_value), (right_hour, right_value) in zip(
        _DEMAND_ANCHORS,
        _DEMAND_ANCHORS[1:],
    ):
        if left_hour <= normalized <= right_hour:
            progress = (normalized - left_hour) / (right_hour - left_hour)
            return _cosine_interpolation(left_value, right_value, progress)
    return _DEMAND_ANCHORS[0][1]


def _daily_variation(day_index: int) -> tuple[float, bool, float, float]:
    randomizer = random.Random(day_index * 1_000_003 + 97)
    return (
        randomizer.uniform(-4.0, 4.0),
        randomizer.random() < 0.38,
        randomizer.choice((6.0, 12.0, 21.0)),
        randomizer.uniform(8.0, 18.0),
    )


def daily_consumption_pct(hour: float, day_index: int) -> float:
    """Demanda continua y jitter determinista para un día simulado."""
    normalized_hour = hour % 24.0
    base = _base_daily_demand(normalized_hour)
    current_offset, super_consumption, selected_peak, peak_boost = _daily_variation(
        day_index
    )
    next_offset, _, _, _ = _daily_variation(day_index + 1)
    daily_offset = _cosine_interpolation(
        current_offset,
        next_offset,
        normalized_hour / 24.0,
    )

    boost = 0.0
    distance = abs((normalized_hour - selected_peak + 12.0) % 24.0 - 12.0)
    if super_consumption and distance <= 2.0:
        boost = peak_boost * (0.5 + 0.5 * math.cos(math.pi * distance / 2.0))

    return max(0.0, min(100.0, base + daily_offset + boost))
