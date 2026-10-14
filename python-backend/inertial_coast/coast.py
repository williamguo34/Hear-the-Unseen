"""Camera position is the lock. Acceleration coasts across dropped frames."""

from __future__ import annotations

import math
from typing import Optional

import numpy as np

class HandleInertial:
    """Wrist camera is the absolute lock. IMU fills frame gaps and brief occlusion."""

    def __init__(self) -> None:
        self.p: Optional[np.ndarray] = None
        self.v = np.zeros(3, dtype=float)
        self.a_bias = np.zeros(3, dtype=float)
        self.last_ms: Optional[float] = None
        self.last_cam_p: Optional[np.ndarray] = None
        self.last_cam_ms: Optional[float] = None

    def ensure(self, position: dict[str, float]) -> None:
        if self.p is None:
            self.p = np.array([position["x"], position["y"], position["z"]], dtype=float)

    def predict(self, a_cam: np.ndarray, now: float, tracking: bool, still: bool) -> None:
        if self.p is None:
            return
        if self.last_ms is None:
            self.last_ms = now
            return
        dt = (now - self.last_ms) / 1000.0
        if dt < 0.0004:
            return
        self.last_ms = now
        dt = min(0.05, dt)
        if still and float(np.linalg.norm(a_cam)) < 2.5:
            self.a_bias = 0.97 * self.a_bias + 0.03 * a_cam
        accel = a_cam - self.a_bias
        tau = 0.20 if tracking else 0.10
        self.v = self.v * math.exp(-dt / tau) + accel * dt
        max_speed = 5.0 if tracking else 3.2
        speed = float(np.linalg.norm(self.v))
        if speed > max_speed:
            self.v *= max_speed / speed
        self.p = self.p + self.v * dt

    def correct(self, p_cam: np.ndarray, captured_ms: float, now: float) -> None:
        p_cam = np.asarray(p_cam, dtype=float).reshape(3)
        if self.p is None or self.last_cam_p is None or self.last_cam_ms is None:
            self.p = p_cam.copy()
            self.v[:] = 0.0
            self.last_cam_p = p_cam.copy()
            self.last_cam_ms = captured_ms
            self.last_ms = now
            return
        dt_cam = max(0.018, min(0.25, (captured_ms - self.last_cam_ms) / 1000.0))
        v_cam = (p_cam - self.last_cam_p) / dt_cam
        delay = min(0.12, max(0.0, (now - captured_ms) / 1000.0))
        p_target = p_cam + v_cam * delay
        # One 12 Hz sample should cover most of the residual. A long gap uses a
        # harder catch-up so the handle does not spend another two samples behind.
        gain = 0.9 if captured_ms - self.last_cam_ms > 400.0 else 0.7
        self.p = self.p + gain * (p_target - self.p)
        self.v = 0.3 * self.v + 0.7 * v_cam
        self.last_cam_p = p_cam.copy()
        self.last_cam_ms = captured_ms
        self.last_ms = now

    def as_position(self) -> Optional[dict[str, float]]:
        if self.p is None:
            return None
        return {
            "x": round(float(self.p[0]), 4),
            "y": round(float(self.p[1]), 4),
            "z": round(float(self.p[2]), 4),
        }
