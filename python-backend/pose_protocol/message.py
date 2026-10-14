"""unity_pose dict. Callers pass the fields; this module does not own tracking state."""

from __future__ import annotations

from typing import Any, Optional

import numpy as np

from geom import vec3


def unity_pose_message(
    *,
    timestamp_ms: float,
    head_position: Optional[np.ndarray],
    head_forward: Optional[np.ndarray],
    head_up: Optional[np.ndarray],
    head_pose_ms: Optional[float],
    now_ms: float,
    yaw_rad: float,
    head_quality: float,
    head_cue: str,
    saber: Optional[dict[str, Any]],
    angular_speed_rad_s: float,
    forward_set: bool,
    saber_reference_set: bool,
    saber_hand: str,
    skeleton: Optional[list[dict[str, Any]]],
    skeleton_ms: Optional[float],
    metrics: dict[str, Any],
) -> dict[str, Any]:
    head_age = None if head_pose_ms is None else now_ms - head_pose_ms
    head_valid = (
        head_position is not None
        and head_forward is not None
        and head_up is not None
        and head_age is not None
        and head_age <= 400.0
    )
    saber_valid = bool(saber) and saber.get("positionM") is not None
    skeleton_age = None if skeleton_ms is None else now_ms - skeleton_ms
    skeleton_fresh = skeleton is not None and skeleton_age is not None and skeleton_age <= 500.0
    pose = saber or {}
    return {
        "type": "unity_pose",
        "timestampMs": round(timestamp_ms, 3),
        "head": {
            "positionCamM": vec3(head_position) if head_position is not None else {"x": 0.0, "y": 0.0, "z": 0.0},
            "forwardCam": vec3(head_forward) if head_forward is not None else {"x": 0.0, "y": 0.0, "z": -1.0},
            "upCam": vec3(head_up) if head_up is not None else {"x": 0.0, "y": -1.0, "z": 0.0},
            "yawRad": round(yaw_rad, 5),
            "valid": head_valid,
            "quality": head_quality,
            "cue": head_cue,
        },
        "saber": {
            "handlePositionCamM": pose["positionM"] if saber_valid else {"x": 0.0, "y": 0.0, "z": 0.0},
            "bladeAxisCam": pose.get("bladeAxis", {"x": 0.0, "y": 0.0, "z": -1.0}) if saber_valid else {"x": 0.0, "y": 0.0, "z": -1.0},
            "bladeUpCam": pose.get("bladeUpCam", {"x": 1.0, "y": 0.0, "z": 0.0}) if saber_valid else {"x": 1.0, "y": 0.0, "z": 0.0},
            "angularSpeedRadS": round(angular_speed_rad_s, 4),
            "positionSource": pose.get("positionSource", "") if saber_valid else "",
            "relativeToHeadM": pose.get("relativeToHeadM", {"x": 0.0, "y": 0.0, "z": 0.0}) if saber_valid else {"x": 0.0, "y": 0.0, "z": 0.0},
            "valid": saber_valid,
            "wrist": pose.get("wrist", "") if saber_valid else "",
        },
        "calibration": {
            "forwardSet": forward_set,
            "saberReferenceSet": saber_reference_set,
            "saberHand": saber_hand,
        },
        "skeleton": {
            "valid": skeleton_fresh,
            "points": skeleton if skeleton_fresh else [],
        },
        "metrics": metrics,
    }
