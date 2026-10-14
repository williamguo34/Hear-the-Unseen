"""Arduino serial IMU. Samples leave through hooks; this module does not fuse them."""

from __future__ import annotations

import math
import platform
import threading
import time
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Callable, Optional

from timebase import now_ms


def usb_serial_candidates() -> list[str]:
    """USB serial ports that --serial auto may open. One match is required."""
    if platform.system() == "Windows":
        from serial.tools import list_ports

        devices = [port.device for port in list_ports.comports() if port.vid is not None]
        return sorted(set(devices), key=str.casefold)
    root = Path("/dev")
    return [str(path) for path in sorted(root.glob("cu.usbmodem*")) + sorted(root.glob("cu.usbserial*"))]


def port_still_present(device: str) -> bool:
    if platform.system() == "Windows":
        from serial.tools import list_ports

        wanted = device.casefold()
        return any(port.device.casefold() == wanted for port in list_ports.comports())
    return Path(device).exists()


@dataclass
class SerialHooks:
    on_sample: Callable[[dict[str, float]], None]
    on_notice: Callable[[str], None]
    on_button: Callable[[], None]
    on_still_begin: Callable[[], None]
    on_still_done: Callable[[], None]
    on_gyro_reset: Callable[[], None]
    on_status: Callable[[], None]
    mag_status: Callable[[], Any]
    imu_snapshot: Callable[[], Optional[dict[str, Any]]]


