#!/usr/bin/env python3
"""Local face/pose + IMU tracker for Hear the Unseen.

Camera capture, MediaPipe, and the browser stay on this computer. Unity receives
the same pose over UDP.
"""

from __future__ import annotations

import argparse
import asyncio
import json
import math
import platform
import socket
import sys
import threading
import time
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path
from typing import Any, Optional

_PY = Path(__file__).resolve().parents[1]
if str(_PY) not in sys.path:
    sys.path.insert(0, str(_PY))

from aiohttp import web
import cv2
import numpy as np

from geom import normalize_degrees, orthonormalize_rotation, unit as _unit, vec3
from imu_attitude.attitude import ComplementaryAttitude
from imu_attitude.imu_processing import MagnetometerCalibration, QMC_UT_PER_COUNT, magnetic_heading, motion_vectors
from imu_transport.osc_reader import OscHooks, OscImuReader
from imu_transport.serial_reader import SerialHooks, SerialImuReader
from inertial_coast.coast import HandleInertial
from mac_camera.choose import choose_mac_camera, print_camera_list
from pose_protocol.hub import UnityPoseHub
from pose_protocol.message import unity_pose_message
from timebase import now_ms
from vision_pose.detector import VisionPose
from vision_pose.geometry import (
    FACE_CUE_AFTER_MS,
    FACE_CUE_HOLD_MS,
    FACE_DEPTH_HOLD_MS,
    POSE_HEAD_HOLD_MS,
    POSE_PREVIEW_EDGES,
    calibrated_head_axes,
    explain_face_loss,
)

# cvtColor/resize are cheap at 640×480; extra OpenCV threads steal cores from
# MediaPipe XNNPACK and increase detect latency under contention.
cv2.setNumThreads(1)


REPO = _PY.parent
STATIC = REPO / "web" / "tracker-page"







def rotation_to_euler_degrees(rotation: np.ndarray) -> dict[str, float]:
    """Return camera-frame yaw, pitch, and roll for a rotation matrix."""
    singular = math.hypot(float(rotation[0, 0]), float(rotation[1, 0])) < 1e-6
    if singular:
        roll = math.atan2(-float(rotation[1, 2]), float(rotation[1, 1]))
        pitch = math.atan2(-float(rotation[2, 0]), math.hypot(float(rotation[0, 0]), float(rotation[1, 0])))
        yaw = 0.0
    else:
        roll = math.atan2(float(rotation[2, 1]), float(rotation[2, 2]))
        pitch = math.atan2(-float(rotation[2, 0]), math.hypot(float(rotation[0, 0]), float(rotation[1, 0])))
        yaw = math.atan2(float(rotation[1, 0]), float(rotation[0, 0]))
    return {"yawDeg": round(math.degrees(yaw), 2), "pitchDeg": round(math.degrees(pitch), 2), "rollDeg": round(math.degrees(roll), 2)}


def lan_ipv4() -> str:
    """Best-effort LAN address so TouchOSC can be pointed at this Mac."""
    probe = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
    try:
        probe.connect(("8.8.8.8", 80))
        return probe.getsockname()[0]
    except OSError:
        return "127.0.0.1"
    finally:
        probe.close()








# Blade direction in each device's local coordinate frame.  The GY-91 in the
# current saber mount has its -Y direction pointing from hilt to tip.
IPHONE_BLADE_DEVICE = np.array([0.0, 1.0, 0.0])
GY91_BLADE_DEVICE = np.array([0.0, -1.0, 0.0])



def rotation_mapping_two_vectors(
    from_a: np.ndarray, from_b: np.ndarray, to_a: np.ndarray, to_b: np.ndarray
) -> np.ndarray:
    """Rotation R with R @ from_a ≈ to_a, using from_b → to_b to fix roll."""
    fa, ta = _unit(np.asarray(from_a, dtype=float)), _unit(np.asarray(to_a, dtype=float))
    fb, tb = _unit(np.asarray(from_b, dtype=float)), _unit(np.asarray(to_b, dtype=float))
    fz = np.cross(fa, fb)
    tz = np.cross(ta, tb)
    if float(np.linalg.norm(fz)) < 1e-6 or float(np.linalg.norm(tz)) < 1e-6:
        axis = np.cross(fa, ta)
        if float(np.linalg.norm(axis)) < 1e-8:
            return np.eye(3) if float(np.dot(fa, ta)) > 0 else np.diag([1.0, -1.0, -1.0])
        axis = _unit(axis)
        cos = float(np.clip(np.dot(fa, ta), -1.0, 1.0))
        sin = math.sqrt(max(0.0, 1.0 - cos * cos))
        k = np.array([[0, -axis[2], axis[1]], [axis[2], 0, -axis[0]], [-axis[1], axis[0], 0]])
        return orthonormalize_rotation(np.eye(3) + sin * k + (1.0 - cos) * (k @ k))
    fy = np.cross(_unit(fz), fa)
    ty = np.cross(_unit(tz), ta)
    source = np.column_stack((fa, fy, _unit(fz)))
    destination = np.column_stack((ta, ty, _unit(tz)))
    return orthonormalize_rotation(destination @ source.T)




G_MS2 = 9.80665






