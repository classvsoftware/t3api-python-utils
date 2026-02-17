"""Logging configuration for t3api_utils.

Sets up a Rich-based logging handler with colored output and rich tracebacks.
Logging is configured automatically on import; the level is read from the
``LOG_LEVEL`` environment variable (default: ``INFO``). Call
:func:`setup_logging` to reconfigure with a different level.
"""

import logging
import os
import sys

from rich.logging import RichHandler

_LOG_LEVEL_NAMES = {
    "DEBUG": logging.DEBUG,
    "INFO": logging.INFO,
    "WARNING": logging.WARNING,
    "WARN": logging.WARNING,
    "ERROR": logging.ERROR,
    "CRITICAL": logging.CRITICAL,
}


def _resolve_log_level() -> int:
    """Read ``LOG_LEVEL`` from the environment and map to a logging constant.

    Returns:
        The corresponding ``logging`` level, defaulting to ``logging.INFO``
        if the variable is unset or unrecognised.
    """
    env_val = os.getenv("LOG_LEVEL", "").strip().upper()
    return _LOG_LEVEL_NAMES.get(env_val, logging.INFO)


def setup_logging(level: int = -1) -> None:
    """Configure the root logger with a Rich handler.

    Replaces any existing handlers on the root logger with a single
    :class:`rich.logging.RichHandler` that renders rich tracebacks and
    supports Rich markup in log messages.

    Args:
        level: Logging level threshold. When ``-1`` (the default sentinel),
            the level is resolved from the ``LOG_LEVEL`` environment variable
            (falling back to ``logging.INFO``).
    """
    if level == -1:
        level = _resolve_log_level()
    logging.basicConfig(
        level=level,
        format="%(message)s",
        datefmt="[%X]",
        handlers=[RichHandler(rich_tracebacks=True, markup=True)]
    )

def get_logger(name: str) -> logging.Logger:
    """Return a named logger.

    Args:
        name: Logger name, typically ``__name__`` of the calling module.

    Returns:
        A :class:`logging.Logger` instance for the given name.
    """
    return logging.getLogger(name)

# Optionally call setup_logging() here or in main.py
setup_logging()