class SerialImuReader:
    """Receive six-axis samples and optional raw magnetic telemetry.

    The tracker is not imported. Callers pass hooks for samples, the button,
    the still window, and link status.
    """

    MAG_STALE_SECONDS = 0.5
    IMU_STALE_SECONDS = 0.8
    RECONNECT_SECONDS = 1.0
    SERIAL_IDLE_SECONDS = 3.0
    STATUS_PERIOD_SECONDS = 0.25

    def __init__(self, device: str, baud: int, hooks: "SerialHooks") -> None:
        try:
            import serial
        except ImportError as error:
            raise RuntimeError("pyserial is not installed. Run run.zsh or run.ps1 once.") from error
        self.hooks = hooks
        self.stop_requested = threading.Event()
        self.write_lock = threading.Lock()
        self.port_factory = serial.Serial
        self.port = None
        self.requested_device = device
        self.device = device
        self.baud = baud
        self.error: Optional[str] = None
        self.last_imu_at: Optional[float] = None
        self.last_serial_activity_at: Optional[float] = None
        self.resume_pending = True
        self.mag_sample: Optional[dict[str, float]] = None
        self.mag_received_at = 0.0
        self.mpu_state = "waiting"
        self.mag_state = "waiting"
        self.last_status_at: Optional[float] = None
        self.thread = threading.Thread(target=self.read_loop, name="mpu6050-serial", daemon=True)
        self.thread.start()

    def clear_samples(self) -> None:
        self.mag_sample = None
        self.mag_received_at = 0.0
        self.last_imu_at = None
        self.resume_pending = True
        self.mpu_state = self.mag_state = "waiting"

    def report_error(self, message: str) -> None:
        if self.error != message:
            self.hooks.on_notice(message)
        self.error = message

    def open_port(self) -> None:
        device = self.requested_device
        if device == "auto":
            candidates = usb_serial_candidates()
            if self.device != "auto" and port_still_present(self.device):
                device = self.device
            elif len(candidates) == 1:
                device = candidates[0]
            else:
                raise OSError("Connect a single Arduino for --serial auto, or specify its port.")
        with self.write_lock:
            port = self.port_factory(device, baudrate=self.baud, timeout=0.1, write_timeout=0.1)
            if self.stop_requested.is_set():
                port.close()
                return
            self.port = port
            self.device = device
        self.clear_samples()
        self.last_serial_activity_at = time.monotonic()
        self.hooks.on_gyro_reset()

    def close_port(self) -> None:
        with self.write_lock:
            port, self.port = self.port, None
            if port is not None:
                try:
                    port.close()
                except Exception:
                    pass
        self.clear_samples()
        self.last_serial_activity_at = None

    def link_status(self) -> dict[str, Any]:
        port, last_imu_at = self.port, self.last_imu_at
        port_connected = port is not None and port.is_open and self.thread.is_alive()
        now = time.monotonic()
        age = None if last_imu_at is None else max(0.0, now - last_imu_at)
        connected = port_connected and age is not None and age <= self.IMU_STALE_SECONDS
        mag_sample, mag_at = self.mag_sample, self.mag_received_at
        mag_age = None if mag_sample is None else max(0.0, now - mag_at)
        mag_connected = port_connected and mag_age is not None and mag_age <= self.MAG_STALE_SECONDS
        mpu_state = "online" if connected else ("stale" if age is not None else self.mpu_state)
        mag_state = "online" if mag_connected else ("stale" if mag_age is not None else self.mag_state)
        if not port_connected:
            mpu_state = mag_state = "unavailable"
        elif not connected:
            # Firmware pauses MAG polling while recovering the shared MPU bus.
            mag_state = "paused"
            mag_connected = False
        imu = self.hooks.imu_snapshot() or {}
        return {
            "connected": connected, "source": "arduino", "device": self.device,
            "portConnected": port_connected, "reconnecting": not connected,
            "ageMs": None if age is None else round(age * 1000),
            "error": None if connected else self.error or "No fresh IMU data; waiting for automatic recovery. Check sensor wiring.",
            "magUsed": connected and mag_connected and bool(imu.get("magUsed")),
            "magCalibration": self.hooks.mag_status(),
            "sensors": {
                "mpu": {"connected": connected, "state": mpu_state,
                        "ageMs": None if age is None else round(age * 1000)},
                "mag": {"connected": mag_connected, "state": mag_state,
                        "ageMs": None if mag_age is None else round(mag_age * 1000)},
            },
        }

    def publish_link_status(self, force: bool = False) -> None:
        now = time.monotonic()
        if force or self.last_status_at is None or now - self.last_status_at >= self.STATUS_PERIOD_SECONDS:
            self.last_status_at = now
            # Keep sensor warnings live even when camera frames stop arriving.
            self.hooks.on_status()

    def read_loop(self) -> None:
        while not self.stop_requested.is_set():
            self.publish_link_status()
            try:
                if self.port is None:
                    self.open_port()
                    if self.stop_requested.is_set():
                        break
                line = self.port.readline(256).decode("utf-8", errors="replace").strip()
            except Exception as error:  # The USB cable can be unplugged mid-demo.
                self.close_port()
                if self.stop_requested.is_set():
                    break
                self.report_error(f"Arduino serial disconnected; retrying: {error}")
                self.publish_link_status(force=True)
                self.stop_requested.wait(self.RECONNECT_SECONDS)
                continue
            if self.stop_requested.is_set():
                break
            if not line:
                last_activity = getattr(self, "last_serial_activity_at", None)
                if last_activity is not None and time.monotonic() - last_activity >= self.SERIAL_IDLE_SECONDS:
                    # A USB device can remain open after its UART/firmware stalls.
                    # Closing/reopening restores the link (and resets a standard
                    # Uno via DTR). Active firmware OFF/error messages instead
                    # leave bus recovery to the board, without repeated resets.
                    self.close_port()
                    self.report_error("Arduino serial silent for 3 seconds; reopening the connection. Recalibrate the gyro after recovery.")
                    self.publish_link_status(force=True)
                    self.stop_requested.wait(self.RECONNECT_SECONDS)
                continue
            received_at = time.monotonic()
            self.last_serial_activity_at = received_at
            if line.startswith("BOOT,") or line == "STATUS,MPU,OFF":
                if line.startswith("BOOT,"):
                    self.hooks.on_gyro_reset()
                self.clear_samples()
                self.error = "MPU offline / restarting; waiting for automatic recovery."
                if line == "STATUS,MPU,OFF":
                    self.mpu_state = "offline"
                self.publish_link_status(force=True)
                continue
            if line == "STATUS,MPU,READY":
                self.mpu_state = "waiting"  # Confirm live data, not just ACK.
                continue
            if line == "CALIBRATING":
                self.hooks.on_still_begin()
                continue
            if line == "CALIBRATE":
                self.hooks.on_button()
                continue
            if line == "GYRO_READY":
                self.hooks.on_still_done()
                continue
            if line == "STATUS,MAG,OFF":
                self.mag_sample = None
                self.mag_state = "offline"
                self.publish_link_status(force=True)
                continue
            if line == "STATUS,MAG,READY":
                self.mag_sample = None
                self.mag_state = "waiting"
                continue
            magnetic = self.parse_mag_line(line)
            if magnetic is not None:
                self.mag_sample = magnetic
                self.mag_received_at = received_at
                self.mag_state = "online"
                continue
            sample = self.parse_imu_line(line)
            if sample is not None:
                if self.mag_sample is not None and received_at - self.mag_received_at <= self.MAG_STALE_SECONDS:
                    sample.update(self.mag_sample)
                # Stay on this thread until BLOCK is written. Hopping to the
                # asyncio loop first used to wait behind camera detection.
                if self.resume_pending or self.last_imu_at is None or received_at - self.last_imu_at > self.IMU_STALE_SECONDS:
                    sample["streamResumed"] = 1.0
                try:
                    self.hooks.on_sample(sample)
                except Exception as error:
                    # A bad frame/consumer must not silently kill the reader.
                    self.report_error(f"Arduino IMU processing failed; continuing: {error}")
                    continue
                self.resume_pending = False
                self.last_imu_at = received_at
                self.mpu_state = "online"
                self.error = None
        self.close_port()

    @staticmethod
    def parse_imu_line(line: str) -> Optional[dict[str, float]]:
        # Firmware format: IMU,device_micros,gx_deg_s,gy_deg_s,gz_deg_s,ax_g,ay_g,az_g
        # ComplementaryAttitude integrates angular rate in rad/s, so convert
        # exactly once at this serial boundary.
        fields = line.split(",")
        if len(fields) != 8 or fields[0] != "IMU":
            return None
        try:
            gx_deg_s, gy_deg_s, gz_deg_s = (float(fields[index]) for index in (2, 3, 4))
            sample = {
                "deviceUs": float(fields[1]),
                "gx": math.radians(gx_deg_s),
                "gy": math.radians(gy_deg_s),
                "gz": math.radians(gz_deg_s),
                "ax": float(fields[5]), "ay": float(fields[6]), "az": float(fields[7]),
                "arduino": 1.0,
            }
            return sample if all(math.isfinite(value) for value in sample.values()) else None
        except ValueError:
            return None

    @staticmethod
    def parse_mag_line(line: str) -> Optional[dict[str, float]]:
        # Separate low-rate frames preserve the existing eight-field IMU protocol.
        # Preserve raw sensor-frame counts; map axes later at the fusion boundary.
        fields = line.split(",")
        if len(fields) != 5 or fields[0] != "MAG":
            return None
        try:
            values = [float(value) for value in fields[1:]]
            if not all(math.isfinite(value) for value in values):
                return None
            return dict(zip(("magDeviceUs", "mxRaw", "myRaw", "mzRaw"), values))
        except ValueError:
            return None

    def send_block(self) -> Optional[float]:
        return now_ms() if self._write_command(b"BLOCK\n") else None

    def send_still(self) -> bool:
        return self._write_command(b"STILL\n")

    def _write_command(self, command: bytes) -> bool:
        try:
            with self.write_lock:
                if self.port is None:
                    return False
                self.port.write(command)
                self.port.flush()
            return True
        except Exception:
            return False

    def close(self) -> None:
        self.stop_requested.set()
        self.close_port()
        self.thread.join(timeout=0.5)