class Tracker:
    def __init__(self, args: argparse.Namespace) -> None:
        self.args = args
        self.clients: set[web.WebSocketResponse] = set()
        self.running = True
        self.last_raw_yaw: Optional[float] = None
        self.yaw_zero = 0.0
        self.frame_number = 0
        self.fps_ema = 0.0
        self.last_frame_finished_ms: Optional[float] = None
        self.camera_error: Optional[str] = None
        self.latest_preview: Optional[bytes] = None
        self.preview_sequence = 0
        self.next_preview_ms = 0.0
        self.vision = VisionPose(
            Path(args.face_model),
            Path(args.pose_model) if args.pose_fps > 0 else None,
        )
        self.latest_saber: Optional[dict[str, Any]] = None
        self.latest_saber_ms: Optional[float] = None
        self.imu: Optional[dict[str, Any]] = None
        self.serial_reader: Optional[SerialImuReader] = None
        self.serial_error: Optional[str] = None
        self.osc_reader: Optional[OscImuReader] = None
        self.osc_error: Optional[str] = None
        self.lan_ip = lan_ipv4()
        self.last_imu_telemetry_ms = 0.0
        self.mirror_camera = args.mirror_camera
        self.last_face_position: Optional[np.ndarray] = None
        self.last_face_rotation: Optional[np.ndarray] = None
        self.last_head_pose_ms: Optional[float] = None
        self._last_face_sample_ms: Optional[float] = None
        self._pose_head_fallback: Optional[tuple[float, str, float]] = None
        self._head_cue = ""
        self._head_cue_since: Optional[float] = None
        self._face_absent_since: Optional[float] = None
        self.latest_saber_rotation: Optional[np.ndarray] = None
        self.imu_rotation: Optional[np.ndarray] = None
        self.imu_handle_position: Optional[dict[str, float]] = None
        self.last_wrist_ms: Optional[float] = None
        self.last_wrist_name: Optional[str] = None
        self.last_skeleton: Optional[list[dict[str, Any]]] = None
        self.last_skeleton_ms: Optional[float] = None
        self.handle = HandleInertial()
        self.attitude = ComplementaryAttitude()
        self.imu_lock = threading.Lock()
        self.mag_calibration = MagnetometerCalibration(
            getattr(args, "mag_calibration_file", REPO / ".cache" / "mag-calibration.json"),
            fixed_mount_angle=getattr(args, "mag_mount_angle", None))
        self.saber_reference_rotation: Optional[np.ndarray] = None
        self.saber_device_to_camera0: Optional[np.ndarray] = None
        self.pending_direction: Optional[tuple[str, int]] = None
        self._direction_token = 0
        self.forward_set = False
        self.last_head_forward: Optional[np.ndarray] = None
        self.last_head_up: Optional[np.ndarray] = None
        self.last_yaw_rad = 0.0
        self.last_head_quality = 0.0
        self.last_metrics: dict[str, Any] = {"fps": 0.0, "detectMs": 0.0, "droppedCaptureFrames": 0}
        self.unity_hub = UnityPoseHub(args.unity_host, args.unity_port, args.unity_command_port)
        self._pose_publish_lock = threading.Lock()
        self.loop: Optional[asyncio.AbstractEventLoop] = None
        self.preview_subscribers = 0
        self._frame_condition = threading.Condition()
        self._latest_frame: Optional[tuple[int, np.ndarray, float, float]] = None
        self._capture_sequence = 0
        self._rgb_buf: Optional[np.ndarray] = None
        self._fx: Optional[float] = None
        self._pose_job: Any = None
        self._next_pose_ms = 0.0
        self._pose_overlay: Optional[dict[str, Any]] = None
        self._preview_job: Any = None
        self.detect_pool = ThreadPoolExecutor(max_workers=1, thread_name_prefix="pose")
        self.preview_pool = ThreadPoolExecutor(max_workers=1, thread_name_prefix="preview")

    def emit_threadsafe(self, message: dict[str, Any]) -> None:
        """Serialize on the caller thread, then send without blocking capture/IMU."""
        if not self.clients or self.loop is None:
            return
        try:
            payload = json.dumps(message, separators=(",", ":"))
            asyncio.run_coroutine_threadsafe(self._send_payload(payload), self.loop)
        except RuntimeError:
            pass

    async def _send_payload(self, payload: str) -> None:
        dead: list[web.WebSocketResponse] = []
        for client in tuple(self.clients):
            try:
                await client.send_str(payload)
            except (ConnectionResetError, RuntimeError):
                dead.append(client)
        for client in dead:
            self.clients.discard(client)

    async def broadcast(self, message: dict[str, Any]) -> None:
        if not self.clients:
            return
        await self._send_payload(json.dumps(message, separators=(",", ":")))

    def start_serial(self) -> None:
        if not self.args.serial:
            return
        device = self.args.serial
        try:
            self.serial_reader = SerialImuReader(device, self.args.baud, SerialHooks(
                on_sample=self.ingest_imu,
                on_notice=lambda message: self.emit_threadsafe({"type": "notice", "ok": False, "message": message}),
                on_button=self.request_button_calibration,
                on_still_begin=self.notify_still_calibrating,
                on_still_done=self.finish_screen_still,
                on_gyro_reset=self.mag_calibration.reset_runtime_gyro,
                on_status=lambda: self.emit_threadsafe({"type": "sensor_status", "serial": self.imu_link()}),
                mag_status=self.mag_calibration.status,
                imu_snapshot=lambda: self.imu,
            ))
        except Exception as error:
            self.serial_error = f"Could not open Arduino serial ({device}): {error}"

    def start_osc(self) -> None:
        if not self.args.iphone:
            return
        try:
            self.osc_reader = OscImuReader(
                self.args.osc_bind,
                self.args.osc_port,
                self.args.iphone_port,
                self.args.gyro_scale,
                OscHooks(
                    on_sample=self.ingest_imu,
                    on_notice=lambda message: self.emit_threadsafe(
                        {"type": "notice", "ok": True, "message": message}
                    ),
                ),
                iphone_host=self.args.iphone_host,
            )
        except OSError as error:
            self.osc_error = f"Could not bind TouchOSC UDP {self.args.osc_bind}:{self.args.osc_port}: {error}"
        except Exception as error:
            self.osc_error = str(error)

    def imu_link(self) -> dict[str, Any]:
        if self.serial_reader is not None:
            return self.serial_reader.link_status()
        if self.osc_reader is not None and self.osc_reader.connected():
            rate = f" · {self.osc_reader.rate_hz:.0f} Hz" if self.osc_reader.rate_hz else ""
            return {
                "connected": True,
                "source": "iphone",
                "device": f"{self.osc_reader.device}{rate}",
                "error": None,
                "haptic": self.osc_reader.haptic_capable,
                "app": self.osc_reader.flavor,
            }
        waiting = f"waiting for ZIG SIM/TouchOSC → {self.lan_ip}:{self.args.osc_port}" if self.osc_reader is not None else None
        return {"connected": False, "source": None, "device": waiting, "error": self.osc_error or self.serial_error}

    def send_haptic(self) -> Optional[float]:
        if self.serial_reader is not None:
            return self.serial_reader.send_block()
        if self.osc_reader is not None:
            return self.osc_reader.send_block()
        return None

    def request_button_calibration(self) -> None:
        """Hardware button locks direction now and does not run the still window."""
        self.pending_direction = None
        self._call_on_loop(self.calibrate_from_button)

    def request_screen_calibration(self, kind: str) -> None:
        """Browser and Unity: two seconds still, then lock the requested direction."""
        self._direction_token += 1
        token = self._direction_token
        self.pending_direction = (kind, token)
        self.emit_threadsafe(
            {
                "type": "notice",
                "ok": True,
                "message": "Keep the saber still for two seconds. Direction is set after that.",
            }
        )
        firmware = self.serial_reader is not None and self.serial_reader.send_still()
        delay = 6.0 if firmware else 2.0
        if self.loop is None:
            return

        async def finish_if_current() -> None:
            await asyncio.sleep(delay)
            if self.pending_direction == (kind, token):
                self._apply_pending_direction()

        try:
            asyncio.run_coroutine_threadsafe(finish_if_current(), self.loop)
        except RuntimeError:
            pass

    def notify_still_calibrating(self) -> None:
        """Firmware is storing its own gyro bias. Do not subtract the Mac bias as well."""
        self.mag_calibration.suspend_saved_gyro()

    def finish_screen_still(self) -> None:
        self._call_on_loop(self._apply_pending_direction)

    def _call_on_loop(self, callback) -> None:
        if self.loop is None:
            return
        try:
            self.loop.call_soon_threadsafe(callback)
        except RuntimeError:
            pass

    def _apply_pending_direction(self) -> None:
        pending = self.pending_direction
        self.pending_direction = None
        if pending is None:
            return
        kind, _token = pending
        if kind == "forward":
            ok, text = self.calibrate()
        else:
            ok, text = self.calibrate_saber_reference()
        self.emit_threadsafe({"type": "notice", "ok": ok, "message": text})

    def calibrate_from_button(self) -> None:
        head_ok, head_text = self.calibrate()
        saber_ok, saber_text = self.calibrate_saber_reference()
        self.publish_unity_pose()
        self.emit_threadsafe(
            {
                "type": "notice",
                "ok": head_ok and saber_ok,
                "message": f"Direction set — head: {head_text} Saber: {saber_text}",
            }
        )

    def ingest_imu(self, sample: dict[str, float]) -> None:
        received_ms = now_ms()
        omega_rad = math.sqrt(sample["gx"] ** 2 + sample["gy"] ** 2 + sample["gz"] ** 2)
        omega_deg = omega_rad * (180.0 / math.pi)
        fused_quaternion: dict[str, float] = {}
        processed: dict[str, Any] = {}
        mag_used = False
        with self.imu_lock:
            arduino = sample.get("arduino") == 1.0
            acceleration = np.array([sample[k] for k in ("ax", "ay", "az")])
            gyro = np.array([sample[k] for k in ("gx", "gy", "gz")])
            magnetic = None
            if arduino:
                if all(key in sample for key in ("mxRaw", "myRaw", "mzRaw")):
                    raw_magnetic = np.array([sample["mxRaw"], sample["myRaw"], sample["mzRaw"]])
                    auto_saved = self.mag_calibration.add(raw_magnetic, sample.get("magDeviceUs"),
                        [sample[k] for k in ("ax", "ay", "az")], [sample[k] for k in ("gx", "gy", "gz")])
                    if auto_saved:
                        self.attitude.mag_reference = self.attitude.mag_norm_reference = None
                        self.emit_threadsafe({"type": "notice", "ok": True,
                            "message": "Sensor calibration passed and saved automatically. Point the blade toward the camera and set its reference."})
                    corrected = self.mag_calibration.apply(raw_magnetic)
                    mount = self.mag_calibration.mount_rotation()
                    if mount is not None:
                        magnetic = mount @ corrected
                    processed["magneticField"] = {
                        **dict(zip(("x", "y", "z"), map(float, (magnetic if magnetic is not None else corrected) * QMC_UT_PER_COUNT))),
                        "unit": "uT", "calibrated": self.mag_calibration.model is not None,
                        "frame": "mpu" if mount is not None else "qmc5883p",
                    }
                acceleration = self.mag_calibration.apply_acceleration(acceleration)
                gyro = self.mag_calibration.apply_rotation_rate(gyro)
                omega_deg = float(np.linalg.norm(gyro)*180/math.pi)
            if sample.get("arduino") and sample.get("streamResumed") and self.attitude.last_ms is not None:
                # Preserve orientation, but do not integrate across an outage.
                self.attitude.last_ms = received_ms
            if all(key in sample for key in ("qx", "qy", "qz", "qw")):
                self.imu_rotation = self.attitude.set_from_xyzw(sample["qx"], sample["qy"], sample["qz"], sample["qw"])
                self.attitude.last_ms = received_ms
                pose_source = "quaternion"
            else:
                grav_x = sample.get("grav_x", sample["ax"])
                grav_y = sample.get("grav_y", sample["ay"])
                grav_z = sample.get("grav_z", sample["az"])
                if arduino:
                    grav_x, grav_y, grav_z = acceleration
                fusion_magnetic = magnetic
                if getattr(self.args, "no_magnetometer", False) or (arduino and self.mag_calibration.collecting):
                    fusion_magnetic = None
                self.imu_rotation = self.attitude.update(
                    *gyro, grav_x, grav_y, grav_z,
                    received_ms, magnetic=fusion_magnetic, initialize_tilt=arduino,
                )
                mag_used = self.attitude.mag_used
                pose_source = ("ahrs-9axis" if mag_used else "ahrs-6axis") if arduino else "gyro"
                if arduino:
                    w, x, y, z = self.attitude.q
                    fused_quaternion = {"qx": float(x), "qy": float(y), "qz": float(z), "qw": float(w)}
            if arduino:
                gravity, user_accel = motion_vectors(self.imu_rotation, acceleration)
                rotation = self.imu_rotation
                heading, true_heading = (None, None)
                if magnetic is not None and mag_used:
                    heading, true_heading = magnetic_heading(rotation, magnetic, getattr(self.args, "mag_declination", None))
                processed.update({
                    "gravity": dict(zip(("x", "y", "z"), map(float, gravity))),
                    "userAcceleration": dict(zip(("x", "y", "z"), map(float, user_accel))),
                    "accelerationUnit": "g", "deviceFrame": "mpu", "gravityConvention": "down",
                    "calibratedAcceleration": dict(zip(("x", "y", "z"), map(float, acceleration))),
                    "rotationRate": dict(zip(("x", "y", "z"),map(float,gyro))),
                    "rotationRateUnit": "rad/s",
                    "attitude": {
                        "yawDeg": math.degrees(math.atan2(rotation[1, 0], rotation[0, 0])),
                        "pitchDeg": math.degrees(math.asin(float(np.clip(-rotation[2, 0], -1, 1)))),
                        "rollDeg": math.degrees(math.atan2(rotation[2, 1], rotation[2, 2])),
                    },
                    "magCalibration": self.mag_calibration.status(),
                    "magneticHeadingDeg": heading, "trueHeadingDeg": true_heading,
                    "headingAxis": "mpu+x", "headingCalibrated": heading is not None and self.mag_calibration.fitted,
                    "saturated": max(abs(sample[k]) for k in ("gx", "gy", "gz")) >= math.radians(499)
                        or max(abs(sample[k]) for k in ("ax", "ay", "az")) >= 7.99,
                })
            if self.imu_handle_position is None:
                self.imu_handle_position = self.default_handle_position()
            self.handle.ensure(self.imu_handle_position)
            tracking = self.last_wrist_ms is not None and received_ms - self.last_wrist_ms <= 280.0
            accel = self.linear_accel_camera({**sample, **processed}) if self.handle.last_cam_p is not None else np.zeros(3)
            self.handle.predict(accel, received_ms, tracking, omega_deg < 35.0)
            self.constrain_handle_reach()
            fused = self.handle.as_position()
            if fused is not None:
                self.imu_handle_position = fused
            saber = self.build_imu_saber()
            if saber is not None:
                self.latest_saber = saber
                self.latest_saber_ms = received_ms
                self.latest_saber_rotation = self.camera_saber_rotation()
        self.imu = {
            **sample,
            **fused_quaternion,
            **processed,
            "omegaDegS": omega_deg,
            "receivedMs": received_ms,
            "poseSource": pose_source,
            "magUsed": mag_used,
        }
        if received_ms - self.last_imu_telemetry_ms >= 8.0:
            self.last_imu_telemetry_ms = received_ms
            self.emit_threadsafe({"type": "imu", "imu": self.imu, "saber": self.latest_saber})
            self.publish_unity_pose()

    def magnetic_calibration_command(self, action: str) -> tuple[bool, str]:
        if not self.imu or not self.imu.get("arduino"):
            return False, "Connect the Arduino sensors first."
        with self.imu_lock:
            calibration = self.mag_calibration
            if calibration.forced_mount_angle is not None and action != "cancel":
                return False, "A fixed mounting angle was requested. Omit --mag-mount-angle to calibrate once."
            if action == "start":
                if not self.imu_fresh() or "magDeviceUs" not in self.imu:
                    return False, "Wait for both MPU and magnetometer data before calibrating."
                calibration.start(auto_save=True)
                message = "Hold still, pause on each face, then tumble slowly away from metal. Calibration saves automatically and is reused after restart."
            elif action == "finish":
                if not self.imu_fresh() or "magDeviceUs" not in self.imu:
                    return False, "Sensor data interrupted. Wait for recovery or cancel this collection."
                try:
                    calibration.finish()
                except ValueError as error:
                    return False, str(error)
                message = "Magnetic calibration and mounting alignment saved. Point the saber toward the camera and set its reference."
            elif action == "cancel":
                calibration.cancel()
                message = "Collection cancelled. Previous calibration and alignment retained, if available."
            else:
                return False, "Unknown magnetic calibration action."
            # Changing the field correction must not reuse the old heading anchor.
            self.attitude.mag_reference = None
            self.attitude.mag_norm_reference = None
            self.attitude.mag_used = False
        return True, message

    def imu_fresh(self) -> bool:
        return self.imu is not None and now_ms() - float(self.imu["receivedMs"]) <= 800.0

    def default_handle_position(self) -> dict[str, float]:
        """Stand-in handle location in camera metres. IMU does not provide xyz."""
        if self.last_face_position is not None:
            p = self.last_face_position
            return {
                "x": round(float(p[0]) + 0.18, 4),
                "y": round(float(p[1]) + 0.08, 4),
                "z": round(max(0.25, float(p[2]) * 0.72), 4),
            }
        return {"x": 0.12, "y": 0.1, "z": 0.55}

    def fresh_face_depth(self, captured_ms: float) -> Optional[float]:
        if self.last_face_position is None or self._last_face_sample_ms is None:
            return None
        if captured_ms - self._last_face_sample_ms > FACE_DEPTH_HOLD_MS:
            return None
        return float(self.last_face_position[2])

    def adopt_pose_head(self, captured_ms: float) -> None:
        """Show the face-loss prompt. The head stays on the last face pose."""
        if self._face_absent_since is None:
            self._face_absent_since = captured_ms
        desired = ""
        fallback = self._pose_head_fallback
        if fallback is not None:
            pose_ms, body_cue, body_depth = fallback
            lost_for = captured_ms - self._face_absent_since
            pose_fresh = captured_ms - pose_ms <= POSE_HEAD_HOLD_MS
            if pose_fresh and lost_for >= FACE_CUE_AFTER_MS:
                face_depth = None if self.last_face_position is None else float(self.last_face_position[2])
                if face_depth is None:
                    desired = body_cue
                else:
                    desired = explain_face_loss(body_cue, self.last_yaw_rad, face_depth, body_depth)
        self.publish_head_cue(desired, captured_ms, face_visible=False)

    def publish_head_cue(self, desired: str, now_ms: float, face_visible: bool) -> None:
        """Hold the current sentence until it would have finished.

        A flickering shoulder class must not replace or clear it. The face
        coming back clears it immediately. After the hold, a new class can
        start the next sentence.
        """
        if face_visible:
            self._head_cue = ""
            self._head_cue_since = None
            return
        if (
            self._head_cue
            and self._head_cue_since is not None
            and now_ms - self._head_cue_since < FACE_CUE_HOLD_MS
        ):
            return
        if desired == self._head_cue:
            return
        self._head_cue = desired
        self._head_cue_since = now_ms if desired else None

    def apply_wrist_position(self, wrist_xyz: np.ndarray, wrist_name: str, captured_ms: float) -> None:
        with self.imu_lock:
            self.last_wrist_ms = captured_ms
            self.last_wrist_name = wrist_name
            self.handle.correct(wrist_xyz, captured_ms, now_ms())
            self.constrain_handle_reach()
            fused = self.handle.as_position()
            if fused is not None:
                self.imu_handle_position = fused
            if self.imu_rotation is not None:
                saber = self.build_imu_saber()
            else:
                saber = self.build_pose_handle_saber(wrist_name)
            if saber is not None:
                self.latest_saber = saber
                self.latest_saber_ms = captured_ms
                self.latest_saber_rotation = self.camera_saber_rotation()

    def build_pose_handle_saber(self, wrist_name: str) -> dict[str, Any]:
        position = self.imu_handle_position or self.default_handle_position()
        return {
            "id": "pose",
            "source": "pose",
            "positionSource": "pose+imu" if self.imu_fresh() else "pose",
            "wrist": wrist_name,
            "positionM": position,
            "orientation": {"yawDeg": 0.0, "pitchDeg": 0.0, "rollDeg": 0.0},
            "bladeAxis": {"x": 0.0, "y": 0.0, "z": -1.0},
            "bladeReferenceSet": False,
        }

    def linear_accel_camera(self, sample: dict[str, Any]) -> np.ndarray:
        """Device-frame linear accel mapped into the Mac camera frame, m/s²."""
        if self.saber_device_to_camera0 is None or self.saber_reference_rotation is None:
            return np.zeros(3)
        rotation = self.camera_saber_rotation()
        if rotation is None:
            return np.zeros(3)
        if sample.get("arduino") and "userAcceleration" in sample:
            # Arduino units are known: a >4g swing is still g, not m/s².
            user = sample["userAcceleration"]
            linear = rotation @ (np.array([user["x"], user["y"], user["z"]]) * G_MS2)
            magnitude = float(np.linalg.norm(linear))
            return linear * min(1.0, 45.0 / max(magnitude, 1e-9))
        accel = np.array([sample["ax"], sample["ay"], sample["az"]], dtype=float)
        if float(np.linalg.norm(accel)) > 4.0:
            accel = accel / G_MS2
        if "grav_x" in sample:
            gravity = np.array([sample["grav_x"], sample["grav_y"], sample["grav_z"]], dtype=float)
            residual = accel - gravity
            if float(np.linalg.norm(accel)) > 0.7 and float(np.linalg.norm(residual)) <= float(np.linalg.norm(accel)) + 0.05:
                accel = residual
        elif self.imu_rotation is not None:
            gravity = self.imu_rotation.T @ np.array([0.0, 0.0, 1.0])
            accel = accel - gravity
        linear = rotation @ (accel * G_MS2)
        mag = float(np.linalg.norm(linear))
        if mag > 45.0:
            linear *= 45.0 / mag
        return linear

    def constrain_handle_reach(self) -> None:
        if self.handle.p is None or self.last_face_position is None or self.last_head_pose_ms is None:
            return
        if now_ms() - self.last_head_pose_ms > 800.0:
            return
        delta = self.handle.p - self.last_face_position
        reach = float(np.linalg.norm(delta))
        limit = 1.15
        if reach <= limit or reach < 1e-6:
            return
        self.handle.p = self.last_face_position + delta * (limit / reach)
        radial = float(np.dot(self.handle.v, delta)) / (reach * reach)
        if radial > 0.0:
            self.handle.v = self.handle.v - radial * delta

    def camera_saber_rotation(self) -> Optional[np.ndarray]:
        if self.imu_rotation is None:
            return None
        if self.saber_reference_rotation is None or self.saber_device_to_camera0 is None:
            return self.imu_rotation
        return self.saber_device_to_camera0 @ self.saber_reference_rotation.T @ self.imu_rotation

    def imu_up_in_device(self) -> np.ndarray:
        """Device-frame vector pointing toward the ceiling (opposite gravity)."""
        sample = self.imu
        if sample is not None and "grav_x" in sample:
            gravity = np.array([sample["grav_x"], sample["grav_y"], sample["grav_z"]], dtype=float)
            if float(np.linalg.norm(gravity)) > 0.2:
                return _unit(-gravity)
        if self.imu_rotation is not None:
            return _unit(self.imu_rotation.T @ np.array([0.0, 0.0, 1.0]))
        return np.array([0.0, 0.0, 1.0])

    def blade_device_axis(self) -> np.ndarray:
        """Return the configured hilt-to-tip direction for the active IMU."""
        if self.imu is not None and self.imu.get("arduino") == 1.0:
            return GY91_BLADE_DEVICE
        return IPHONE_BLADE_DEVICE

    def build_imu_saber(self) -> Optional[dict[str, Any]]:
        if self.imu_rotation is None:
            return None
        R_cam = self.camera_saber_rotation()
        assert R_cam is not None
        blade_device = self.blade_device_axis()
        if self.saber_reference_rotation is None or self.saber_device_to_camera0 is None:
            # Before calibration, IMU world is Z-up. Camera is Y-down, Z into the room.
            blade_imu = self.imu_rotation @ blade_device
            blade_axis = np.array([blade_imu[0], -blade_imu[2], -blade_imu[1]])
        else:
            blade_axis = R_cam @ blade_device
        norm = float(np.linalg.norm(blade_axis)) or 1.0
        blade_axis = blade_axis / norm
        position = self.imu_handle_position or self.default_handle_position()
        wrist_age = None if self.last_wrist_ms is None else now_ms() - self.last_wrist_ms
        if wrist_age is not None and wrist_age <= 180.0:
            position_source = "pose+imu"
        elif self.handle.last_cam_p is not None:
            position_source = "imu"
        else:
            position_source = "stand-in"
        saber: dict[str, Any] = {
            "id": "iphone",
            "source": "imu",
            "positionSource": position_source,
            "positionM": position,
            "orientation": rotation_to_euler_degrees(R_cam),
            "bladeAxis": {"x": round(float(blade_axis[0]), 4), "y": round(float(blade_axis[1]), 4), "z": round(float(blade_axis[2]), 4)},
            "bladeUpCam": vec3(self.blade_up_cam(blade_axis)),
            "bladeReferenceSet": self.saber_reference_rotation is not None,
        }
        if self.last_wrist_name and wrist_age is not None and wrist_age <= 2500.0:
            saber["wrist"] = self.last_wrist_name
        if self.last_face_position is not None and self.last_face_rotation is not None and self.last_head_pose_ms is not None:
            if now_ms() - self.last_head_pose_ms <= 400:
                delta = np.array([position["x"], position["y"], position["z"]]) - self.last_face_position
                relative = self.last_face_rotation.T @ delta
                saber["relativeToHeadM"] = {
                    "x": round(float(relative[0]), 4),
                    "y": round(float(relative[1]), 4),
                    "z": round(float(relative[2]), 4),
                }
        return saber

    def blade_up_cam(self, blade_axis: np.ndarray) -> np.ndarray:
        room_up = np.array([0.0, -1.0, 0.0])
        projected = room_up - float(np.dot(room_up, blade_axis)) * blade_axis
        if float(np.linalg.norm(projected)) < 0.05 and self.latest_saber_rotation is not None:
            projected = self.latest_saber_rotation @ np.array([1.0, 0.0, 0.0])
            projected = projected - float(np.dot(projected, blade_axis)) * blade_axis
        return _unit(projected)

    def build_unity_pose(self) -> dict[str, Any]:
        omega = float(self.imu["omegaDegS"]) * math.pi / 180.0 if self.imu else 0.0
        return unity_pose_message(
            timestamp_ms=now_ms(),
            head_position=self.last_face_position,
            head_forward=self.last_head_forward,
            head_up=self.last_head_up,
            head_pose_ms=self.last_head_pose_ms,
            now_ms=now_ms(),
            yaw_rad=self.last_yaw_rad,
            head_quality=self.last_head_quality,
            head_cue=self._head_cue,
            saber=self.latest_saber,
            angular_speed_rad_s=omega,
            forward_set=self.forward_set,
            saber_reference_set=self.saber_reference_rotation is not None,
            saber_hand=self.args.saber_hand,
            skeleton=self.last_skeleton,
            skeleton_ms=self.last_skeleton_ms,
            metrics=self.last_metrics,
        )

    def publish_unity_pose(self) -> None:
        with self._pose_publish_lock:
            self.unity_hub.send(self.build_unity_pose())

    def handle_unity_command(self, message: dict[str, Any]) -> None:
        kind = message.get("type")
        if kind == "calibrate_forward":
            self.request_screen_calibration("forward")
        elif kind == "calibrate_saber_reference":
            self.request_screen_calibration("saber")
        elif kind == "vibrate":
            self.send_haptic()
        elif kind == "set_saber_hand":
            hand = message.get("hand")
            if hand not in ("left", "right"):
                return
            self.args.saber_hand = hand
            self.publish_unity_pose()

    def detect_pose_wrist(
        self,
        rgb: np.ndarray,
        timestamp_ms: int,
        captured_ms: float,
        width: int,
        height: int,
        fx: float,
        face_depth_m: Optional[float],
        want_overlay: bool,
    ) -> Optional[dict[str, Any]]:
        found = self.vision.detect_pose(
            rgb, timestamp_ms, width, height, fx, face_depth_m, want_overlay, self.args.saber_hand,
        )
        if found.pose_head is not None:
            self._pose_head_fallback = (captured_ms, found.pose_head[0], found.pose_head[1])
        if found.skeleton is not None:
            self.last_skeleton = found.skeleton
            self.last_skeleton_ms = captured_ms
        if found.wrist_xyz is not None and found.wrist_name is not None:
            self.apply_wrist_position(found.wrist_xyz, found.wrist_name, captured_ms)
            self.publish_unity_pose()
        return found.overlay

    def collect_pose_job(self) -> None:
        """Copy a finished Pose overlay. The wrist is already applied on the Pose thread."""
        if self._pose_job is None:
            return
        future = self._pose_job
        if not future.done():
            return
        self._pose_job = None
        try:
            overlay = future.result()
        except Exception:
            return
        if overlay is not None:
            self._pose_overlay = overlay

    def ensure_frame_buffers(self, frame: np.ndarray) -> tuple[int, int, float, np.ndarray]:
        h, w = frame.shape[0], frame.shape[1]
        if self._rgb_buf is None or self._rgb_buf.shape[:2] != (h, w):
            self._rgb_buf = np.empty((h, w, 3), dtype=np.uint8)
            self._fx = w / (2.0 * math.tan(math.radians(self.args.camera_fov) / 2.0))
        assert self._fx is not None and self._rgb_buf is not None
        return h, w, self._fx, self._rgb_buf

    def calibrate(self) -> tuple[bool, str]:
        if self.last_raw_yaw is None:
            return False, "No face is visible yet. Face the camera and try again."
        self.yaw_zero = self.last_raw_yaw
        self.forward_set = True
        if self.last_face_rotation is not None:
            forward, up, yaw_rad = calibrated_head_axes(self.last_face_rotation, self.yaw_zero)
            self.last_head_forward = forward
            self.last_head_up = up
            self.last_yaw_rad = yaw_rad
        self.publish_unity_pose()
        return True, "Forward direction set to the current face pose."

    def calibrate_saber_reference(self) -> tuple[bool, str]:
        """Lock the configured hilt-to-tip axis, currently pointing at the camera."""
        if self.imu_rotation is None or not self.imu_fresh():
            link = "the iPhone OSC link" if self.args.iphone else "the Arduino USB connection"
            return False, f"No fresh IMU sample yet. Check {link}, then try again."
        self.saber_reference_rotation = self.imu_rotation.copy()
        self.saber_device_to_camera0 = rotation_mapping_two_vectors(
            self.blade_device_axis(),
            self.imu_up_in_device(),
            np.array([0.0, 0.0, -1.0]),  # toward Mac camera
            np.array([0.0, -1.0, 0.0]),  # room up (camera +y is down)
        )
        if self.last_wrist_ms is None or now_ms() - self.last_wrist_ms > 800.0:
            if self.handle.last_cam_p is None:
                self.imu_handle_position = self.default_handle_position()
                self.handle.ensure(self.imu_handle_position)
        saber = self.build_imu_saber()
        if saber is not None:
            self.latest_saber = saber
            self.latest_saber_ms = now_ms()
            self.latest_saber_rotation = self.camera_saber_rotation()
        return True, "Saber reference saved. At this pose the blade points at the camera; lifting the tip should raise the blade."

    async def capture_loop(self) -> None:
        thread = threading.Thread(target=self.capture_loop_sync, name="camera-capture", daemon=True)
        thread.start()
        try:
            while self.running:
                await asyncio.sleep(0.25)
        finally:
            self.running = False
            thread.join(timeout=2.0)

    def capture_loop_sync(self) -> None:
        # The first backend matches list_cameras(): AVFoundation on macOS, Media Foundation on Windows.
        system = platform.system()
        if system == "Darwin":
            cap = cv2.VideoCapture(self.args.camera, cv2.CAP_AVFOUNDATION)
        elif system == "Windows":
            cap = cv2.VideoCapture(self.args.camera, cv2.CAP_MSMF)
        else:
            cap = cv2.VideoCapture(self.args.camera)
        if not cap.isOpened():
            cap = cv2.VideoCapture(self.args.camera)
        if not cap.isOpened():
            if system == "Darwin":
                self.camera_error = "Could not open the selected camera. Allow Camera access for Terminal/Python in macOS Settings, then restart."
            elif system == "Windows":
                self.camera_error = "Could not open the selected camera. Allow Camera access for Python in Windows Settings, then restart."
            else:
                self.camera_error = "Could not open the selected camera."
            self.emit_threadsafe({"type": "error", "message": self.camera_error})
            self.running = False
            return

        cap.set(cv2.CAP_PROP_FRAME_WIDTH, self.args.width)
        cap.set(cv2.CAP_PROP_FRAME_HEIGHT, self.args.height)
        cap.set(cv2.CAP_PROP_FPS, self.args.fps)
        # Backends may ignore this property, but it is safe and helps when they do
        # honour it: always prefer a fresh frame to a queued stale one.
        cap.set(cv2.CAP_PROP_BUFFERSIZE, 1)
        actual_w = int(cap.get(cv2.CAP_PROP_FRAME_WIDTH))
        actual_h = int(cap.get(cv2.CAP_PROP_FRAME_HEIGHT))
        actual_fps = float(cap.get(cv2.CAP_PROP_FPS))
        print(
            f"Camera requested {self.args.width}x{self.args.height} at {self.args.fps} fps; "
            f"backend reports {actual_w}x{actual_h} at {actual_fps:.1f} fps.",
            flush=True,
        )

        processor = threading.Thread(target=self.process_latest_frames, name="face-process", daemon=True)
        processor.start()
        try:
            while self.running:
                read_started_ms = now_ms()
                ok, frame = cap.read()
                captured_ms = now_ms()
                if not ok or frame is None:
                    time.sleep(0.03)
                    continue

                with self._frame_condition:
                    self._capture_sequence += 1
                    self._latest_frame = (self._capture_sequence, frame, read_started_ms, captured_ms)
                    self._frame_condition.notify()
        finally:
            cap.release()
            self.running = False
            with self._frame_condition:
                self._frame_condition.notify_all()
            processor.join(timeout=2.0)
            if self._pose_job is not None:
                try:
                    self._pose_job.result(timeout=1.0)
                except Exception:
                    pass
                self._pose_job = None
            self.vision.close()

    def process_latest_frames(self) -> None:
        """Process only the newest camera frame; intermediate frames are discarded."""
        last_sequence = 0
        while self.running:
            with self._frame_condition:
                self._frame_condition.wait_for(
                    lambda: not self.running
                    or (self._latest_frame is not None and self._latest_frame[0] > last_sequence),
                    timeout=0.25,
                )
                packet = self._latest_frame
            if packet is None or packet[0] <= last_sequence:
                continue
            sequence, frame, read_started_ms, captured_ms = packet
            dropped_frames = max(0, sequence - last_sequence - 1)
            last_sequence = sequence

            if frame.shape[1] != self.args.width or frame.shape[0] != self.args.height:
                frame = cv2.resize(frame, (self.args.width, self.args.height))
            h, w, fx, rgb = self.ensure_frame_buffers(frame)
            cv2.cvtColor(frame, cv2.COLOR_BGR2RGB, dst=rgb)
            self.collect_pose_job()
            observation: Optional[dict[str, Any]] = None
            face_locked = False
            raw_yaw = 0.0
            preview_dots = None
            timestamp_ms = int(captured_ms)
            want_preview = self.preview_subscribers > 0 and captured_ms >= self.next_preview_ms
            if self.vision.pose_landmarker is not None and self._pose_job is None and captured_ms >= self._next_pose_ms:
                face_depth_guess = self.fresh_face_depth(captured_ms)
                self._pose_job = self.detect_pool.submit(
                    self.detect_pose_wrist,
                    rgb.copy(),
                    timestamp_ms,
                    captured_ms,
                    w,
                    h,
                    fx,
                    face_depth_guess,
                    self.preview_subscribers > 0,
                )
                self._next_pose_ms = captured_ms + 1000.0 / self.args.pose_fps

            try:
                face = self.vision.detect_face(rgb, timestamp_ms, w, h, fx, self.yaw_zero)
            except Exception as error:
                print(f"Face detection failed, skipping frame: {error}", flush=True)
                continue
            observation = face.observation
            face_locked = face.locked
            raw_yaw = face.raw_yaw
            preview_dots = face.preview_dots
            if face.locked and face.position is not None:
                self.last_face_position = face.position
                self.last_face_rotation = face.rotation
                self._last_face_sample_ms = captured_ms
                self.last_head_pose_ms = captured_ms
                self.last_head_forward = face.forward
                self.last_head_up = face.up
                self.last_yaw_rad = face.yaw_rad
                self.last_head_quality = face.quality
            if face_locked:
                self._face_absent_since = None
                self.publish_head_cue("", captured_ms, face_visible=True)
            else:
                self.adopt_pose_head(captured_ms)
            detected_ms = now_ms()
            live_saber = self.latest_saber

            if observation is not None:
                self.last_raw_yaw = raw_yaw
                yaw = normalize_degrees(raw_yaw - self.yaw_zero)
                observation["rawYawDeg"] = round(raw_yaw, 3)
                observation["yawDeg"] = round(yaw, 3)

            sent_ms = now_ms()
            if self.last_frame_finished_ms is not None:
                instantaneous_fps = 1000.0 / max(0.1, sent_ms - self.last_frame_finished_ms)
                self.fps_ema = instantaneous_fps if self.fps_ema == 0 else 0.12 * instantaneous_fps + 0.88 * self.fps_ema
            self.last_frame_finished_ms = sent_ms
            self.frame_number += 1
            self.emit_threadsafe(
                {
                    "type": "pose",
                    "sequence": self.frame_number,
                    "timestamps": {
                        "readStartedMs": round(read_started_ms, 3),
                        "capturedMs": round(captured_ms, 3),
                        "detectedMs": round(detected_ms, 3),
                        "sentMs": round(sent_ms, 3),
                    },
                    "metrics": {
                        "captureCallMs": round(captured_ms - read_started_ms, 3),
                        "detectMs": round(detected_ms - captured_ms, 3),
                        "framePipelineMs": round(sent_ms - captured_ms, 3),
                        "fps": round(self.fps_ema, 2),
                        "droppedCaptureFrames": dropped_frames,
                    },
                    "tag": observation,
                    "saber": live_saber,
                    "saberLastSeenMs": self.latest_saber_ms,
                    "serial": self.imu_link(),
                }
            )
            self.last_metrics = {
                "fps": round(self.fps_ema, 2),
                "detectMs": round(detected_ms - captured_ms, 3),
                "droppedCaptureFrames": dropped_frames,
            }
            self.publish_unity_pose()
            preview_ready = self._preview_job is None or self._preview_job.done()
            if want_preview and preview_ready:
                face_dots = preview_dots
                yaw_text = None
                if observation is not None and "yawDeg" in observation:
                    yaw_text = f"face yaw {observation['yawDeg']:+.1f} deg"
                self._preview_job = self.preview_pool.submit(
                    self.update_preview, frame.copy(), face_dots, yaw_text, self._pose_overlay
                )
                self.next_preview_ms = captured_ms + 1000.0 / self.args.preview_fps

    def update_preview(
        self,
        frame: np.ndarray,
        face_dots: Optional[list[tuple[int, int]]],
        yaw_text: Optional[str],
        pose_overlay: Optional[dict[str, Any]] = None,
    ) -> None:
        debug = frame
        if face_dots:
            for point in face_dots:
                cv2.circle(debug, point, 2, (80, 235, 120), -1)
            cv2.putText(
                debug,
                yaw_text or "face",
                (18, 36),
                cv2.FONT_HERSHEY_SIMPLEX,
                0.72,
                (80, 235, 120),
                2,
            )
        else:
            cv2.putText(
                debug,
                "Looking for a face",
                (18, 36),
                cv2.FONT_HERSHEY_SIMPLEX,
                0.72,
                (80, 180, 255),
                2,
            )
        if pose_overlay is not None:
            points = pose_overlay["points"]
            for start, end in POSE_PREVIEW_EDGES:
                a, b = points[start], points[end]
                if a is not None and b is not None:
                    cv2.line(debug, a, b, (90, 160, 220), 2)
            wrist_index = pose_overlay.get("wristIndex")
            for index, point in enumerate(points):
                if point is None:
                    continue
                if index == wrist_index:
                    cv2.circle(debug, point, 7, (65, 210, 255), -1)
                else:
                    cv2.circle(debug, point, 3, (80, 180, 220), -1)
            if wrist_index is not None and points[wrist_index] is not None:
                wrist_pixel = points[wrist_index]
                cv2.putText(
                    debug,
                    f"{pose_overlay.get('wristName') or 'pose'} wrist",
                    (wrist_pixel[0] + 8, max(58, wrist_pixel[1] - 8)),
                    cv2.FONT_HERSHEY_SIMPLEX,
                    0.55,
                    (65, 210, 255),
                    2,
                )
        cv2.putText(
            debug,
            f"preview {self.args.preview_fps} Hz (diagnostic only)",
            (18, debug.shape[0] - 18),
            cv2.FONT_HERSHEY_SIMPLEX,
            0.5,
            (215, 230, 240),
            1,
        )
        if self.mirror_camera:
            debug = cv2.flip(debug, 1)
        ok, encoded = cv2.imencode(".jpg", debug, [cv2.IMWRITE_JPEG_QUALITY, 60])
        if ok:
            self.latest_preview = encoded.tobytes()
            self.preview_sequence += 1


