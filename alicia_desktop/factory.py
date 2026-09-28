"""Desktop composition: only this module connects tools to OS capabilities."""

from collections.abc import Callable
from pathlib import Path
from typing import Protocol

from alicia_core.adapters.search import web_search
from alicia_core.adapters.sqlite_memory import SQLiteMemory
from alicia_core.llm import LLMClient
from alicia_core.permissions import Risk
from alicia_core.service import ConversationService
from alicia_core.tool_args import ExpressionArgs, OpenAppArgs, SearchArgs
from alicia_core.tools import ToolDefinition, ToolRegistry, TypedTool

from .config import DesktopConfig, resolve_path
from .launcher import AppLauncher


class ExpressionAvatar(Protocol):
    def list_expressions(self) -> list[dict[str, str]]: ...
    def trigger_expression(self, expression_file: str) -> str: ...


def build_service(
    config: DesktopConfig,
    config_path: Path,
    launcher: AppLauncher,
    confirm: Callable[[str, str], bool],
    avatar: ExpressionAvatar | None = None,
) -> ConversationService:
    tools: list[ToolDefinition] = []
    if config.search_enabled:
        tools.append(
            TypedTool(
                "web_search",
                "Buscar fuentes públicas actuales.",
                SearchArgs,
                lambda args: web_search(args.query),
            )
        )
    if launcher.apps:
        tools.append(
            TypedTool(
                "abrir_app",
                "Solicitar al usuario abrir una aplicación del catálogo.",
                OpenAppArgs,
                lambda args: launcher.launch(args.app_name),
                domain_check=lambda args: args.app_name in launcher.apps,
                authorize=lambda args: confirm("abrir_app", args.app_name),
                requires_confirmation=True,
                choices={"app_name": tuple(launcher.apps)},
                risk=Risk.REVERSIBLE,
            )
        )
    if avatar:
        expressions = tuple(e["file"] for e in avatar.list_expressions() if e["file"])
        if expressions:
            tools.append(
                TypedTool(
                    "set_expression",
                    "Cambiar la expresión del avatar.",
                    ExpressionArgs,
                    lambda args: avatar.trigger_expression(args.expression_file),
                    choices={"expression_file": expressions},
                    risk=Risk.READ,
                )
            )
    memory = SQLiteMemory(resolve_path(config_path, config.memory_path))
    client = LLMClient(config.llm, ToolRegistry(tuple(tools), confirm))
    return ConversationService(memory, client, config.llm.max_history_turns)
