#!/usr/bin/env python3
"""Local face/pose + iPhone IMU saber server for the LightSaber prototype.

The server keeps camera capture, MediaPipe, and the browser WebSocket on one
computer. Timing telemetry locates software delay; it is not a physical
motion-to-sound result because the webcam sensor/ISP age is not observable.
"""

from __future__ import annotations

import argparse
import asyncio
import json
import math
import platform
import re
import socket
import subprocess
import threading
import time
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path
from typing import Any, Optional

from aiohttp import web
import cv2
import numpy as np

# cvtColor/resize are cheap at 640×480; extra OpenCV threads steal cores from
# MediaPipe XNNPACK and increase detect latency under contention.
cv2.setNumThreads(1)


ROOT = Path(__file__).resolve().parent
STATIC = ROOT / "web"

_PHONE_CAMERA_RE = re.compile(
    r"iphone|ipad|continuity|desk\s*view|桌上视角|sidecar",
    re.IGNORECASE,
)
_SCREEN_CAMERA_RE = re.compile(r"capture\s+screen|screen\s+recording", re.IGNORECASE)
_AUDIO_DEVICE_RE = re.compile(r"microphone|麦克风|audio", re.IGNORECASE)
_MAC_CAMERA_RE = re.compile(r"facetime|built[- ]in|macbook|imac\b", re.IGNORECASE)


def now_ms() -> float:
    """Monotonic time, shared by all server-side stage timestamps."""
    return time.perf_counter_ns() / 1_000_000.0


def list_macos_cameras() -> list[tuple[int, str]]:
    """Return cameras in OpenCV's AVFoundation order, not ffmpeg's."""
    cameras = _opencv_avfoundation_cameras()
    if cameras:
        return cameras
    return _system_profiler_cameras()


def _opencv_camera_helper() -> Optional[Path]:
    """Compile macos_cameras.swift once; OpenCV indices follow uniqueID sort."""
    source = ROOT / "macos_cameras.swift"
    if not source.is_file():
        return None
    binary = ROOT / ".cache" / "macos_cameras"
    binary.parent.mkdir(parents=True, exist_ok=True)
    if binary.is_file() and binary.stat().st_mtime >= source.stat().st_mtime:
        return binary
    try:
        result = subprocess.run(
            ["swiftc", "-O", "-o", str(binary), str(source)],
            capture_output=True,
            text=True,
            timeout=60,
        )
    except (FileNotFoundError, subprocess.TimeoutExpired):
        return None
    if result.returncode != 0 or not binary.is_file():
        return None
    return binary


def _opencv_avfoundation_cameras() -> list[tuple[int, str]]:
    if platform.system() != "Darwin":
        return []
    helper = _opencv_camera_helper()
    if helper is None:
        return []
    try:
        result = subprocess.run([str(helper)], capture_output=True, text=True, timeout=8)
    except (OSError, subprocess.TimeoutExpired):
        return []
    if result.returncode != 0:
        return []
    cameras: list[tuple[int, str]] = []
    for line in result.stdout.splitlines():
        if "\t" not in line:
            continue
        index_text, name = line.split("\t", 1)
        name = name.strip()
        if not index_text.isdigit() or not name:
            continue
        if _SCREEN_CAMERA_RE.search(name) or _AUDIO_DEVICE_RE.search(name):
            continue
        cameras.append((int(index_text), name))
    return cameras


def _system_profiler_cameras() -> list[tuple[int, str]]:
    if platform.system() != "Darwin":
        return []
    try:
        result = subprocess.run(
            ["system_profiler", "SPCameraDataType", "-json"],
            capture_output=True,
            text=True,
            timeout=8,
        )
    except (FileNotFoundError, subprocess.TimeoutExpired):
        return []
    try:
        payload = json.loads(result.stdout)
    except json.JSONDecodeError:
        return []
    cameras: list[tuple[int, str]] = []
    for index, item in enumerate(payload.get("SPCameraDataType") or []):
        name = str(item.get("_name") or "").strip()
        if not name or _SCREEN_CAMERA_RE.search(name) or _AUDIO_DEVICE_RE.search(name):
            continue
        cameras.append((index, name))
    return cameras


def camera_name_score(name: str) -> int:
    """Higher is a better Mac built-in match. iPhone / Desk View score below zero."""
    if _PHONE_CAMERA_RE.search(name) or _SCREEN_CAMERA_RE.search(name) or _AUDIO_DEVICE_RE.search(name):
        return -1
    if _MAC_CAMERA_RE.search(name):
        return 100
    return 0


def choose_mac_camera(explicit: Optional[str]) -> tuple[int, str]:
    """Pick a camera by name each launch. Indices change when Continuity Camera appears."""
    cameras = list_macos_cameras()
    if explicit is not None:
        if explicit.isdigit():
            index = int(explicit)
            name = next((name for camera_index, name in cameras if camera_index == index), f"index {index}")
            return index, name
        needle = explicit.casefold()
        hits = [(index, name) for index, name in cameras if needle in name.casefold()]
        if not hits:
            available = ", ".join(f"[{index}] {name}" for index, name in cameras) or "none listed"
            raise SystemExit(f"No camera matching {explicit!r}. Available: {available}")
        preferred = [(index, name) for index, name in hits if camera_name_score(name) > 0]
        return (preferred or hits)[0]
    ranked = [(camera_name_score(name), index, name) for index, name in cameras]
    mac = [(score, index, name) for score, index, name in ranked if score > 0]
    if mac:
        mac.sort(reverse=True)
        return mac[0][1], mac[0][2]
    other = [(index, name) for score, index, name in ranked if score == 0]
    if other:
        return other[0]
    if cameras:
        return cameras[0]
    return 0, "default (no camera list available)"