async def ws_handler(request: web.Request) -> web.WebSocketResponse:
    tracker: Tracker = request.app["tracker"]
    ws = web.WebSocketResponse(heartbeat=20)
    await ws.prepare(request)
    tracker.clients.add(ws)
    await ws.send_json(
        {
            "type": "server_info",
            "message": "Connected to local tracker.",
            "cameraError": tracker.camera_error,
            "mirrorCamera": tracker.mirror_camera,
        }
    )
    try:
        async for msg in ws:
            if msg.type != web.WSMsgType.TEXT:
                continue
            try:
                data = json.loads(msg.data)
            except json.JSONDecodeError:
                continue
            if data.get("type") == "calibrate":
                tracker.request_screen_calibration("forward")
            elif data.get("type") == "calibrate_saber_reference":
                tracker.request_screen_calibration("saber")
            elif data.get("type") == "mag_calibration":
                ok, text = tracker.magnetic_calibration_command(data.get("action"))
                await tracker.broadcast({"type": "notice", "ok": ok, "message": text})
                await tracker.broadcast({"type": "mag_calibration", "calibration": tracker.mag_calibration.status()})
            elif data.get("type") == "mirror_camera":
                tracker.mirror_camera = bool(data.get("mirrored"))
                state = "on" if tracker.mirror_camera else "off"
                await tracker.broadcast({"type": "notice", "ok": True, "message": f"Selfie display and audio mirror {state}."})
            elif data.get("type") == "block":
                sent_ms = tracker.send_haptic()
                await tracker.broadcast({"type": "block", "manual": True, "hapticCommandSentMs": sent_ms})
    finally:
        tracker.clients.discard(ws)
    return ws


