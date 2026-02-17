"""Logging configuration for t3api_utils.

Sets up a Rich-based logging handler with colored output and rich tracebacks.
Logging is configured automatically on import with INFO level; call
:func:`setup_logging` to reconfigure with a different level.
"""

import logging
import sys

from rich.logging import RichHandler


def setup_logging(level: int = logging.INFO) -> None:
    """Configure the root logger with a Rich handler.

    Replaces any existing handlers on the root logger with a single
    :class:`rich.logging.RichHandler` that renders rich tracebacks and
    supports Rich markup in log messages.

    Args:
        level: Logging level threshold (default: ``logging.INFO``).
    """
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