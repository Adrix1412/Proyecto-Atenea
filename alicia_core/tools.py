"""Closed tool registry with typed arguments and authorization."""

import logging
import secrets
from collections.abc import Callable, Mapping
from dataclasses import dataclass, field, replace
from typing import Generic, Protocol, TypeVar

from pydantic import BaseModel, ValidationError

from .errors import ToolError
from .execution import TaskExecutor, TaskJournal
from .permissions import ActionRequest, PermissionEngine, Risk

logger = logging.getLogger(__name__)
ArgsT = TypeVar("ArgsT", bound=BaseModel)
LegacyConfirm = Callable[[str, str], bool]


class ToolDefinition(Protocol):
    @property
    def name(self) -> str: ...

    @property
    def description(self) -> str: ...

    def schema(self) -> dict[str, object]: ...

    def invoke(self, arguments: Mapping[str, object], confirm: LegacyConfirm | None) -> str: ...


@dataclass(frozen=True)
class Tool:
    """Compatibility adapter for the existing single-string tools."""

    name: str
    description: str
    argument: str
    handler: Callable[[str], str]
    choices: tuple[str, ...] = ()
    max_length: int = 500
    requires_confirmation: bool = False

    def schema(self) -> dict[str, object]:
        prop: dict[str, object] = {"type": "string", "minLength": 1, "maxLength": self.max_length}
        if self.choices:
            prop["enum"] = list(self.choices)
        return {
            "type": "object",
            "properties": {self.argument: prop},
            "required": [self.argument],
            "additionalProperties": False,
        }

    def invoke(self, arguments: Mapping[str, object], confirm: LegacyConfirm | None) -> str:
        value = arguments.get(self.argument)
        if (
            set(arguments) != {self.argument}
            or not isinstance(value, str)
            or not value.strip()
            or len(value) > self.max_length
            or "\x00" in value
            or (self.choices and value not in self.choices)
        ):
            return "Error: argumentos inválidos."
        if self.requires_confirmation and (confirm is None or not confirm(self.name, value)):
            return "Acción denegada: falta confirmación del usuario."
        return self.handler(value)


@dataclass(frozen=True)
class TypedTool(Generic[ArgsT]):
    name: str
    description: str
    args_type: type[ArgsT]
    handler: Callable[[ArgsT], str]
    domain_check: Callable[[ArgsT], bool] | None = None
    authorize: Callable[[ArgsT], bool] | None = None
    requires_confirmation: bool = False
    choices: Mapping[str, tuple[str, ...]] = field(default_factory=dict)
    risk: Risk = Risk.READ

    def __post_init__(self) -> None:
        if self.args_type.model_config.get("extra") != "forbid":
            raise ValueError("Los argumentos deben prohibir propiedades extra.")
        if self.requires_confirmation and self.authorize is None:
            raise ValueError("La herramienta sensible requiere una política.")
        if self.requires_confirmation and self.risk is Risk.READ:
            raise ValueError("Una herramienta sensible no puede declararse de solo lectura.")
        if not set(self.choices).issubset(self.args_type.model_fields):
            raise ValueError("Las opciones deben referirse a campos del esquema.")

    def schema(self) -> dict[str, object]:
        schema = self.args_type.model_json_schema()
        properties = schema.get("properties")
        if isinstance(properties, dict):
            for name, allowed in self.choices.items():
                prop = properties.get(name)
                if isinstance(prop, dict):
                    prop["enum"] = list(allowed)
        return schema

    def prepare(self, arguments: Mapping[str, object]) -> ArgsT | None:
        try:
            parsed = self.args_type.model_validate(dict(arguments), strict=True)
        except ValidationError:
            return None
        if any(getattr(parsed, key) not in allowed for key, allowed in self.choices.items()):
            return None
        if self.domain_check is not None and not self.domain_check(parsed):
            return None
        return parsed

    def invoke(self, arguments: Mapping[str, object], confirm: LegacyConfirm | None) -> str:
        del confirm
        parsed = self.prepare(arguments)
        if parsed is None:
            return "Error: argumentos inválidos."
        if self.requires_confirmation and (self.authorize is None or not self.authorize(parsed)):
            return "Acción denegada: falta confirmación del usuario."
        return self.handler(parsed)


class ToolRegistry:
    def __init__(self, tools: tuple[ToolDefinition, ...] = (), confirm: LegacyConfirm | None = None) -> None:
        if len({t.name for t in tools}) != len(tools):
            raise ValueError("Nombres de herramientas duplicados.")
        self.tools = tools
        self._by_name = {t.name: t for t in tools}
        self._confirm = confirm

    def execute(self, name: str, arguments: Mapping[str, object]) -> str:
        tool = self._by_name.get(name)
        if tool is None:
            return "Error: herramienta no permitida."
        try:
            result = tool.invoke(arguments, self._confirm)
            if not isinstance(result, str):
                raise ToolError("Resultado inválido.")
            return result[:6000]
        except Exception as exc:
            logger.warning("tool_failed tool=%s type=%s", tool.name, type(exc).__name__)
            return "Error: la herramienta no pudo completar la operación."

    def execute_authorized(
        self,
        name: str,
        arguments: Mapping[str, object],
        request: ActionRequest,
        policy: PermissionEngine,
        approval_token: str | None = None,
        journal: TaskJournal | None = None,
    ) -> str:
        """For trusted callers that already authenticated actor and device identity."""
        tool = self._by_name.get(name)
        if not isinstance(tool, TypedTool):
            return "Error: herramienta no permitida para ejecución autorizada."
        try:
            if request.capability != name or request.risk is not tool.risk:
                return "Acción denegada: solicitud incompatible."
            supplied = replace(request, arguments=dict(arguments))
            if not secrets.compare_digest(request.fingerprint(), supplied.fingerprint()):
                return "Acción denegada: argumentos distintos a los aprobados."
            parsed = tool.prepare(arguments)
            if parsed is None:
                return "Error: argumentos inválidos."
            if tool.requires_confirmation and (tool.authorize is None or not tool.authorize(parsed)):
                return "Acción denegada: falta confirmación local."
            result = TaskExecutor(journal).run(request, policy, lambda: tool.handler(parsed), approval_token)
            return result.message
        except Exception as exc:
            logger.warning("authorized_tool_failed tool=%s type=%s", name, type(exc).__name__)
            return "Error: la herramienta no pudo completar la operación."
