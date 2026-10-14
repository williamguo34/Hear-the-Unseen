"""Monotonic milliseconds shared by the tracker and the IMU readers."""

import time


def now_ms() -> float:
    return time.perf_counter_ns() / 1_000_000.0