def print_camera_list() -> None:
    cameras = list_macos_cameras()
    if not cameras:
        print("No cameras were listed. Install Xcode command-line tools so macos_cameras.swift can compile.")
        return
    chosen_index, chosen_name = choose_mac_camera(None)
    print("OpenCV camera order (sorted by AVFoundation uniqueID, not ffmpeg):")
    for index, name in cameras:
        mark = f"  <- auto ({chosen_name})" if index == chosen_index else ""
        print(f"  [{index}] {name}{mark}")
    print("Auto-select matches the Mac built-in name. Override with --camera 'MacBook' or --camera N.")


def normalize_degrees(angle: float) -> float:
    return (angle + 180.0) % 360.0 - 180.0


def rotation_to_euler_degrees(rotation: np.ndarray) -> dict[str, float]:
    """Return the marker orientation as camera-frame yaw, pitch, and roll."""
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


def orthonormalize_rotation(matrix: np.ndarray) -> np.ndarray:
    """Remove any scale/shear before using a face transform as a rotation."""
    left, _, right_t = np.linalg.svd(matrix[:3, :3])
    rotation = left @ right_t
    if np.linalg.det(rotation) < 0:
        left[:, -1] *= -1
        rotation = left @ right_t
    return rotation


def _unit(vector: np.ndarray) -> np.ndarray:
    norm = float(np.linalg.norm(vector))
    return vector / (norm if norm > 1e-9 else 1.0)


def vec3(values: np.ndarray) -> dict[str, float]:
    return {"x": round(float(values[0]), 4), "y": round(float(values[1]), 4), "z": round(float(values[2]), 4)}


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


class UnityPoseHub:
    """Local UDP: Python → Unity pose, Unity → Python commands."""

    def __init__(self, dest_host: str, dest_port: int, command_port: int) -> None:
        self.dest = (dest_host, dest_port)
        self.sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        self.command_sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        self.command_sock.bind(("127.0.0.1", command_port))
        self.command_sock.settimeout(0.25)
        self._on_command: Optional[Any] = None
        self._running = False
        self._thread: Optional[threading.Thread] = None

    def send(self, message: dict[str, Any]) -> None:
        payload = json.dumps(message, separators=(",", ":")).encode("utf-8")
        try:
            self.sock.sendto(payload, self.dest)
        except OSError:
            pass

    def start(self, on_command: Any) -> None:
        self._on_command = on_command
        self._running = True
        self._thread = threading.Thread(target=self._listen, name="unity-commands", daemon=True)
        self._thread.start()

    def _listen(self) -> None:
        while self._running:
            try:
                data, _addr = self.command_sock.recvfrom(4096)
            except (TimeoutError, socket.timeout, OSError):
                continue
            try:
                message = json.loads(data.decode("utf-8"))
            except (UnicodeDecodeError, json.JSONDecodeError):
                continue
            if self._on_command is not None:
                self._on_command(message)

    def close(self) -> None:
        self._running = False
        try:
            self.command_sock.close()
            self.sock.close()
        except OSError:
            pass


# Core Motion +Y is the top of the iPhone (earpiece). That is the blade.
IPHONE_BLADE_DEVICE = np.array([0.0, 1.0, 0.0])

POSE_NOSE = 0
POSE_LEFT_SHOULDER = 11
POSE_RIGHT_SHOULDER = 12
POSE_LEFT_WRIST = 15
POSE_RIGHT_WRIST = 16
SHOULDER_WIDTH_M = 0.38
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


def unproject_normalized_landmark(landmark: Any, z_m: float, width: int, height: int, fx: float) -> np.ndarray:
    return np.array(
        [
            ((float(landmark.x) * width - width / 2.0) / fx) * z_m,
            ((float(landmark.y) * height - height / 2.0) / fx) * z_m,
            z_m,
        ]
    )


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
    """Gyro integration with optional gravity tilt correction. Gyro in rad/s."""

    def __init__(self) -> None:
        self.q = np.array([1.0, 0.0, 0.0, 0.0], dtype=float)  # w, x, y, z
        self.last_ms: Optional[float] = None

    def rotation(self) -> np.ndarray:
        w, x, y, z = self.q
        return quat_xyzw_to_rotation(x, y, z, w)

    def set_from_xyzw(self, x: float, y: float, z: float, w: float) -> np.ndarray:
        norm = math.sqrt(x * x + y * y + z * z + w * w) or 1.0
        self.q = np.array([w / norm, x / norm, y / norm, z / norm], dtype=float)
        return self.rotation()

    def update(self, gx: float, gy: float, gz: float, ax: float, ay: float, az: float, now_ms: float, kp: float = 1.0) -> np.ndarray:
        if self.last_ms is None:
            self.last_ms = now_ms
            return self.rotation()
        dt = max(0.001, min(0.1, (now_ms - self.last_ms) / 1000.0))
        self.last_ms = now_ms
        q0, q1, q2, q3 = self.q
        acc_norm = math.sqrt(ax * ax + ay * ay + az * az)
        if acc_norm > 0.4:  # gravity-sized; skip user-acceleration-only samples
            ax, ay, az = ax / acc_norm, ay / acc_norm, az / acc_norm
            vx = 2 * (q1 * q3 - q0 * q2)
            vy = 2 * (q0 * q1 + q2 * q3)
            vz = q0 * q0 - q1 * q1 - q2 * q2 + q3 * q3
            gx += kp * (ay * vz - az * vy)
            gy += kp * (az * vx - ax * vz)
            gz += kp * (ax * vy - ay * vx)
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


G_MS2 = 9.80665


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
        gain = 0.72 if captured_ms - self.last_cam_ms > 400.0 else 0.34
        self.p = self.p + gain * (p_target - self.p)
        self.v = 0.58 * self.v + 0.42 * v_cam
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


