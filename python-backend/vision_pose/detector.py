"""Face and Pose Landmarker. One frame in, head and upper body out."""

from __future__ import annotations

import math
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Optional

import numpy as np

from vision_pose.geometry import (
    POSE_LEFT_SHOULDER,
    POSE_LEFT_WRIST,
    POSE_NOSE,
    POSE_RIGHT_SHOULDER,
    POSE_RIGHT_WRIST,
    SHOULDER_WIDTH_M,
    calibrated_head_axes,
    face_loss_cue_from_landmarks,
    landmark_in_frame_score,
    skeleton_points,
    unproject_normalized_landmark,
)


@dataclass
class FaceFrame:
    locked: bool = False
    raw_yaw: float = 0.0
    rotation: Optional[np.ndarray] = None
    position: Optional[np.ndarray] = None
    forward: Optional[np.ndarray] = None
    up: Optional[np.ndarray] = None
    yaw_rad: float = 0.0
    quality: float = 0.0
    position_dict: Optional[dict[str, float]] = None
    observation: Optional[dict[str, Any]] = None
    preview_dots: Optional[list[tuple[int, int]]] = None


@dataclass
class PoseFrame:
    wrist_xyz: Optional[np.ndarray] = None
    wrist_name: Optional[str] = None
    overlay: Optional[dict[str, Any]] = None
    skeleton: Optional[list[dict[str, Any]]] = None
    pose_head: Optional[tuple[str, float]] = None


class VisionPose:
    def __init__(self, face_model: Path, pose_model: Optional[Path]) -> None:
        self.face_landmarker = self._create_face(face_model)
        self.pose_landmarker = self._create_pose(pose_model) if pose_model is not None else None
        self._mp: Any = None
        # detect_for_video rejects a timestamp that is not strictly greater than the last one.
        self._face_timestamp_ms = -1
        self._pose_timestamp_ms = -1

    def close(self) -> None:
        if self.face_landmarker is not None:
            self.face_landmarker.close()
        if self.pose_landmarker is not None:
            self.pose_landmarker.close()

    def _image(self, rgb: np.ndarray) -> Any:
        import mediapipe as mp
        self._mp = mp
        return mp.Image(image_format=mp.ImageFormat.SRGB, data=rgb)

    @staticmethod
    def _advance_video_timestamp(previous_ms: int, timestamp_ms: int) -> int:
        """Return a timestamp MediaPipe VIDEO mode will accept.

        Capture time is truncated to whole milliseconds, so two frames read in
        the same millisecond share a timestamp. detect_for_video treats that
        as out of order and raises ValueError.
        """
        timestamp_ms = int(timestamp_ms)
        if timestamp_ms <= previous_ms:
            return previous_ms + 1
        return timestamp_ms

    def _create_face(self, face_model: Path) -> Any:
        if not face_model.is_file():
            raise RuntimeError(f"Face model not found: {face_model}. Run run.zsh or run.ps1 once to install it.")
        try:
            from mediapipe.tasks import python as mp_python
            from mediapipe.tasks.python import vision
        except ImportError as error:
            raise RuntimeError("MediaPipe is not installed. Run run.zsh or run.ps1 once.") from error
        options = vision.FaceLandmarkerOptions(
            base_options=mp_python.BaseOptions(
                model_asset_path=str(face_model), delegate=mp_python.BaseOptions.Delegate.CPU
            ),
            running_mode=vision.RunningMode.VIDEO,
            num_faces=1,
            output_facial_transformation_matrixes=True,
        )
        return vision.FaceLandmarker.create_from_options(options)

    def _create_pose(self, pose_model: Path) -> Any:
        if not pose_model.is_file():
            raise RuntimeError(f"Pose model not found: {pose_model}. Run run.zsh or run.ps1 once to install it.")
        try:
            from mediapipe.tasks import python as mp_python
            from mediapipe.tasks.python import vision
        except ImportError as error:
            raise RuntimeError("MediaPipe is not installed. Run run.zsh or run.ps1 once.") from error
        options = vision.PoseLandmarkerOptions(
            base_options=mp_python.BaseOptions(
                model_asset_path=str(pose_model), delegate=mp_python.BaseOptions.Delegate.CPU
            ),
            running_mode=vision.RunningMode.VIDEO,
            num_poses=1,
            min_pose_detection_confidence=0.5,
            min_pose_presence_confidence=0.5,
            min_tracking_confidence=0.5,
        )
        return vision.PoseLandmarker.create_from_options(options)

    def detect_face(
        self, rgb: np.ndarray, timestamp_ms: int, width: int, height: int, fx: float, yaw_zero_deg: float,
    ) -> FaceFrame:
        from geom import orthonormalize_rotation

        timestamp_ms = self._advance_video_timestamp(self._face_timestamp_ms, timestamp_ms)
        self._face_timestamp_ms = timestamp_ms
        result = self.face_landmarker.detect_for_video(self._image(rgb), timestamp_ms)
        frame = FaceFrame()
        if not result.facial_transformation_matrixes:
            return frame
        matrix = np.asarray(result.facial_transformation_matrixes[0], dtype=float).reshape(4, 4)
        rotation = orthonormalize_rotation(matrix)
        frame.rotation = rotation
        frame.raw_yaw = math.degrees(math.atan2(float(rotation[0, 2]), float(rotation[2, 2])))
        selected = result.face_landmarks[0] if result.face_landmarks else None
        head_position: Optional[dict[str, float]] = None
        if selected is not None:
            frame.locked = True
            nose = selected[1]
            left_eye, right_eye = selected[33], selected[263]
            eye_distance_px = math.hypot((right_eye.x - left_eye.x) * width, (right_eye.y - left_eye.y) * height)
            head_z = max(0.35, min(4.0, (0.063 * fx) / max(1.0, eye_distance_px)))
            position = np.array(
                [
                    ((nose.x * width - width / 2.0) / fx) * head_z,
                    ((nose.y * height - height / 2.0) / fx) * head_z,
                    head_z,
                ]
            )
            frame.position = position
            forward, up, yaw_rad = calibrated_head_axes(rotation, yaw_zero_deg)
            frame.forward = forward
            frame.up = up
            frame.yaw_rad = yaw_rad
            frame.quality = float(len(selected))
            head_position = {
                "x": round(float(position[0]), 4),
                "y": round(float(position[1]), 4),
                "z": round(float(position[2]), 4),
            }
            frame.position_dict = head_position
            frame.preview_dots = [(int(landmark.x * width), int(landmark.y * height)) for landmark in selected[::12]]
        frame.observation = {
            "kind": "Face",
            "id": "face",
            "quality": round(float(len(selected) if selected else 0), 0),
            "center": [
                round(float(selected[1].x) * width, 1) if selected else width / 2,
                round(float(selected[1].y) * height, 1) if selected else height / 2,
            ],
            "positionM": head_position,
        }
        return frame

    def detect_pose(
        self,
        rgb: np.ndarray,
        timestamp_ms: int,
        width: int,
        height: int,
        fx: float,
        head_z: Optional[float],
        want_overlay: bool,
        hand: str,
    ) -> PoseFrame:
        if self.pose_landmarker is None:
            return PoseFrame()
        timestamp_ms = self._advance_video_timestamp(self._pose_timestamp_ms, timestamp_ms)
        self._pose_timestamp_ms = timestamp_ms
        result = self.pose_landmarker.detect_for_video(self._image(rgb), timestamp_ms)
        return self._wrist_from_pose(result, width, height, fx, head_z, want_overlay, hand)

    def _wrist_from_pose(
        self,
        pose_result: Any,
        width: int,
        height: int,
        fx: float,
        head_z: Optional[float],
        want_overlay: bool,
        hand: str,
    ) -> PoseFrame:
        frame = PoseFrame()
        if pose_result is None or not pose_result.pose_landmarks:
            return frame
        landmarks = pose_result.pose_landmarks[0]
        wrist_name, wrist = _choose_wrist(landmarks, hand)
        frame.wrist_name = wrist_name
        if want_overlay:
            frame.overlay = _preview_overlay(landmarks, width, height, wrist_name)
        depth_m = _pose_depth_m(landmarks, width, height, fx, head_z)
        if depth_m is not None:
            frame.skeleton = skeleton_points(landmarks, width, height, fx, depth_m)
        frame.pose_head = face_loss_cue_from_landmarks(landmarks, width, height, fx)
        if wrist_name is None or wrist is None or depth_m is None:
            return frame
        nose = landmarks[POSE_NOSE]
        image_width_m = depth_m * width / fx
        wrist_z = depth_m + (float(wrist.z) - float(nose.z)) * image_width_m
        wrist_z = max(0.25, min(4.5, wrist_z))
        frame.wrist_xyz = unproject_normalized_landmark(wrist, wrist_z, width, height, fx)
        return frame


