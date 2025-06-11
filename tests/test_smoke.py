import pytest


def test_import_t3api_utils():
    import t3api_utils  # Ensure the top-level package is importable


def test_import_main_module():
    from t3api_utils.main import utils


def test_import_cli_module():
    from t3api_utils.cli import utils


def test_import_auth_module():
    from t3api_utils.auth import utils


def test_import_file_module():
    from t3api_utils.file import utils


def test_import_collection_module():
    from t3api_utils.collection import utils


class DummyPrompt:
    def __init__(self, value: str):
        self.value = value

    def ask(self):
        return self.value