class SerialImuReader:
    """Receive mature-library MPU6050 gyro samples without delaying camera capture."""

    def __init__(self, tracker: "Tracker", device: str, baud: int, loop: asyncio.AbstractEventLoop) -> None:
        try:
            import serial
        except ImportError as error:
            raise RuntimeError("pyserial is not installed. Run ./run.zsh once.") from error
        self.tracker = tracker
        self.loop = loop
        self.stop_requested = threading.Event()
        self.write_lock = threading.Lock()
        self.port = serial.Serial(device, baudrate=baud, timeout=0.1, write_timeout=0.1)
        self.device = device
        self.thread = threading.Thread(target=self.read_loop, name="mpu6050-serial", daemon=True)
        self.thread.start()

    def read_loop(self) -> None:
        while not self.stop_requested.is_set():
            try:
                line = self.port.readline().decode("utf-8", errors="replace").strip()
            except Exception as error:  # The USB cable can be unplugged mid-demo.
                asyncio.run_coroutine_threadsafe(self.tracker.serial_failed(str(error)), self.loop)
                return
            sample = self.parse_imu_line(line)
            if sample is not None:
                # Stay on this thread until BLOCK is written. Hopping to the
                # asyncio loop first used to wait behind camera detection.
                self.tracker.ingest_imu(sample)

    @staticmethod
    def parse_imu_line(line: str) -> Optional[dict[str, float]]:
        # Firmware format: IMU,device_micros,gx_deg_s,gy_deg_s,gz_deg_s,ax_g,ay_g,az_g
        fields = line.split(",")
        if len(fields) != 8 or fields[0] != "IMU":
            return None
        try:
            return {
                "deviceUs": float(fields[1]),
                "gx": float(fields[2]), "gy": float(fields[3]), "gz": float(fields[4]),
                "ax": float(fields[5]), "ay": float(fields[6]), "az": float(fields[7]),
            }
        except ValueError:
            return None

    def send_block(self) -> Optional[float]:
        try:
            with self.write_lock:
                self.port.write(b"BLOCK\n")
                self.port.flush()
            return now_ms()
        except Exception:
            return None

    def close(self) -> None:
        self.stop_requested.set()
        self.thread.join(timeout=0.3)
        try:
            self.port.close()
        except Exception:
            pass