def _choose_wrist(landmarks: Any, hand: str) -> tuple[Optional[str], Any]:
    left, right = landmarks[POSE_LEFT_WRIST], landmarks[POSE_RIGHT_WRIST]
    left_score, right_score = landmark_in_frame_score(left), landmark_in_frame_score(right)
    if hand == "left":
        return ("left", left) if left_score >= 0 else (None, None)
    if hand == "right":
        return ("right", right) if right_score >= 0 else (None, None)
    if left_score < 0 and right_score < 0:
        return None, None
    if left_score < 0:
        return "right", right
    if right_score < 0:
        return "left", left
    nose = landmarks[POSE_NOSE]
    left_reach = math.hypot(float(left.x) - float(nose.x), float(left.y) - float(nose.y))
    right_reach = math.hypot(float(right.x) - float(nose.x), float(right.y) - float(nose.y))
    if right_reach + 0.02 >= left_reach:
        return "right", right
    return "left", left


def _pose_depth_m(landmarks: Any, width: int, height: int, fx: float, head_z: Optional[float]) -> Optional[float]:
    if head_z is not None:
        return float(head_z)
    left, right = landmarks[POSE_LEFT_SHOULDER], landmarks[POSE_RIGHT_SHOULDER]
    span = math.hypot((float(right.x) - float(left.x)) * width, (float(right.y) - float(left.y)) * height)
    if span < 8.0:
        return None
    return max(0.35, min(4.0, (SHOULDER_WIDTH_M * fx) / span))


def _preview_overlay(landmarks: Any, width: int, height: int, wrist_name: Optional[str]) -> dict[str, Any]:
    points: list[Optional[tuple[int, int]]] = []
    for landmark in landmarks:
        visibility = 1.0 if landmark.visibility is None else float(landmark.visibility)
        if visibility < 0.3:
            points.append(None)
        else:
            points.append((int(landmark.x * width), int(landmark.y * height)))
    wrist_index = POSE_RIGHT_WRIST if wrist_name == "right" else POSE_LEFT_WRIST if wrist_name == "left" else None
    return {"points": points, "wristIndex": wrist_index, "wristName": wrist_name}
