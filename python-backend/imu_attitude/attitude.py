"""Complementary AHRS. Gyro in rad/s. No serial port and no camera."""

from __future__ import annotations

import math
from typing import Optional

import numpy as np

def quat_xyzw_to_rotation(x: float, y: float, z: float, w: float) -> np.ndarray:
    """Rotation matrix that maps device vectors into the IMU reference frame."""
    norm = math.sqrt(x * x + y * y + z * z + w * w) or 1.0
    x, y, z, w = x / norm, y / norm, z / norm, w / norm
    return np.array(
        [
            [1 - 2 * (y * y + z * z), 2 * (x * y - w * z), 2 * (x * z + w * y)],
            [2 * (x * y + w * z), 1 - 2 * (x * x + z * z), 2 * (y * z - w * x)],
            [2 * (x * z - w * y), 2 * (y * z + w * x), 1 - 2 * (x * x + y * y)],
        ],
        dtype=float,
    )


class ComplementaryAttitude:
    """Quaternion AHRS with gravity tilt and optional magnetic yaw correction.

    Magnetic heading is anchored to the initial horizontal direction, not north,
    like an arbitrary-heading motion reference. Gyro input is always rad/s.
    """

    def __init__(self) -> None:
        self.q = np.array([1.0, 0.0, 0.0, 0.0], dtype=float)  # w, x, y, z
        self.last_ms: Optional[float] = None
        self.mag_reference: Optional[np.ndarray] = None
        self.mag_norm_reference: Optional[float] = None
        self.mag_used = False

    def rotation(self) -> np.ndarray:
        w, x, y, z = self.q
        return quat_xyzw_to_rotation(x, y, z, w)

    def set_from_xyzw(self, x: float, y: float, z: float, w: float) -> np.ndarray:
        norm = math.sqrt(x * x + y * y + z * z + w * w) or 1.0
        self.q = np.array([w / norm, x / norm, y / norm, z / norm], dtype=float)
        self.mag_reference = None
        self.mag_norm_reference = None
        self.mag_used = False
        return self.rotation()

    def magnetic_feedback(self, magnetic: Optional[np.ndarray], gain: float) -> np.ndarray:
        """Use all three aligned magnetic axes to constrain yaw, not gravity tilt."""
        self.mag_used = False
        if magnetic is None or gain <= 0:
            return np.zeros(3)
        field = np.asarray(magnetic, dtype=float)
        if field.shape != (3,) or not np.all(np.isfinite(field)):
            return np.zeros(3)
        norm = float(np.linalg.norm(field))
        if norm < 1e-6:
            return np.zeros(3)
        # Reject gross field-strength disturbances without altering calibration.
        if self.mag_norm_reference is not None and not (0.65 <= norm / self.mag_norm_reference <= 1.5):
            return np.zeros(3)
        rotation = self.rotation()
        horizontal = (rotation @ (field / norm))[:2]
        horizontal_norm = float(np.linalg.norm(horizontal))
        if horizontal_norm < 0.1:  # Near-vertical field has no reliable heading.
            return np.zeros(3)
        horizontal = horizontal / horizontal_norm
        if self.mag_reference is None:
            self.mag_reference = horizontal.copy()
            self.mag_norm_reference = norm
        reference = self.mag_reference
        cross = horizontal[0] * reference[1] - horizontal[1] * reference[0]
        error = math.atan2(float(cross), float(np.dot(horizontal, reference)))
        self.mag_used = True
        # World Z expressed in device axes: correction changes yaw only.
        return gain * error * rotation[2, :]

    def update(
        self, gx: float, gy: float, gz: float, ax: float, ay: float, az: float,
        now_ms: float, kp: float = 1.0, *, magnetic: Optional[np.ndarray] = None,
        kp_mag: float = 0.8, initialize_tilt: bool = False,
    ) -> np.ndarray:
        self.mag_used = False
        if self.last_ms is None:
            self.last_ms = now_ms
            if initialize_tilt:
                up = np.array([ax, ay, az], dtype=float)
                norm = float(np.linalg.norm(up))
                if np.all(np.isfinite(up)) and 0.7 <= norm <= 1.3:
                    up /= norm
                    # Shortest quaternion rotating measured device up to world Z.
                    candidate = np.array([1.0 + up[2], up[1], -up[0], 0.0])
                    length = float(np.linalg.norm(candidate))
                    self.q = candidate / length if length > 1e-6 else np.array([0.0, 1.0, 0.0, 0.0])
            return self.rotation()
        dt = max(0.001, min(0.1, (now_ms - self.last_ms) / 1000.0))
        self.last_ms = now_ms
        q0, q1, q2, q3 = self.q
        acc_norm = math.sqrt(ax * ax + ay * ay + az * az)
        # Strong Arduino linear acceleration must not be treated as gravity tilt.
        tilt_trusted = 0.7 <= acc_norm <= 1.3 if initialize_tilt else acc_norm > 0.4
        if tilt_trusted:
            ax, ay, az = ax / acc_norm, ay / acc_norm, az / acc_norm
            vx = 2 * (q1 * q3 - q0 * q2)
            vy = 2 * (q0 * q1 + q2 * q3)
            vz = q0 * q0 - q1 * q1 - q2 * q2 + q3 * q3
            gx += kp * (ay * vz - az * vy)
            gy += kp * (az * vx - ax * vz)
            gz += kp * (ax * vy - ay * vx)
        if 0.7 <= acc_norm <= 1.3:
            correction = self.magnetic_feedback(magnetic, kp_mag)
            gx += float(correction[0])
            gy += float(correction[1])
            gz += float(correction[2])
        self.q = self.q + 0.5 * dt * np.array(
            [
                -q1 * gx - q2 * gy - q3 * gz,
                q0 * gx + q2 * gz - q3 * gy,
                q0 * gy - q1 * gz + q3 * gx,
                q0 * gz + q1 * gy - q2 * gx,
            ]
        )
        self.q /= np.linalg.norm(self.q) or 1.0
        return self.rotation()