async def mjpeg_handler(request: web.Request) -> web.StreamResponse:
    """Serve the most recent debug frame without adding a capture queue."""
    tracker: Tracker = request.app["tracker"]
    response = web.StreamResponse(
        status=200,
        headers={
            "Content-Type": "multipart/x-mixed-replace; boundary=frame",
            "Cache-Control": "no-store, no-cache, must-revalidate, max-age=0",
            "Pragma": "no-cache",
        },
    )
    await response.prepare(request)
    tracker.preview_subscribers += 1
    seen = -1
    try:
        while tracker.running:
            image = tracker.latest_preview
            if image is not None and tracker.preview_sequence != seen:
                seen = tracker.preview_sequence
                await response.write(
                    b"--frame\r\nContent-Type: image/jpeg\r\n"
                    + f"Content-Length: {len(image)}\r\n\r\n".encode("ascii")
                    + image
                    + b"\r\n"
                )
            await asyncio.sleep(0.04)
    except (ConnectionResetError, asyncio.CancelledError):
        pass
    finally:
        tracker.preview_subscribers = max(0, tracker.preview_subscribers - 1)
    return response


async def on_startup(app: web.Application) -> None:
    loop = asyncio.get_running_loop()
    app["tracker"].loop = loop
    app["tracker"].start_osc()
    app["tracker"].start_serial()
    app["tracker"].unity_hub.start(app["tracker"].handle_unity_command)
    app["capture_task"] = asyncio.create_task(app["tracker"].capture_loop())


