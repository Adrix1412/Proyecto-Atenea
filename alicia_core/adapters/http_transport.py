"""Bounded HTTP transport; credentials never appear in exception messages."""

import json
import logging
import time
from collections.abc import Callable

import httpx

from alicia_core.errors import ProviderError
from alicia_core.jsonutil import obj

logger = logging.getLogger(__name__)


class HTTPTransport:
    def __init__(
        self,
        timeout: float,
        client: httpx.Client | None = None,
        sleeper: Callable[[float], None] = time.sleep,
    ) -> None:
        self._owned = client is None
        self._sleeper = sleeper
        self.client = client or httpx.Client(
            timeout=httpx.Timeout(timeout, connect=10), follow_redirects=False, trust_env=False
        )

    def post(self, url: str, payload: dict[str, object], headers: dict[str, str]) -> dict[str, object]:
        try:
            for attempt in range(3):
                with self.client.stream("POST", url, json=payload, headers=headers) as response:
                    if response.status_code == 200:
                        data = bytearray()
                        for chunk in response.iter_bytes(chunk_size=8192):
                            data.extend(chunk)
                            if len(data) > 2_000_000:
                                raise ProviderError("La respuesta del proveedor excede el límite permitido.")
                        return obj(json.loads(data))
                    retryable = response.status_code in (429, 503)
                    if not retryable or attempt == 2:
                        logger.warning("provider_http_error status=%d", response.status_code)
                        raise ProviderError(
                            "El proveedor rechazó la solicitud. Revise modelo, credenciales y cuota."
                        )
                    delay = self._retry_delay(response.headers.get("retry-after"), attempt)
                logger.info("provider_retry status=%d attempt=%d", response.status_code, attempt + 1)
                self._sleeper(delay)
            raise AssertionError("Bucle de reintento terminado sin resultado.")
        except httpx.TimeoutException as exc:
            raise ProviderError("El proveedor agotó el tiempo de espera.") from exc
        except (httpx.HTTPError, ValueError, UnicodeError) as exc:
            raise ProviderError("No se pudo obtener una respuesta válida del proveedor.") from exc

    @staticmethod
    def _retry_delay(value: str | None, attempt: int) -> float:
        try:
            return min(5.0, max(0.1, float(value))) if value is not None else float(attempt + 1)
        except ValueError:
            return float(attempt + 1)

    def close(self) -> None:
        if self._owned:
            self.client.close()
