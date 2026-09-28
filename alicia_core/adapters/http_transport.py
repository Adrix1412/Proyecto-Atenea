"""Bounded HTTP transport; credentials never appear in exception messages."""

import json
import logging

import httpx

from alicia_core.errors import ProviderError
from alicia_core.jsonutil import obj

logger = logging.getLogger(__name__)


class HTTPTransport:
    def __init__(self, timeout: float, client: httpx.Client | None = None) -> None:
        self._owned = client is None
        self.client = client or httpx.Client(
            timeout=httpx.Timeout(timeout, connect=10), follow_redirects=False, trust_env=False
        )

    def post(self, url: str, payload: dict[str, object], headers: dict[str, str]) -> dict[str, object]:
        try:
            with self.client.stream("POST", url, json=payload, headers=headers) as response:
                if response.status_code != 200:
                    logger.warning("provider_http_error status=%d", response.status_code)
                    raise ProviderError(
                        "El proveedor rechazó la solicitud. Revise modelo, credenciales y cuota."
                    )
                data = bytearray()
                for chunk in response.iter_bytes(chunk_size=8192):
                    data.extend(chunk)
                    if len(data) > 2_000_000:
                        raise ProviderError("La respuesta del proveedor excede el límite permitido.")
                return obj(json.loads(data))
        except httpx.TimeoutException as exc:
            raise ProviderError("El proveedor agotó el tiempo de espera.") from exc
        except (httpx.HTTPError, ValueError, UnicodeError) as exc:
            raise ProviderError("No se pudo obtener una respuesta válida del proveedor.") from exc

    def close(self) -> None:
        if self._owned:
            self.client.close()
