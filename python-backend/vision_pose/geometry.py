"""Face and upper-body geometry in Mac camera metres (Y down)."""

from __future__ import annotations

import math
from typing import Any, Optional

import numpy as np

from geom import normalize_degrees, unit as _unit

def rotation_about_camera_y(radians: float) -> np.ndarray:
    cosine, sine = math.cos(radians), math.sin(radians)
    return np.array([[cosine, 0.0, sine], [0.0, 1.0, 0.0], [-sine, 0.0, cosine]], dtype=float)


def calibrated_head_axes(face_rotation: np.ndarray, yaw_zero_deg: float) -> tuple[np.ndarray, np.ndarray, float]:
    """Yaw-calibrated forward/up in camera metres. Preserves pitch and roll."""
    forward_raw = _unit(face_rotation[:, 2])
    up_raw = _unit(face_rotation[:, 1])
    raw_yaw = math.atan2(float(forward_raw[0]), float(forward_raw[2]))
    stripped_forward = rotation_about_camera_y(-raw_yaw) @ forward_raw
    stripped_up = rotation_about_camera_y(-raw_yaw) @ up_raw
    if stripped_forward[2] > 0.0:
        stripped_forward = rotation_about_camera_y(math.pi) @ stripped_forward
        stripped_up = rotation_about_camera_y(math.pi) @ stripped_up
    yaw_rad = math.radians(normalize_degrees(math.degrees(raw_yaw) - yaw_zero_deg))
    forward = _unit(rotation_about_camera_y(-yaw_rad) @ stripped_forward)
    up = rotation_about_camera_y(-yaw_rad) @ stripped_up
    up = up - float(np.dot(up, forward)) * forward
    if float(np.linalg.norm(up)) < 1e-6:
        up = np.array([0.0, -1.0, 0.0]) - float(np.dot(np.array([0.0, -1.0, 0.0]), forward)) * forward
    up = _unit(up)
    if float(np.dot(up, np.array([0.0, -1.0, 0.0]))) < 0.0:
        up = -up
    return forward, up, yaw_rad

POSE_NOSE = 0
POSE_LEFT_EAR = 7
POSE_RIGHT_EAR = 8
POSE_LEFT_SHOULDER = 11
POSE_RIGHT_SHOULDER = 12
POSE_LEFT_WRIST = 15
POSE_RIGHT_WRIST = 16
SHOULDER_WIDTH_M = 0.38
# Wrist depth may reuse the face while that mesh is still the current sample.
# A lost face must not keep the body on the last near distance.
FACE_DEPTH_HOLD_MS = 100.0
POSE_HEAD_HOLD_MS = 400.0
# Nose shift along the shoulders below this is "still facing the camera".
FRONTAL_NOSE_LATERAL_M = 0.04
# Far end of the distance where a forward-facing face mesh still holds.
# A loss past this is "step closer".
FACE_FAR_M = 1.6
# Nose shift large enough to name which way to turn back toward the camera.
CUE_SIDE_LATERAL_M = 0.06
# Last face yaw at or beyond this means the mesh died by turning.
# Face tracking is aimed at about ±60°.
FACE_LOSS_YAW_RAD = math.radians(30.0)
FACE_CUE_AFTER_MS = 250.0
# Once a cue is spoken, keep it through the sentence. The longest clip is step closer.
FACE_CUE_HOLD_MS = 1000.0
POSE_PREVIEW_EDGES = (
    (11, 12),
    (11, 13),
    (13, 15),
    (12, 14),
    (14, 16),
    (11, 23),
    (12, 24),
    (23, 24),
    (0, 11),
    (0, 12),
)
SKELETON_JOINTS = tuple(sorted({index for edge in POSE_PREVIEW_EDGES for index in edge}))


def landmark_in_frame_score(landmark: Any) -> float:
    """Visibility × presence, or -1 if the point is off-screen / occluded."""
    if landmark is None:
        return -1.0
    visibility = 1.0 if landmark.visibility is None else float(landmark.visibility)
    presence = 1.0 if landmark.presence is None else float(landmark.presence)
    if visibility < 0.4 or presence < 0.4:
        return -1.0
    if not (0.02 < float(landmark.x) < 0.98 and 0.02 < float(landmark.y) < 0.98):
        return -1.0
    return visibility * presence


