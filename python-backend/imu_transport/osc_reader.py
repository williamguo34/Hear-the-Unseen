"""iPhone OSC IMU (ZIG SIM or TouchOSC). Same sample dict as the serial reader."""

from __future__ import annotations

import threading
from dataclasses import dataclass
from typing import Any, Callable, Optional

from timebase import now_ms


@dataclass
class OscHooks:
    on_sample: Callable[[dict[str, float]], None]
    on_notice: Callable[[str], None]


class OscImuReader:
    """Receive iPhone IMU samples over UDP (ZIG SIM OSC, optional TouchOSC)."""

    STALE_MS = 800.0

    def __init__(
        self,
        bind: str,
        port: int,
        iphone_port: int,
        gyro_scale: float,
        hooks: "OscHooks",
        iphone_host: Optional[str] = None,
    ) -> None:
        try:
            from pythonosc.dispatcher import Dispatcher
            from pythonosc.osc_server import BlockingOSCUDPServer
            from pythonosc.udp_client import SimpleUDPClient
        except ImportError as error:
            raise RuntimeError("python-osc is not installed. Run run.zsh or run.ps1 once.") from error
        self.hooks = hooks
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
        self.hooks.on_sample(sample)

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
        self.hooks.on_notice(f"iPhone haptic test from {self.phone_ip}.")

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
        self.hooks.on_sample(sample)

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
