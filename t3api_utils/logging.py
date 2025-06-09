import logging
import sys

from rich.logging import RichHandler


def setup_logging(level=logging.INFO):
    logging.basicConfig(
        level=level,
        format="%(message)s",
        datefmt="[%X]",
        handlers=[RichHandler(rich_tracebacks=True, markup=True)]
    )

def get_logger(name: str) -> logging.Logger:
    return logging.getLogger(name)

# Optionally call setup_logging() here or in main.py
setup_logging()