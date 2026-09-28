"""Serialized VTube Studio RPC: one reader, bounded waits, explicit socket lifecycle."""

import ipaddress
import json
import logging
import os
import tempfile
import threading
import time
from pathlib import Path
from uuid import uuid4

from platformdirs import user_data_path
from websockets.sync.client import ClientConnection, connect

from alicia_core.errors import ToolError
from alicia_core.jsonutil import items, obj, string

logger = logging.getLogger(__name__)


class VTubeStudioAvatar:
    def __init__(self, host: str, port: int = 8001, token_path: Path | None = None) -> None:
        address = ipaddress.ip_address(host)
        if not address.is_loopback or not 1 <= port <= 65535:
            raise ValueError("VTube Studio requiere una dirección loopback y puerto válido.")
        host_part = f"[{host}]" if address.version == 6 else host
        self.uri = f"ws://{host_part}:{port}"
        self.token_path = token_path or user_data_path("Alicia", "Adrix") / "vts_token.txt"
        self._socket: ClientConnection | None = None
        self._lock = threading.RLock()
        self._expressions: tuple[str, ...] = ()

    def _request(self, kind: str, data: dict[str, object], timeout: float = 5) -> dict[str, object]:
        with self._lock:
            if self._socket is None:
                raise ToolError("Avatar desconectado.")
            identifier = uuid4().hex
            self._socket.send(
                json.dumps(
                    {
                        "apiName": "VTubeStudioPublicAPI",
                        "apiVersion": "1.0",
                        "requestID": identifier,
                        "messageType": kind,
                        "data": data,
                    }
                )
            )
            deadline = time.monotonic() + timeout
            while time.monotonic() < deadline:
                message = obj(json.loads(self._socket.recv(timeout=max(0.01, deadline - time.monotonic()))))
                if message.get("requestID") == identifier:
                    if message.get("messageType") == "APIError":
                        raise ToolError("VTube Studio rechazó la operación.")
                    return obj(message.get("data"))
            raise ToolError("VTube Studio agotó el tiempo de espera.")

    def _save_token(self, token: str) -> None:
        self.token_path.parent.mkdir(parents=True, exist_ok=True, mode=0o700)
        fd, temp = tempfile.mkstemp(dir=self.token_path.parent)
        try:
            with os.fdopen(fd, "w", encoding="utf-8") as stream:
                stream.write(token)
            os.replace(temp, self.token_path)
            self.token_path.chmod(0o600)
        finally:
            Path(temp).unlink(missing_ok=True)

    def connect(self) -> bool:
        try:
            self._socket = connect(self.uri, open_timeout=10, close_timeout=3, max_size=1_000_000)
            token = self.token_path.read_text(encoding="utf-8").strip() if self.token_path.exists() else ""
            details: dict[str, object] = {"pluginName": "Alicia", "pluginDeveloper": "Adrix"}
            if (
                token
                and self._request("AuthenticationRequest", {**details, "authenticationToken": token}).get(
                    "authenticated"
                )
                is True
            ):
                return True
            token = string(
                self._request("AuthenticationTokenRequest", details, timeout=60).get("authenticationToken")
            )
            if (
                not token
                or self._request("AuthenticationRequest", {**details, "authenticationToken": token}).get(
                    "authenticated"
                )
                is not True
            ):
                raise ToolError("Autenticación rechazada.")
            self._save_token(token)
            return True
        except Exception:
            logger.warning("avatar_connection_failed")
            self.close()
            return False

    def list_expressions(self) -> list[dict[str, str]]:
        try:
            data = self._request("ExpressionStateRequest", {"details": False})
            expressions = [obj(v) for v in items(data.get("expressions", []))]
            result = [
                {"name": string(e.get("name", "")), "file": string(e.get("file", ""))} for e in expressions
            ]
            self._expressions = tuple(e["file"] for e in result if e["file"])
            return result
        except Exception:
            logger.warning("avatar_catalog_failed")
            return []

    def list_parameters(self) -> list[str]:
        data = self._request("InputParameterListRequest", {})
        return [string(obj(p).get("name")) for p in items(data.get("defaultParameters", []))]

    def trigger_expression(self, expression_file: str) -> str:
        if expression_file not in self._expressions:
            raise ToolError("Expresión no permitida.")
        try:
            self._request("ExpressionActivationRequest", {"expressionFile": expression_file, "active": True})
            return "Expresión activada."
        except Exception as exc:
            raise ToolError("No se pudo activar la expresión.") from exc

    def set_mouth_open(self, value: float) -> None:
        if self._socket is None:
            return
        try:
            self._request(
                "InjectParameterDataRequest",
                {
                    "faceFound": False,
                    "mode": "set",
                    "parameterValues": [{"id": "MouthOpen", "value": max(0.0, min(1.0, value))}],
                },
                timeout=0.25,
            )
        except Exception:
            logger.warning("avatar_lipsync_failed")
            self.close()

    def close(self) -> None:
        with self._lock:
            if self._socket:
                self._socket.close()
                self._socket = None
