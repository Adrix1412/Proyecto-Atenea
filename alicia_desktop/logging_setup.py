"""Metadata-only logs with bounded rotation; dependency debug logs stay disabled."""

import logging
from logging.handlers import RotatingFileHandler
from pathlib import Path


def setup_logging(path: Path, level: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    handler = RotatingFileHandler(path, maxBytes=1_000_000, backupCount=3, encoding="utf-8")
    path.chmod(0o600)
    logging.basicConfig(
        level=getattr(logging, level),
        handlers=[handler, logging.StreamHandler()],
        format="%(asctime)s %(levelname)s %(name)s %(message)s",
        force=True,
    )
    for name in ("httpx", "httpcore", "websockets", "faster_whisper", "ddgs"):
        logging.getLogger(name).setLevel(logging.WARNING)