async def on_cleanup(app: web.Application) -> None:
    app["tracker"].running = False
    task: asyncio.Task[Any] = app.get("capture_task")
    if task:
        task.cancel()
        try:
            await task
        except asyncio.CancelledError:
            pass
    if app["tracker"].osc_reader:
        app["tracker"].osc_reader.close()
    if app["tracker"].serial_reader:
        app["tracker"].serial_reader.close()
    app["tracker"].unity_hub.close()
    app["tracker"].detect_pool.shutdown(wait=False)
    app["tracker"].preview_pool.shutdown(wait=False)


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Hear the Unseen head and saber tracker")
    parser.add_argument("--host", default="127.0.0.1", help="Local host to listen on (default: 127.0.0.1)")
    parser.add_argument("--port", type=int, default=8765)
    parser.add_argument(
        "--camera",
        default=None,
        help="Camera name substring or OpenCV index; default prefers the built-in camera",
    )
    parser.add_argument("--list-cameras", action="store_true", help="List cameras and exit")
    parser.add_argument("--width", type=int, default=640)
    parser.add_argument("--height", type=int, default=480)
    parser.add_argument("--fps", type=int, default=60)
    parser.add_argument("--camera-fov", type=float, default=60.0, help="Approximate horizontal camera FOV in degrees")
    parser.add_argument("--mirror-camera", action=argparse.BooleanOptionalAction, default=True, help="Mirror preview and HRTF left/right by default; World stays a room view")
    parser.add_argument("--serial", default="auto", help="Arduino port, or auto for the only USB modem (default: auto). Unused with --iphone")
    parser.add_argument("--baud", type=int, default=230400)
    parser.add_argument("--iphone", action="store_true", help="Use iPhone OSC IMU instead of Arduino serial")
    parser.add_argument("--no-magnetometer", action="store_true", help="Read magnetic telemetry but disable Arduino magnetic heading correction")
    parser.add_argument("--mag-calibration-file", type=Path, default=REPO / ".cache" / "mag-calibration.json", help="Saved hard/soft-iron calibration for this sensor and mounting")
    parser.add_argument("--mag-mount-angle", type=float, default=None, help="Force a signed twist about MPU -Y and skip the one-time mounting fit. Default: use the saved calibration, or +8° until that calibration exists")
    parser.add_argument("--mag-declination", type=float, default=None, help="Local east-positive magnetic declination in degrees; omitted = no true-north output")
    parser.add_argument("--osc-bind", default="0.0.0.0", help="UDP bind address for TouchOSC (default: all interfaces)")
    parser.add_argument("--osc-port", type=int, default=8000, help="UDP port this computer receives /imu on")
    parser.add_argument("--iphone-port", type=int, default=9000, help="UDP port TouchOSC listens on for /vibrate")
    parser.add_argument("--iphone-host", default=None, help="Force iPhone IP for /vibrate; default is the last OSC sender")
    parser.add_argument("--gyro-scale", type=float, default=1.0, help="Multiply incoming gyro; the TouchOSC layout already converts rad/s to deg/s")
    parser.add_argument("--face-model", default=str(REPO / "assets" / "face_landmarker.task"))
    parser.add_argument("--pose-model", default=str(REPO / "assets" / "pose_landmarker_lite.task"))
    parser.add_argument("--saber-hand", choices=("auto", "left", "right"), default="right", help="Which Pose Landmarker wrist is the saber handle")
    parser.add_argument("--pose-fps", type=float, default=12.0, help="Pose wrist rate; 0 disables Pose for lowest head-audio latency")
    parser.add_argument("--preview-fps", type=float, default=12.0, help="Diagnostic MJPEG preview rate; it is not part of audio timing")
    parser.add_argument("--unity-host", default="127.0.0.1", help="UDP host for Unity pose packets")
    parser.add_argument("--unity-port", type=int, default=8766, help="UDP port Unity listens on for pose")
    parser.add_argument("--unity-command-port", type=int, default=8767, help="UDP port Python listens on for Unity commands")
    args = parser.parse_args()
    if args.iphone:
        if args.serial != "auto":
            parser.error("--iphone uses the phone IMU and does not open a serial port")
        args.serial = None
    if args.mag_declination is not None and (not math.isfinite(args.mag_declination) or abs(args.mag_declination) > 180):
        parser.error("--mag-declination must be finite and between -180 and 180 degrees")
    return args