def skeleton_points(landmarks: Any, width: int, height: int, fx: float, depth_m: float) -> list[dict[str, Any]]:
    """Upper-body joints in Mac camera metres, using the same depth model as the wrist."""
    nose = landmarks[POSE_NOSE]
    image_width_m = depth_m * width / fx
    points: list[dict[str, Any]] = []
    for index in SKELETON_JOINTS:
        landmark = landmarks[index]
        visibility = 1.0 if landmark.visibility is None else float(landmark.visibility)
        z_m = depth_m + (float(landmark.z) - float(nose.z)) * image_width_m
        z_m = max(0.25, min(4.5, z_m))
        xyz = unproject_normalized_landmark(landmark, z_m, width, height, fx)
        points.append({
            "i": index,
            "x": round(float(xyz[0]), 4),
            "y": round(float(xyz[1]), 4),
            "z": round(float(xyz[2]), 4),
            "v": 1 if visibility >= 0.3 else 0,
        })
    return points


def unproject_normalized_landmark(landmark: Any, z_m: float, width: int, height: int, fx: float) -> np.ndarray:
    return np.array(
        [
            ((float(landmark.x) * width - width / 2.0) / fx) * z_m,
            ((float(landmark.y) * height - height / 2.0) / fx) * z_m,
            z_m,
        ]
    )


def face_loss_cue(lateral: float, one_ear: bool, depth_m: float) -> str:
    """Shoulder-and-nose reading. Empty when the body does not explain the loss.

    The side is the player's own left or right. Positive lateral is the player's right.
    """
    if one_ear or abs(lateral) >= FRONTAL_NOSE_LATERAL_M:
        if lateral >= CUE_SIDE_LATERAL_M:
            return "turn-right"
        if lateral <= -CUE_SIDE_LATERAL_M:
            return "turn-left"
        return "turn"
    if depth_m >= FACE_FAR_M:
        return "far"
    return ""


def explain_face_loss(
    body_cue: str,
    yaw_rad: float,
    face_depth_m: Optional[float],
    body_depth_m: Optional[float],
) -> str:
    """Combine the last face with the current shoulders.

    The last face yaw only decides that the loss was a turn, and only while the
    shoulders still look turned. Which side is the shoulder cue. A
    forward-facing loss past FACE_FAR_M is distance, so a noisy shoulder offset
    does not become a turn.
    """
    yaw_turned = abs(yaw_rad) >= FACE_LOSS_YAW_RAD
    body_turned = body_cue in ("turn-left", "turn-right", "turn")
    if yaw_turned and body_turned:
        return body_cue
    face_far = face_depth_m is not None and face_depth_m >= FACE_FAR_M
    # Ignore shoulder distance while the shoulders themselves say "turned":
    # a yawed torso shortens the span and looks farther than it is.
    body_far = body_depth_m is not None and body_depth_m >= FACE_FAR_M and not body_turned
    if face_far or body_far:
        return "far"
    if body_turned:
        return ""
    return body_cue


def face_loss_cue_from_landmarks(landmarks: Any, width: int, height: int, fx: float) -> Optional[tuple[str, float]]:
    """Prompt when the face mesh is gone but the shoulders and nose remain.

    The head pose is left on the last face. Returns the shoulder cue and the
    shoulder-span distance in metres.
    """
    if landmarks is None or len(landmarks) <= POSE_RIGHT_SHOULDER:
        return None
    nose = landmarks[POSE_NOSE]
    left = landmarks[POSE_LEFT_SHOULDER]
    right = landmarks[POSE_RIGHT_SHOULDER]
    if (
        landmark_in_frame_score(nose) < 0
        or landmark_in_frame_score(left) < 0
        or landmark_in_frame_score(right) < 0
    ):
        return None
    span = math.hypot((float(right.x) - float(left.x)) * width, (float(right.y) - float(left.y)) * height)
    if span < 8.0 or fx <= 1e-6:
        return None
    depth = max(0.35, min(4.0, (SHOULDER_WIDTH_M * fx) / span))
    image_width_m = depth * width / fx

    def place(landmark: Any) -> np.ndarray:
        z_m = depth + (float(landmark.z) - float(nose.z)) * image_width_m
        z_m = max(0.25, min(4.5, z_m))
        return unproject_normalized_landmark(landmark, z_m, width, height, fx)

    nose_p = place(nose)
    left_p = place(left)
    right_p = place(right)
    across = right_p - left_p
    if float(np.linalg.norm(across)) < 1e-4:
        return None
    # Person's right, flipped so a chest facing the camera keeps the same sign.
    normal = np.cross(np.array([0.0, -1.0, 0.0]), across)
    if float(np.linalg.norm(normal)) >= 1e-4 and float(normal[2]) > 0.0:
        across = -across
    lateral = float(np.dot(nose_p - (left_p + right_p) * 0.5, _unit(across)))
    one_ear = (landmark_in_frame_score(landmarks[POSE_LEFT_EAR]) >= 0) != (
        landmark_in_frame_score(landmarks[POSE_RIGHT_EAR]) >= 0
    )
    return face_loss_cue(lateral, one_ear, depth), depth
