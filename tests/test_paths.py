"""_paths.py: the user config and cache folders.

conftest patches both functions for every test, so the real ones are captured
here at import time, before any fixture runs.
"""

from __future__ import annotations

from pathlib import Path

import platformdirs

from t3api_utils import _paths
from t3api_utils._paths import cache_dir as real_cache_dir
from t3api_utils._paths import config_dir as real_config_dir


def test_config_dir_is_platform_user_config_folder() -> None:
    path = real_config_dir()
    assert path == Path(platformdirs.user_config_dir("t3api-utils", appauthor=False))
    assert "t3api-utils" in path.parts


def test_cache_dir_is_platform_user_cache_folder() -> None:
    path = real_cache_dir()
    assert path == Path(platformdirs.user_cache_dir("t3api-utils", appauthor=False))
    assert "t3api-utils" in path.parts


def test_tests_never_touch_the_real_folders(isolated: Path) -> None:
    assert _paths.config_dir() == isolated / "config"
    assert _paths.cache_dir() == isolated / "cache"
