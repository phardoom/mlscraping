from __future__ import annotations

from loguru import logger


def setup_logging() -> None:
    """Configura o Loguru com formato amigável."""

    logger.remove()
    logger.add(
        sink=lambda msg: print(msg, end=""),
        colorize=True,
        format="<green>{time:YYYY-MM-DD HH:mm:ss}</green> | <level>{level: <8}</level> | "
        "<cyan>{name}</cyan>:<cyan>{function}</cyan>:<cyan>{line}</cyan> - <level>{message}</level>",
    )

