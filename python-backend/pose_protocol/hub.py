"""UDP pose out, command datagrams in. The dict shape lives in message.py."""

from __future__ import annotations

import json
import socket
import threading
from typing import Any, Optional

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
