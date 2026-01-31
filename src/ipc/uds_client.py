"""
Unix Domain Socket client with MessagePack framing.
"""

from __future__ import annotations

import asyncio
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
    Unified sync/async request/response client over Unix Domain Socket.

    底层使用异步实现，同时提供同步和异步两种调用方式。

    Protocol:
    - MessagePack encoded dict
    - 4-byte big-endian length prefix

    Usage (sync):
        client = UDSMessageClient("/tmp/ipc.sock")
        response = client.request("action", {"key": "value"})

    Usage (async):
        client = UDSMessageClient("/tmp/ipc.sock")
        response = await client.request_async("action", {"key": "value"})

    Usage (async context manager):
        async with UDSMessageClient("/tmp/ipc.sock") as client:
            response = await client.request_async("action", {"key": "value"})
    """

    def __init__(self, socket_path: str, timeout: float = 3.0):
        """
        Initialize the client.

        Args:
            socket_path: Path to the Unix domain socket.
            timeout: Timeout in seconds for operations.
        """
        self.socket_path = socket_path
        self.timeout = max(timeout, 0.1)
        self._reader: Optional[asyncio.StreamReader] = None
        self._writer: Optional[asyncio.StreamWriter] = None
        self._async_lock = asyncio.Lock()
        self._sync_lock = threading.Lock()
        self._loop: Optional[asyncio.AbstractEventLoop] = None

    # ==================== Async Methods ====================

    async def connect_async(self) -> None:
        """Establish async connection to the Unix domain socket."""
        if self._reader is not None and self._writer is not None:
            return

        try:
            self._reader, self._writer = await asyncio.wait_for(
                asyncio.open_unix_connection(self.socket_path),
                timeout=self.timeout,
            )
        except asyncio.TimeoutError as exc:
            raise IPCError(f"Connection timeout: {self.socket_path}") from exc
        except OSError as exc:
            raise IPCError(f"Connection failed: {exc}") from exc

    async def close_async(self) -> None:
        """Close the async connection."""
        if self._writer:
            try:
                self._writer.close()
                await self._writer.wait_closed()
            except Exception:
                pass
            finally:
                self._reader = None
                self._writer = None

    async def request_async(
        self, action: str, payload: Optional[Dict[str, Any]] = None
    ) -> IPCResponse:
        """
        Send an async request and wait for response.

        Args:
            action: The action name to invoke.
            payload: Optional payload dict.

        Returns:
            IPCResponse containing the response data.

        Raises:
            IPCError: On transport or protocol errors.
        """
        request_id = str(uuid.uuid4())
        message = {
            "id": request_id,
            "type": "request",
            "action": action,
            "payload": payload or {},
        }

        packed = msgpack.packb(message, use_bin_type=True)
        frame = struct.pack("!I", len(packed)) + packed

        async with self._async_lock:
            try:
                await self.connect_async()
                await self._sendall_async(frame)
                response = await self._recv_message_async()
            except (OSError, msgpack.ExtraData, msgpack.FormatError) as exc:
                await self.close_async()
                raise IPCError(f"IPC transport error: {exc}") from exc
            except asyncio.TimeoutError as exc:
                await self.close_async()
                raise IPCError(f"IPC timeout: {exc}") from exc

        if response.get("type") != "response" or response.get("id") != request_id:
            raise IPCError("IPC protocol error: unexpected response")

        if response.get("error"):
            error = response["error"]
            err_message = error.get("message", "Unknown IPC error")
            raise IPCError(err_message)

        return IPCResponse(data=response.get("payload", {}))

    async def _sendall_async(self, data: bytes) -> None:
        """Send all data through the async socket."""
        if not self._writer:
            raise IPCError("Socket is not connected")
        self._writer.write(data)
        await asyncio.wait_for(self._writer.drain(), timeout=self.timeout)

    async def _recv_exact_async(self, size: int) -> bytes:
        """Receive exact number of bytes asynchronously."""
        if not self._reader:
            raise IPCError("Socket is not connected")
        try:
            data = await asyncio.wait_for(
                self._reader.readexactly(size),
                timeout=self.timeout,
            )
            return data
        except asyncio.IncompleteReadError as exc:
            raise IPCError("Socket closed by peer") from exc

    async def _recv_message_async(self) -> Dict[str, Any]:
        """Receive and decode a MessagePack message asynchronously."""
        header = await self._recv_exact_async(4)
        (length,) = struct.unpack("!I", header)
        payload = await self._recv_exact_async(length)
        return msgpack.unpackb(payload, raw=False)

    async def __aenter__(self) -> "UDSMessageClient":
        """Async context manager entry."""
        await self.connect_async()
        return self

    async def __aexit__(self, exc_type, exc_val, exc_tb) -> None:
        """Async context manager exit."""
        await self.close_async()

    # ==================== Sync Methods ====================

    def _get_or_create_event_loop(self) -> asyncio.AbstractEventLoop:
        """Get running event loop or create a new one for sync operations."""
        try:
            loop = asyncio.get_running_loop()
            return loop
        except RuntimeError:
            # No running loop, create one for this thread
            if self._loop is None or self._loop.is_closed():
                self._loop = asyncio.new_event_loop()
            return self._loop

    def _run_sync(self, coro):
        """Run a coroutine synchronously."""
        try:
            # Check if we're already in an async context
            asyncio.get_running_loop()
            # If we get here, we're in an async context - can't use run_until_complete
            raise RuntimeError(
                "Cannot use sync methods from async context. Use async methods instead."
            )
        except RuntimeError:
            # No running loop - safe to run synchronously
            pass

        with self._sync_lock:
            loop = self._get_or_create_event_loop()
            try:
                return loop.run_until_complete(coro)
            except Exception:
                # Clean up connection on error
                if self._writer:
                    loop.run_until_complete(self.close_async())
                raise

    def connect(self) -> None:
        """Establish sync connection to the Unix domain socket."""
        self._run_sync(self.connect_async())

    def close(self) -> None:
        """Close the connection synchronously."""
        try:
            asyncio.get_running_loop()
            # In async context, schedule close
            if self._writer:
                self._writer.close()
                self._reader = None
                self._writer = None
        except RuntimeError:
            # Not in async context
            if self._loop and not self._loop.is_closed():
                self._loop.run_until_complete(self.close_async())
            if self._loop and not self._loop.is_closed():
                self._loop.close()
                self._loop = None

    def request(
        self, action: str, payload: Optional[Dict[str, Any]] = None
    ) -> IPCResponse:
        """
        Send a sync request and wait for response.

        Args:
            action: The action name to invoke.
            payload: Optional payload dict.

        Returns:
            IPCResponse containing the response data.

        Raises:
            IPCError: On transport or protocol errors.
            RuntimeError: If called from async context.
        """
        return self._run_sync(self.request_async(action, payload))

    def __enter__(self) -> "UDSMessageClient":
        """Sync context manager entry."""
        self.connect()
        return self

    def __exit__(self, exc_type, exc_val, exc_tb) -> None:
        """Sync context manager exit."""
        self.close()


# Keep backward compatibility alias
AsyncUDSMessageClient = UDSMessageClient
