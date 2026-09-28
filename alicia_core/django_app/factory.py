"""Web composition root intentionally exposes search only; no desktop capabilities."""

from pathlib import Path

from django.conf import settings

from alicia_core.adapters.search import web_search
from alicia_core.config import load_core_config
from alicia_core.llm import LLMClient
from alicia_core.tool_args import SearchArgs
from alicia_core.tools import ToolRegistry, TypedTool


def build_web_client() -> LLMClient:
    cfg = load_core_config(Path(settings.ALICIA_CONFIG_PATH))
    tools = (
        (
            TypedTool(
                "web_search",
                "Buscar fuentes públicas actuales.",
                SearchArgs,
                lambda args: web_search(args.query),
            ),
        )
        if cfg.search_enabled
        else ()
    )
    return LLMClient(cfg.llm, ToolRegistry(tools))