def main() -> None:
    args = parse_args()
    if args.list_cameras:
        print_camera_list()
        return
    camera_index, camera_name = choose_mac_camera(args.camera)
    args.camera = camera_index
    args.camera_name = camera_name
    app = web.Application()
    app["tracker"] = Tracker(args)
    app.router.add_get("/", lambda request: web.FileResponse(STATIC / "index.html"))
    app.router.add_static("/static/", STATIC, show_index=False)
    app.router.add_get("/ws", ws_handler)
    app.router.add_get("/preview.mjpg", mjpeg_handler)
    app.router.add_get("/health", lambda request: web.json_response({"ok": True}))
    app.on_startup.append(on_startup)
    app.on_cleanup.append(on_cleanup)
    print(f"Open http://{args.host}:{args.port} in Chrome or Safari.")
    print(f"Using camera {args.camera} ({args.camera_name}).")
    if args.iphone:
        print(
            f"iPhone IMU: UDP Host {lan_ipv4()}, Port {args.osc_port}, OSC, enable GYRO + QUATERNION (and GRAVITY if listed)."
        )
        print(f"Optional TouchOSC haptic: same Host, Send {args.osc_port}, Receive {args.iphone_port}.")
    else:
        print(f"Arduino IMU: serial {args.serial} at {args.baud} baud.")
    print(f"Unity pose UDP {args.unity_host}:{args.unity_port}  commands :{args.unity_command_port}")
    web.run_app(app, host=args.host, port=args.port, access_log=None)


if __name__ == "__main__":
    main()
