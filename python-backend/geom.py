"""Small rotation helpers shared by vision and the saber tracker."""

from __future__ import annotations

import math

import numpy as np


def unit(vector: np.ndarray) -> np.ndarray:
    norm = float(np.linalg.norm(vector))
    return vector / (norm if norm > 1e-9 else 1.0)


def orthonormalize_rotation(matrix: np.ndarray) -> np.ndarray:
    """Remove any scale/shear before using a face transform as a rotation."""
    left, _, right_t = np.linalg.svd(matrix[:3, :3])
    rotation = left @ right_t
    if np.linalg.det(rotation) < 0:
        left[:, -1] *= -1
        rotation = left @ right_t
    return rotation


def vec3(values: np.ndarray) -> dict[str, float]:
    return {"x": round(float(values[0]), 4), "y": round(float(values[1]), 4), "z": round(float(values[2]), 4)}


def normalize_degrees(angle: float) -> float:
    return (angle + 180.0) % 360.0 - 180.0
