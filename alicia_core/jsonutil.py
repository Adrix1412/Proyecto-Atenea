"""Runtime narrowing for untrusted JSON without leaking Any into the domain."""

from alicia_core.errors import ProviderError


def obj(value: object) -> dict[str, object]:
    if not isinstance(value, dict) or not all(isinstance(k, str) for k in value):
        raise ProviderError("Respuesta JSON inválida del proveedor.")
    return {str(k): v for k, v in value.items()}


def items(value: object) -> list[object]:
    if not isinstance(value, list):
        raise ProviderError("Respuesta JSON inválida del proveedor.")
    return list(value)


def string(value: object) -> str:
    if not isinstance(value, str):
        raise ProviderError("Respuesta JSON inválida del proveedor.")
    return value
