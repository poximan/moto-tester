from moto_time import clock

def monotonic_seconds() -> float:
    return clock.monotonic_seconds()