class OscImuReader:
    """Receive iPhone IMU samples over UDP (ZIG SIM OSC, optional TouchOSC)."""

    STALE_MS = 800.0

    def __init__(
        self,
        tracker: "Tracker",
        bind: str,
        port: int,
        iphone_port: int,
        gyro_scale: float,
        loop: asyncio.AbstractEventLoop,
        iphone_host: Optional[str] = None,
    ) -> None:
        try:
            from pythonosc.dispatcher import Dispatcher
            from pythonosc.osc_server import BlockingOSCUDPServer
            from pythonosc.udp_client import SimpleUDPClient
        except ImportError as error:
            raise RuntimeError("python-osc is not installed. Run ./run.zsh once.") from error
        self.tracker = tracker
        self.loop = loop
        self.bind = bind
        self.port = port
        self.iphone_port = iphone_port
        self.gyro_scale = gyro_scale
        self.SimpleUDPClient = SimpleUDPClient
        self.phone_ip = iphone_host
        self.flavor = "osc"
        self.haptic_capable = False
        self.device = f"iPhone OSC UDP {bind}:{port}"
        self.write_lock = threading.Lock()
        self.last_packet_ms = 0.0
        self.packet_times: list[float] = []
        self.rate_hz = 0.0
        self._partial: dict[str, float] = {}
        dispatcher = Dispatcher()
        dispatcher.map("/imu", self.on_imu, needs_reply_address=True)
        dispatcher.map("/accxyz", self.on_accxyz, needs_reply_address=True)
        dispatcher.map("/gyro", self.on_gyro, needs_reply_address=True)
        dispatcher.map("/ZIGSIM/*/gyro", self.on_gyro, needs_reply_address=True)
        dispatcher.map("/ZIGSIM/*/accel", self.on_accxyz, needs_reply_address=True)
        dispatcher.map("/ZIGSIM/*/gravity", self.on_gravity, needs_reply_address=True)
        dispatcher.map("/ZIGSIM/*/quaternion", self.on_quat, needs_reply_address=True)
        dispatcher.map("/ping", self.on_ping, needs_reply_address=True)
        dispatcher.set_default_handler(self.on_unknown, needs_reply_address=True)
        self.server = BlockingOSCUDPServer((bind, port), dispatcher)
        self.thread = threading.Thread(target=self.server.serve_forever, name="iphone-osc-udp", daemon=True)
        self.thread.start()

    def remember_phone(self, client_address: tuple[str, int], address: str = "") -> None:
        self.phone_ip = client_address[0]
        if "ZIGSIM" in address.upper():
            self.flavor = "zigsim"
            self.haptic_capable = False
        elif address in ("/imu", "/ping", "/accxyz"):
            self.flavor = "touchosc"
            self.haptic_capable = True
        label = "ZIG SIM" if self.flavor == "zigsim" else "TouchOSC" if self.flavor == "touchosc" else "iPhone OSC"
        self.device = f"{label} {self.phone_ip} → UDP {self.port}"

    def connected(self) -> bool:
        return self.last_packet_ms > 0 and (now_ms() - self.last_packet_ms) <= self.STALE_MS

    def note_packet(self) -> None:
        received = now_ms()
        self.last_packet_ms = received
        self.packet_times.append(received)
        cutoff = received - 1000.0
        self.packet_times = [stamp for stamp in self.packet_times if stamp >= cutoff]
        if len(self.packet_times) >= 2:
            span = self.packet_times[-1] - self.packet_times[0]
            self.rate_hz = (len(self.packet_times) - 1) * 1000.0 / max(1.0, span)

    @staticmethod
    def floats(args: tuple[Any, ...]) -> list[float]:
        values: list[float] = []
        for item in args:
            if isinstance(item, (int, float)) and not isinstance(item, bool):
                values.append(float(item))
        return values

    def on_unknown(self, client_address: tuple[str, int], address: str, *args: Any) -> None:
        lower = address.lower()
        if lower.endswith("/gyro"):
            self.on_gyro(client_address, address, *args)
        elif lower.endswith("/accel") or lower.endswith("/accxyz") or lower.endswith("/accelerometer"):
            self.on_accxyz(client_address, address, *args)
        elif lower.endswith("/gravity"):
            self.on_gravity(client_address, address, *args)
        elif lower.endswith("/quaternion"):
            self.on_quat(client_address, address, *args)

    def on_imu(self, client_address: tuple[str, int], address: str, *args: Any) -> None:
        values = self.floats(args)
        if len(values) < 6:
            return
        self.remember_phone(client_address, address)
        self.note_packet()
        sample = {
            "deviceUs": values[6] * 1000.0 if len(values) > 6 else now_ms() * 1000.0,
            "gx": values[0] * self.gyro_scale,
            "gy": values[1] * self.gyro_scale,
            "gz": values[2] * self.gyro_scale,
            "ax": values[3],
            "ay": values[4],
            "az": values[5],
        }
        self.tracker.ingest_imu(sample)

    def on_accxyz(self, client_address: tuple[str, int], address: str, *args: Any) -> None:
        values = self.floats(args)
        if len(values) < 3:
            return
        self.remember_phone(client_address, address)
        self.note_packet()
        self._partial["ax"], self._partial["ay"], self._partial["az"] = values[0], values[1], values[2]
        self.emit_partial()

    def on_gyro(self, client_address: tuple[str, int], address: str, *args: Any) -> None:
        values = self.floats(args)
        if len(values) < 3:
            return
        self.remember_phone(client_address, address)
        self.note_packet()
        scale = self.gyro_scale
        self._partial["gx"], self._partial["gy"], self._partial["gz"] = values[0] * scale, values[1] * scale, values[2] * scale
        self.emit_partial()

    def on_gravity(self, client_address: tuple[str, int], address: str, *args: Any) -> None:
        values = self.floats(args)
        if len(values) < 3:
            return
        self.remember_phone(client_address, address)
        self.note_packet()
        self._partial["grav_x"], self._partial["grav_y"], self._partial["grav_z"] = values[0], values[1], values[2]
        self.emit_partial()

    def on_quat(self, client_address: tuple[str, int], address: str, *args: Any) -> None:
        values = self.floats(args)
        if len(values) < 4:
            return
        self.remember_phone(client_address, address)
        self.note_packet()
        self._partial["qx"], self._partial["qy"], self._partial["qz"], self._partial["qw"] = values[0], values[1], values[2], values[3]
        self.emit_partial()

    def on_ping(self, client_address: tuple[str, int], address: str, *_args: Any) -> None:
        self.remember_phone(client_address, address)
        self.note_packet()
        self.tracker.emit_threadsafe({"type": "notice", "ok": True, "message": f"iPhone haptic test from {self.phone_ip}."})

    def emit_partial(self) -> None:
        if "gx" not in self._partial and "qw" not in self._partial:
            return
        sample = {
            "deviceUs": now_ms() * 1000.0,
            "gx": self._partial.get("gx", 0.0),
            "gy": self._partial.get("gy", 0.0),
            "gz": self._partial.get("gz", 0.0),
            "ax": self._partial.get("ax", 0.0),
            "ay": self._partial.get("ay", 0.0),
            "az": self._partial.get("az", 0.0),
        }
        if "grav_x" in self._partial:
            sample["grav_x"] = self._partial["grav_x"]
            sample["grav_y"] = self._partial["grav_y"]
            sample["grav_z"] = self._partial["grav_z"]
        if "qw" in self._partial:
            sample["qx"] = self._partial["qx"]
            sample["qy"] = self._partial["qy"]
            sample["qz"] = self._partial["qz"]
            sample["qw"] = self._partial["qw"]
        self.tracker.ingest_imu(sample)

    def send_block(self) -> Optional[float]:
        if not self.phone_ip or not self.haptic_capable:
            return None
        try:
            with self.write_lock:
                client = self.SimpleUDPClient(self.phone_ip, self.iphone_port)
                client.send_message("/vibrate", 1.0)
            return now_ms()
        except Exception:
            return None

    def close(self) -> None:
        try:
            self.server.shutdown()
            self.server.server_close()
        except Exception:
            pass
        self.thread.join(timeout=0.5)


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
        self.face_landmarker: Any = None
        self.pose_landmarker: Any = None
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
        self.latest_saber_rotation: Optional[np.ndarray] = None
        self.imu_rotation: Optional[np.ndarray] = None
        self.imu_handle_position: Optional[dict[str, float]] = None
        self.last_wrist_ms: Optional[float] = None
        self.last_wrist_name: Optional[str] = None
        self.handle = HandleInertial()
        self.attitude = ComplementaryAttitude()
        self.imu_lock = threading.Lock()
        # Calibrated blade = iPhone top, pointing at the camera at click time.
        self.saber_reference_rotation: Optional[np.ndarray] = None
        self.saber_device_to_camera0: Optional[np.ndarray] = None
        self.forward_set = False
        self.last_head_forward: Optional[np.ndarray] = None
        self.last_head_up: Optional[np.ndarray] = None
        self.last_yaw_rad = 0.0
        self.last_head_quality = 0.0
        self.last_metrics: dict[str, Any] = {"fps": 0.0, "detectMs": 0.0, "droppedCaptureFrames": 0}
        self.unity_hub = UnityPoseHub(args.unity_host, args.unity_port, args.unity_command_port)
        self.loop: Optional[asyncio.AbstractEventLoop] = None
        self.preview_subscribers = 0
        self._frame_condition = threading.Condition()
        self._latest_frame: Optional[tuple[int, np.ndarray, float, float]] = None
        self._capture_sequence = 0
        self._rgb_buf: Optional[np.ndarray] = None
        self._fx: Optional[float] = None
        self._pose_job: Optional[tuple[Any, float]] = None
        self._next_pose_ms = 0.0
        self._pose_overlay: Optional[dict[str, Any]] = None
        self._preview_job: Any = None
        self.detect_pool = ThreadPoolExecutor(max_workers=1, thread_name_prefix="pose")
        self.preview_pool = ThreadPoolExecutor(max_workers=1, thread_name_prefix="preview")
        self.create_face_landmarker()
        if args.pose_fps > 0:
            self.create_pose_landmarker()

    def create_face_landmarker(self) -> None:
        """Load MediaPipe Face Landmarker on CPU/XNNPACK."""
        face_model = Path(self.args.face_model)
        if not face_model.is_file():
            raise RuntimeError(
                f"Face model not found: {face_model}. Run ./run.zsh once to install it."
            )
        try:
            import mediapipe as mp
            from mediapipe.tasks import python as mp_python
            from mediapipe.tasks.python import vision
        except ImportError as error:
            raise RuntimeError("MediaPipe is not installed. Run ./run.zsh once.") from error
        options = vision.FaceLandmarkerOptions(
            # Keep inference on CPU/XNNPACK.  It avoids a platform-dependent
            # Metal setup path and makes the benchmark configuration repeatable.
            base_options=mp_python.BaseOptions(
                model_asset_path=str(face_model), delegate=mp_python.BaseOptions.Delegate.CPU
            ),
            running_mode=vision.RunningMode.VIDEO,
            num_faces=1,
            output_facial_transformation_matrixes=True,
        )
        self.mp = mp
        self.face_landmarker = vision.FaceLandmarker.create_from_options(options)

    def create_pose_landmarker(self) -> None:
        """Same CPU/XNNPACK path as Face Landmarker; lite model keeps 30 fps plausible."""
        pose_model = Path(self.args.pose_model)
        if not pose_model.is_file():
            raise RuntimeError(
                f"Pose model not found: {pose_model}. Run ./run.zsh once to install it."
            )
        try:
            from mediapipe.tasks import python as mp_python
            from mediapipe.tasks.python import vision
        except ImportError as error:
            raise RuntimeError("MediaPipe is not installed. Run ./run.zsh once.") from error
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
        self.pose_landmarker = vision.PoseLandmarker.create_from_options(options)

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

    def start_serial(self, loop: asyncio.AbstractEventLoop) -> None:
        if not self.args.serial:
            return
        device = self.args.serial
        if device == "auto":
            candidates = sorted(Path("/dev").glob("cu.usbmodem*")) + sorted(Path("/dev").glob("cu.usbserial*"))
            if not candidates:
                self.serial_error = "No Arduino serial port found. Connect the Uno, then pass --serial /dev/cu.usbmodem…"
                return
            device = str(candidates[0])
        try:
            self.serial_reader = SerialImuReader(self, device, self.args.baud, loop)
        except Exception as error:
            self.serial_error = f"Could not open Arduino serial ({device}): {error}"

    def start_osc(self, loop: asyncio.AbstractEventLoop) -> None:
        if self.args.no_iphone:
            return
        try:
            self.osc_reader = OscImuReader(
                self,
                self.args.osc_bind,
                self.args.osc_port,
                self.args.iphone_port,
                self.args.gyro_scale,
                loop,
                iphone_host=self.args.iphone_host,
            )
        except OSError as error:
            self.osc_error = f"Could not bind TouchOSC UDP {self.args.osc_bind}:{self.args.osc_port}: {error}"
        except Exception as error:
            self.osc_error = str(error)

    def imu_link(self) -> dict[str, Any]:
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
        if self.serial_reader is not None:
            return {"connected": True, "source": "arduino", "device": self.serial_reader.device, "error": self.serial_error}
        waiting = None
        if self.osc_reader is not None:
            waiting = f"waiting for ZIG SIM/TouchOSC → {self.lan_ip}:{self.args.osc_port}"
        return {"connected": False, "source": None, "device": waiting, "error": self.osc_error or self.serial_error}

    def send_haptic(self) -> Optional[float]:
        if self.osc_reader is not None:
            sent = self.osc_reader.send_block()
            if sent is not None:
                return sent
        if self.serial_reader is not None:
            return self.serial_reader.send_block()
        return None

    async def serial_failed(self, error: str) -> None:
        self.serial_error = f"Arduino serial disconnected: {error}"
        await self.broadcast({"type": "error", "message": self.serial_error})

    def ingest_imu(self, sample: dict[str, float]) -> None:
        received_ms = now_ms()
        omega_rad = math.sqrt(sample["gx"] ** 2 + sample["gy"] ** 2 + sample["gz"] ** 2)
        omega_deg = omega_rad * (180.0 / math.pi)
        with self.imu_lock:
            if all(key in sample for key in ("qx", "qy", "qz", "qw")):
                self.imu_rotation = self.attitude.set_from_xyzw(sample["qx"], sample["qy"], sample["qz"], sample["qw"])
                self.attitude.last_ms = received_ms
            else:
                grav_x = sample.get("grav_x", sample["ax"])
                grav_y = sample.get("grav_y", sample["ay"])
                grav_z = sample.get("grav_z", sample["az"])
                self.imu_rotation = self.attitude.update(sample["gx"], sample["gy"], sample["gz"], grav_x, grav_y, grav_z, received_ms)
            if self.imu_handle_position is None:
                self.imu_handle_position = self.default_handle_position()
            self.handle.ensure(self.imu_handle_position)
            tracking = self.last_wrist_ms is not None and received_ms - self.last_wrist_ms <= 280.0
            accel = self.linear_accel_camera(sample) if self.handle.last_cam_p is not None else np.zeros(3)
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
            "omegaDegS": omega_deg,
            "receivedMs": received_ms,
            "poseSource": "quaternion" if "qw" in sample else "gyro",
        }
        if received_ms - self.last_imu_telemetry_ms >= 8.0:
            self.last_imu_telemetry_ms = received_ms
            self.emit_threadsafe({"type": "imu", "imu": self.imu, "saber": self.latest_saber})
            self.publish_unity_pose()

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

    def choose_pose_wrist(self, landmarks: Any) -> tuple[Optional[str], Any]:
        left, right = landmarks[POSE_LEFT_WRIST], landmarks[POSE_RIGHT_WRIST]
        left_score, right_score = landmark_in_frame_score(left), landmark_in_frame_score(right)
        wanted = self.args.saber_hand
        if wanted == "left":
            return ("left", left) if left_score >= 0 else (None, None)
        if wanted == "right":
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
        # Prefer the more extended arm; small bias toward the right hand.
        if right_reach + 0.02 >= left_reach:
            return "right", right
        return "left", left

    def pose_depth_m(self, landmarks: Any, width: int, height: int, fx: float, head_z: Optional[float]) -> Optional[float]:
        if head_z is not None:
            return float(head_z)
        left, right = landmarks[POSE_LEFT_SHOULDER], landmarks[POSE_RIGHT_SHOULDER]
        span = math.hypot((float(right.x) - float(left.x)) * width, (float(right.y) - float(left.y)) * height)
        if span < 8.0:
            return None
        return max(0.35, min(4.0, (SHOULDER_WIDTH_M * fx) / span))

    def pose_preview_overlay(self, landmarks: Any, width: int, height: int, wrist_name: Optional[str]) -> dict[str, Any]:
        points: list[Optional[tuple[int, int]]] = []
        for landmark in landmarks:
            visibility = 1.0 if landmark.visibility is None else float(landmark.visibility)
            if visibility < 0.3:
                points.append(None)
            else:
                points.append((int(landmark.x * width), int(landmark.y * height)))
        wrist_index = POSE_RIGHT_WRIST if wrist_name == "right" else POSE_LEFT_WRIST if wrist_name == "left" else None
        return {"points": points, "wristIndex": wrist_index, "wristName": wrist_name}

    def wrist_from_pose(
        self,
        pose_result: Any,
        width: int,
        height: int,
        fx: float,
        head_z: Optional[float],
        want_overlay: bool,
    ) -> tuple[Optional[np.ndarray], Optional[str], Optional[dict[str, Any]]]:
        if pose_result is None or not pose_result.pose_landmarks:
            return None, None, None
        landmarks = pose_result.pose_landmarks[0]
        wrist_name, wrist = self.choose_pose_wrist(landmarks)
        overlay = self.pose_preview_overlay(landmarks, width, height, wrist_name) if want_overlay else None
        if wrist_name is None or wrist is None:
            return None, None, overlay
        depth_m = self.pose_depth_m(landmarks, width, height, fx, head_z)
        if depth_m is None:
            return None, wrist_name, overlay
        nose = landmarks[POSE_NOSE]
        image_width_m = depth_m * width / fx
        wrist_z = depth_m + (float(wrist.z) - float(nose.z)) * image_width_m
        wrist_z = max(0.25, min(4.5, wrist_z))
        return unproject_normalized_landmark(wrist, wrist_z, width, height, fx), wrist_name, overlay

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

    def linear_accel_camera(self, sample: dict[str, float]) -> np.ndarray:
        """Device-frame linear accel mapped into the Mac camera frame, m/s²."""
        if self.saber_device_to_camera0 is None or self.saber_reference_rotation is None:
            return np.zeros(3)
        rotation = self.camera_saber_rotation()
        if rotation is None:
            return np.zeros(3)
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

    def build_imu_saber(self) -> Optional[dict[str, Any]]:
        if self.imu_rotation is None:
            return None
        R_cam = self.camera_saber_rotation()
        assert R_cam is not None
        if self.saber_reference_rotation is None or self.saber_device_to_camera0 is None:
            # Before calibration, IMU world is Z-up. Camera is Y-down, Z into the room.
            blade_imu = self.imu_rotation @ IPHONE_BLADE_DEVICE
            blade_axis = np.array([blade_imu[0], -blade_imu[2], -blade_imu[1]])
        else:
            blade_axis = R_cam @ IPHONE_BLADE_DEVICE
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
        head_age = None if self.last_head_pose_ms is None else now_ms() - self.last_head_pose_ms
        head_valid = (
            self.last_face_position is not None
            and self.last_head_forward is not None
            and self.last_head_up is not None
            and head_age is not None
            and head_age <= 400.0
        )
        saber = self.latest_saber
        saber_valid = bool(saber) and saber.get("positionM") is not None
        return {
            "type": "unity_pose",
            "timestampMs": round(now_ms(), 3),
            "head": {
                "positionCamM": vec3(self.last_face_position) if self.last_face_position is not None else {"x": 0.0, "y": 0.0, "z": 0.0},
                "forwardCam": vec3(self.last_head_forward) if self.last_head_forward is not None else {"x": 0.0, "y": 0.0, "z": -1.0},
                "upCam": vec3(self.last_head_up) if self.last_head_up is not None else {"x": 0.0, "y": -1.0, "z": 0.0},
                "yawRad": round(self.last_yaw_rad, 5),
                "valid": head_valid,
                "quality": self.last_head_quality,
            },
            "saber": {
                "handlePositionCamM": saber["positionM"] if saber_valid else {"x": 0.0, "y": 0.0, "z": 0.0},
                "bladeAxisCam": saber.get("bladeAxis", {"x": 0.0, "y": 0.0, "z": -1.0}) if saber_valid else {"x": 0.0, "y": 0.0, "z": -1.0},
                "bladeUpCam": saber.get("bladeUpCam", {"x": 1.0, "y": 0.0, "z": 0.0}) if saber_valid else {"x": 1.0, "y": 0.0, "z": 0.0},
                "angularSpeedRadS": round(float(self.imu["omegaDegS"]) * math.pi / 180.0, 4) if self.imu else 0.0,
                "positionSource": saber.get("positionSource", "") if saber_valid else "",
                "relativeToHeadM": saber.get("relativeToHeadM", {"x": 0.0, "y": 0.0, "z": 0.0}) if saber_valid else {"x": 0.0, "y": 0.0, "z": 0.0},
                "valid": saber_valid,
                "wrist": saber.get("wrist", "") if saber_valid else "",
            },
            "calibration": {
                "forwardSet": self.forward_set,
                "saberReferenceSet": self.saber_reference_rotation is not None,
            },
            "metrics": self.last_metrics,
        }

    def publish_unity_pose(self) -> None:
        self.unity_hub.send(self.build_unity_pose())

    def handle_unity_command(self, message: dict[str, Any]) -> None:
        kind = message.get("type")
        if kind == "calibrate_forward":
            ok, text = self.calibrate()
            self.emit_threadsafe({"type": "notice", "ok": ok, "message": text})
        elif kind == "calibrate_saber_reference":
            ok, text = self.calibrate_saber_reference()
            self.emit_threadsafe({"type": "notice", "ok": ok, "message": text})
        elif kind == "vibrate":
            self.send_haptic()

    def detect_pose_wrist(
        self,
        rgb: np.ndarray,
        timestamp_ms: int,
        width: int,
        height: int,
        fx: float,
        face_depth_m: Optional[float],
        want_overlay: bool,
    ) -> tuple[Optional[np.ndarray], Optional[str], Optional[dict[str, Any]]]:
        image = self.mp.Image(image_format=self.mp.ImageFormat.SRGB, data=rgb)
        result = self.pose_landmarker.detect_for_video(image, timestamp_ms)
        return self.wrist_from_pose(result, width, height, fx, face_depth_m, want_overlay)

    def collect_pose_job(self) -> None:
        """Apply a ready Pose result without ever holding up face tracking."""
        if self._pose_job is None:
            return
        future, captured_ms = self._pose_job
        if not future.done():
            return
        self._pose_job = None
        try:
            wrist_xyz, wrist_name, overlay = future.result()
        except Exception:
            return
        if overlay is not None:
            self._pose_overlay = overlay
        if wrist_xyz is not None and wrist_name is not None:
            self.apply_wrist_position(wrist_xyz, wrist_name, captured_ms)

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
        """Lock iPhone top (+Y) as the blade, currently pointing at the camera."""
        if self.imu_rotation is None or not self.imu_fresh():
            return False, "No fresh iPhone IMU yet. Start ZIG SIM with GYRO (and QUATERNION if available), then try again."
        self.saber_reference_rotation = self.imu_rotation.copy()
        self.saber_device_to_camera0 = rotation_mapping_two_vectors(
            IPHONE_BLADE_DEVICE,
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
        return True, "Saber reference saved. Phone top (earpiece) is the blade; at this pose it points at the camera. Lift the top and the blade should go up."

    async def capture_loop(self, app: web.Application) -> None:
        self.loop = asyncio.get_running_loop()
        thread = threading.Thread(target=self.capture_loop_sync, name="camera-capture", daemon=True)
        thread.start()
        try:
            while self.running:
                await asyncio.sleep(0.25)
        finally:
            self.running = False
            thread.join(timeout=2.0)

    def capture_loop_sync(self) -> None:
        # CAP_AVFOUNDATION matters on macOS; the fallback keeps the script usable
        # on another platform for development.
        cap = cv2.VideoCapture(self.args.camera, cv2.CAP_AVFOUNDATION)
        if not cap.isOpened():
            cap = cv2.VideoCapture(self.args.camera)
        if not cap.isOpened():
            self.camera_error = "Could not open the selected camera. Allow Camera access for Terminal/Python in macOS Settings, then restart."
            self.emit_threadsafe({"type": "error", "message": self.camera_error})
            self.running = False
            return

        cap.set(cv2.CAP_PROP_FRAME_WIDTH, self.args.width)
        cap.set(cv2.CAP_PROP_FRAME_HEIGHT, self.args.height)
        cap.set(cv2.CAP_PROP_FPS, self.args.fps)
        # Backends may ignore this property, but it is safe and helps when they do
        # honour it: always prefer a fresh frame to a queued stale one.
        cap.set(cv2.CAP_PROP_BUFFERSIZE, 1)

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
                    self._pose_job[0].result(timeout=1.0)
                except Exception:
                    pass
                self._pose_job = None
            if self.face_landmarker is not None:
                self.face_landmarker.close()
            if self.pose_landmarker is not None:
                self.pose_landmarker.close()

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
            selected: Any = None
            observation: Optional[dict[str, Any]] = None
            raw_yaw = 0.0
            timestamp_ms = int(captured_ms)
            want_preview = self.preview_subscribers > 0 and captured_ms >= self.next_preview_ms
            if self.pose_landmarker is not None and self._pose_job is None and captured_ms >= self._next_pose_ms:
                face_depth_guess = float(self.last_face_position[2]) if self.last_face_position is not None else None
                self._pose_job = (
                    self.detect_pool.submit(
                        self.detect_pose_wrist,
                        rgb.copy(),
                        timestamp_ms,
                        w,
                        h,
                        fx,
                        face_depth_guess,
                        self.preview_subscribers > 0,
                    ),
                    captured_ms,
                )
                self._next_pose_ms = captured_ms + 1000.0 / self.args.pose_fps

            image = self.mp.Image(image_format=self.mp.ImageFormat.SRGB, data=rgb)
            result = self.face_landmarker.detect_for_video(image, timestamp_ms)
            if result.facial_transformation_matrixes:
                matrix = np.asarray(result.facial_transformation_matrixes[0], dtype=float).reshape(4, 4)
                face_rotation = orthonormalize_rotation(matrix)
                raw_yaw = math.degrees(math.atan2(float(face_rotation[0, 2]), float(face_rotation[2, 2])))
                selected = result.face_landmarks[0] if result.face_landmarks else None
                head_position: Optional[dict[str, float]] = None
                if selected is not None:
                    nose = selected[1]
                    left_eye, right_eye = selected[33], selected[263]
                    eye_distance_px = math.hypot((right_eye.x - left_eye.x) * w, (right_eye.y - left_eye.y) * h)
                    head_z = max(0.35, min(4.0, (0.063 * fx) / max(1.0, eye_distance_px)))
                    base_head_position = np.array(
                        [
                            ((nose.x * w - w / 2.0) / fx) * head_z,
                            ((nose.y * h - h / 2.0) / fx) * head_z,
                            head_z,
                        ]
                    )
                    self.last_face_position = base_head_position
                    self.last_face_rotation = face_rotation
                    self.last_head_pose_ms = captured_ms
                    forward, up, yaw_rad = calibrated_head_axes(face_rotation, self.yaw_zero)
                    self.last_head_forward = forward
                    self.last_head_up = up
                    self.last_yaw_rad = yaw_rad
                    self.last_head_quality = float(len(selected))
                    head_position = {
                        "x": round(float(base_head_position[0]), 4),
                        "y": round(float(base_head_position[1]), 4),
                        "z": round(float(base_head_position[2]), 4),
                    }
                observation = {
                    "kind": "Face",
                    "id": "face",
                    "quality": round(float(len(selected) if selected else 0), 0),
                    "center": [
                        round(float(selected[1].x) * w, 1) if selected else w / 2,
                        round(float(selected[1].y) * h, 1) if selected else h / 2,
                    ],
                    "positionM": head_position,
                }
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
                face_dots = None
                if selected is not None:
                    face_dots = [(int(landmark.x * w), int(landmark.y * h)) for landmark in selected[::12]]
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
            if data.get("type") == "sync":
                # NTP-style exchange: the browser estimates the monotonic-clock
                # offset from the round trip and uses it for a one-way local-hop
                # estimate. It is deliberately labelled an estimate in the UI.
                received_ms = now_ms()
                await ws.send_json(
                    {
                        "type": "sync_ack",
                        "t0": data.get("t0"),
                        "serverReceivedMs": received_ms,
                        "serverSentMs": now_ms(),
                    }
                )
            elif data.get("type") == "calibrate":
                ok, text = tracker.calibrate()
                await tracker.broadcast({"type": "notice", "ok": ok, "message": text})
            elif data.get("type") == "calibrate_saber_reference":
                ok, text = tracker.calibrate_saber_reference()
                await tracker.broadcast({"type": "notice", "ok": ok, "message": text})
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
    app["tracker"].start_osc(loop)
    app["tracker"].start_serial(loop)
    app["tracker"].unity_hub.start(app["tracker"].handle_unity_command)
    app["capture_task"] = asyncio.create_task(app["tracker"].capture_loop(app))


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
    parser = argparse.ArgumentParser(description="Head audio + saber tracking prototype")
    parser.add_argument("--host", default="127.0.0.1", help="Local host to listen on (default: 127.0.0.1)")
    parser.add_argument("--port", type=int, default=8765)
    parser.add_argument(
        "--camera",
        default=None,
        help="Camera name substring or OpenCV index; default matches the Mac built-in camera by name",
    )
    parser.add_argument("--list-cameras", action="store_true", help="List cameras and exit")
    parser.add_argument("--width", type=int, default=640)
    parser.add_argument("--height", type=int, default=480)
    parser.add_argument("--fps", type=int, default=30)
    parser.add_argument("--camera-fov", type=float, default=60.0, help="Approximate horizontal camera FOV in degrees")
    parser.add_argument("--mirror-camera", action=argparse.BooleanOptionalAction, default=True, help="Mirror preview and HRTF left/right by default; World stays a room view")
    parser.add_argument("--serial", default=None, help="Optional Arduino port, or 'auto' for /dev/cu.usbmodem*; omitted = iPhone OSC IMU")
    parser.add_argument("--baud", type=int, default=115200)
    parser.add_argument("--no-iphone", action="store_true", help="Do not listen for TouchOSC IMU/haptic on UDP")
    parser.add_argument("--osc-bind", default="0.0.0.0", help="UDP bind address for TouchOSC (default: all interfaces)")
    parser.add_argument("--osc-port", type=int, default=8000, help="UDP port the Mac receives /imu on")
    parser.add_argument("--iphone-port", type=int, default=9000, help="UDP port TouchOSC listens on for /vibrate")
    parser.add_argument("--iphone-host", default=None, help="Force iPhone IP for /vibrate; default is the last OSC sender")
    parser.add_argument("--gyro-scale", type=float, default=1.0, help="Multiply incoming gyro; the TouchOSC layout already converts rad/s to deg/s")
    parser.add_argument("--face-model", default=str(ROOT / "assets" / "face_landmarker.task"))
    parser.add_argument("--pose-model", default=str(ROOT / "assets" / "pose_landmarker_lite.task"))
    parser.add_argument("--saber-hand", choices=("auto", "left", "right"), default="auto", help="Which Pose Landmarker wrist is the saber handle")
    parser.add_argument("--pose-fps", type=float, default=12.0, help="Pose wrist rate; 0 disables Pose for lowest head-audio latency")
    parser.add_argument("--preview-fps", type=float, default=12.0, help="Diagnostic MJPEG preview rate; it is not part of audio timing")
    parser.add_argument("--unity-host", default="127.0.0.1", help="UDP host for Unity pose packets")
    parser.add_argument("--unity-port", type=int, default=8766, help="UDP port Unity listens on for pose")
    parser.add_argument("--unity-command-port", type=int, default=8767, help="UDP port Python listens on for Unity commands")
    return parser.parse_args()


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
    if not args.no_iphone:
        print(
            f"iPhone IMU pose: UDP Host {lan_ipv4()}, Port {args.osc_port}, OSC, enable GYRO + QUATERNION (and GRAVITY if listed)."
        )
        print(
            f"Optional TouchOSC haptic: same Host, Send {args.osc_port}, Receive {args.iphone_port}."
        )
    print(f"Unity pose UDP {args.unity_host}:{args.unity_port}  commands :{args.unity_command_port}")
    web.run_app(app, host=args.host, port=args.port, access_log=None)


if __name__ == "__main__":
    main()
