"""Where t3api-utils keeps its files. Tests patch these two functions."""

from __future__ import annotations

from pathlib import Path

import platformdirs

APP_NAME = "t3api-utils"


def config_dir() -> Path:
    """The user config folder: profiles (config.toml) and the secrets fallback."""
    return Path(platformdirs.user_config_dir(APP_NAME, appauthor=False))


def cache_dir() -> Path:
    """The user cache folder: the cached OpenAPI spec and /v2/states."""
    return Path(platformdirs.user_cache_dir(APP_NAME, appauthor=False))
