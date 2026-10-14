"""Pick the built-in camera. Skips Continuity Camera, iPhone, Desk View, and virtual cameras."""

from __future__ import annotations

import json
import os
import platform
import re
import subprocess
import sys
import tempfile
import time
from pathlib import Path
from typing import Optional

_PHONE_CAMERA_RE = re.compile(
    r"iphone|ipad|continuity|desk\s*view|桌上视角|sidecar",
    re.IGNORECASE,
)
_SCREEN_CAMERA_RE = re.compile(r"capture\s+screen|screen\s+recording", re.IGNORECASE)
_AUDIO_DEVICE_RE = re.compile(r"microphone|麦克风|audio", re.IGNORECASE)
_VIRTUAL_CAMERA_RE = re.compile(r"\bvirtual\b|\bobs\b|manycam|snap camera|\bndi\b", re.IGNORECASE)
_BUILTIN_CAMERA_RE = re.compile(
    r"facetime|built[- ]in|macbook|imac\b|integrated (?:camera|webcam)",
    re.IGNORECASE,
)


def now_ms() -> float:
    """Monotonic time, shared by all server-side stage timestamps."""
    return time.perf_counter_ns() / 1_000_000.0


def list_cameras() -> list[tuple[int, str]]:
    """Return cameras in the same order OpenCV will open them."""
    if platform.system() == "Windows":
        return _windows_cameras()
    return list_macos_cameras()


def list_macos_cameras() -> list[tuple[int, str]]:
    """Return cameras in OpenCV's AVFoundation order, not ffmpeg's."""
    cameras = _opencv_avfoundation_cameras()
    if cameras:
        return cameras
    return _system_profiler_cameras()


def _parse_camera_lines(text: str) -> list[tuple[int, str]]:
    cameras: list[tuple[int, str]] = []
    for line in text.splitlines():
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


def _windows_cameras() -> list[tuple[int, str]]:
    """Media Foundation order, which is OpenCV CAP_MSMF's index order."""
    script = Path(__file__).resolve().parent / "windows_cameras.ps1"
    if not script.is_file():
        return []
    fd, dest = tempfile.mkstemp(prefix="cameras-", suffix=".txt")
    os.close(fd)
    try:
        try:
            result = subprocess.run(
                [
                    "powershell.exe",
                    "-NoProfile",
                    "-ExecutionPolicy",
                    "Bypass",
                    "-File",
                    str(script),
                    dest,
                ],
                capture_output=True,
                text=True,
                encoding="utf-8",
                errors="replace",
                timeout=60,
                creationflags=subprocess.CREATE_NO_WINDOW,
            )
        except (FileNotFoundError, subprocess.TimeoutExpired, AttributeError):
            return []
        if result.returncode != 0:
            message = (result.stderr or "").strip()
            if message:
                print(message, file=sys.stderr)
            return []
        return _parse_camera_lines(Path(dest).read_text(encoding="utf-8"))
    finally:
        Path(dest).unlink(missing_ok=True)


def _opencv_camera_helper() -> Optional[Path]:
    """Compile macos_cameras.swift once; OpenCV indices follow uniqueID sort."""
    source = Path(__file__).resolve().parent / "macos_cameras.swift"
    if not source.is_file():
        return None
    binary = Path(__file__).resolve().parents[2] / ".cache" / "macos_cameras"
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
    return _parse_camera_lines(result.stdout)


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
    """Higher is a better built-in match. Phone, virtual, and screen devices score below zero."""
    if (
        _PHONE_CAMERA_RE.search(name)
        or _SCREEN_CAMERA_RE.search(name)
        or _AUDIO_DEVICE_RE.search(name)
        or _VIRTUAL_CAMERA_RE.search(name)
    ):
        return -1
    if _BUILTIN_CAMERA_RE.search(name):
        return 100
    return 0


def choose_mac_camera(explicit: Optional[str]) -> tuple[int, str]:
    """Pick a camera by name each launch. Indices change when another camera appears."""
    cameras = list_cameras()
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
    cameras = list_cameras()
    if not cameras:
        if platform.system() == "Darwin":
            print("No cameras were listed. Install Xcode command-line tools so macos_cameras.swift can compile.")
        elif platform.system() == "Windows":
            print("No cameras were listed. Check Windows camera privacy, then run --list-cameras again.")
        else:
            print("No cameras were listed.")
        return
    chosen_index, chosen_name = choose_mac_camera(None)
    if platform.system() == "Windows":
        print("OpenCV camera order (Media Foundation, same indices as CAP_MSMF):")
    else:
        print("OpenCV camera order (sorted by AVFoundation uniqueID, not ffmpeg):")
    for index, name in cameras:
        mark = f"  <- auto ({chosen_name})" if index == chosen_index else ""
        print(f"  [{index}] {name}{mark}")
    print("Auto-select prefers the built-in camera. Override with a name substring or --camera N.")
