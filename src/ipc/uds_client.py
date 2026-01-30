"""
Unix Domain Socket client with MessagePack framing.
"""

from __future__ import annotations

import socket
import struct
import threading
import uuid
from dataclasses import dataclass
from typing import Any, Dict, Optional

import msgpack


class IPCError(RuntimeError):
    """Raised when IPC request fails or backend returns an error."""


@dataclass
class IPCResponse:
    """IPC response payload."""
    data: Dict[str, Any]


class UDSMessageClient:
    """
    Simple request/response client over Unix Domain Socket.

    Protocol:
    - MessagePack encoded dict
    - 4-byte big-endian length prefix
    """

    def __init__(self, socket_path: str, timeout_ms: int = 3000):
        self.socket_path = socket_path
        self.timeout = max(timeout_ms, 100) / 1000.0
        self._sock: Optional[socket.socket] = None
        self._lock = threading.Lock()

    def connect(self) -> None:
        if self._sock:
            return

        sock = socket.socket(socket.AF_UNIX, socket.SOCK_STREAM)
        sock.settimeout(self.timeout)
        sock.connect(self.socket_path)
        self._sock = sock

    def close(self) -> None:
        if not self._sock:
            return
        try:
            self._sock.close()
        finally:
            self._sock = None

    def request(self, action: str, payload: Optional[Dict[str, Any]] = None) -> IPCResponse:
        request_id = str(uuid.uuid4())
        message = {
            "id": request_id,
            "type": "request",
            "action": action,
            "payload": payload or {},
        }

        packed = msgpack.packb(message, use_bin_type=True)
        frame = struct.pack("!I", len(packed)) + packed

        with self._lock:
            try:
                self.connect()
                self._sendall(frame)
                response = self._recv_message()
            except (OSError, msgpack.ExtraData, msgpack.FormatError) as exc:
                self.close()
                raise IPCError(f"IPC transport error: {exc}") from exc

        if response.get("type") != "response" or response.get("id") != request_id:
            raise IPCError("IPC protocol error: unexpected response")

        if response.get("error"):
            error = response["error"]
            message = error.get("message", "Unknown IPC error")
            raise IPCError(message)

        return IPCResponse(data=response.get("payload", {}))

    def _sendall(self, data: bytes) -> None:
        if not self._sock:
            raise IPCError("Socket is not connected")
        self._sock.sendall(data)

    def _recv_exact(self, size: int) -> bytes:
        if not self._sock:
            raise IPCError("Socket is not connected")
        buf = bytearray()
        while len(buf) < size:
            chunk = self._sock.recv(size - len(buf))
            if not chunk:
                raise IPCError("Socket closed by peer")
            buf.extend(chunk)
        return bytes(buf)

    def _recv_message(self) -> Dict[str, Any]:
        header = self._recv_exact(4)
        (length,) = struct.unpack("!I", header)
        payload = self._recv_exact(length)
        return msgpack.unpackb(payload, raw=False)
