import pytest


def test_import_t3api_utils():
    import t3api_utils  # Ensure the top-level package is importable


def test_import_cli_module():
    from t3api_utils import cli


def test_import_decoratorss_module():
    from t3api_utils import decorators


class DummyPrompt:
    def __init__(self, value: str):
        self.value = value

    def ask(self):
        return self.value
