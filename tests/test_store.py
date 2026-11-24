from __future__ import annotations

import logging
import os
import stat
import sys
import tomllib
from collections.abc import Iterator
from pathlib import Path
from types import SimpleNamespace

import keyring
import pytest
from keyring.backends import fail

from t3api_utils import _paths
from t3api_utils._http import DEFAULT_HOST
from t3api_utils.auth import store as store_module
from t3api_utils.auth.store import KEYRING_SERVICE, Config, Profile, Store
from tests.conftest import MemoryKeyring


@pytest.fixture
def store() -> Store:
    return Store()


@pytest.fixture
def no_keyring(memory_keyring: MemoryKeyring) -> Iterator[None]:
    """Swap in the keyring backend that fails every operation (headless Linux, containers)."""
    keyring.set_keyring(fail.Keyring())  # type: ignore[no-untyped-call]
    yield
    keyring.set_keyring(memory_keyring)


def _read_toml(path: Path) -> dict[str, object]:
    return tomllib.loads(path.read_text(encoding="utf-8"))


# --------------------------------------------------------------------------- Profile


def test_profile_to_toml_drops_name_and_none() -> None:
    profile = Profile(name="mo", metrc_hostname="mo.metrc.com", username="jdoe")
    assert profile.to_toml() == {
        "api_host": DEFAULT_HOST,
        "metrc_hostname": "mo.metrc.com",
        "username": "jdoe",
    }


def test_profile_from_toml_defaults_and_bad_credential() -> None:
    profile = Profile.from_toml("x", {"api_host": "", "credential": "password", "extra": 1})
    assert profile == Profile(name="x", api_host=DEFAULT_HOST, credential=None)
    assert Profile.from_toml("y", {"credential": "jwt"}).credential == "jwt"
    assert Profile.from_toml("z", {"credential": "secret_key"}).credential == "secret_key"


# --------------------------------------------------------------------------- paths


def test_store_uses_config_dir_by_default(store: Store) -> None:
    assert store.config_dir == _paths.config_dir()
    assert store.config_path == _paths.config_dir() / "config.toml"
    assert store.secrets_path == _paths.config_dir() / "secrets.toml"


def test_store_accepts_custom_dir(tmp_path: Path) -> None:
    custom = Store(tmp_path / "elsewhere")
    custom.save_profile(Profile(name="a"))
    assert (tmp_path / "elsewhere" / "config.toml").is_file()
    assert not _paths.config_dir().exists()


# --------------------------------------------------------------------------- profiles


def test_load_without_file(store: Store) -> None:
    assert store.load() == Config()
    assert store.profiles() == []
    assert store.get_profile("nope") is None
    assert store.default_profile_name() is None


def test_profiles_round_trip(store: Store) -> None:
    mo = Profile(
        name="mo",
        api_host="https://t3.example",
        metrc_hostname="mo.metrc.com",
        username="jdoe",
        license="LIC-00001",
        credential="secret_key",
    )
    mi = Profile(name="mi", metrc_hostname="mi.metrc.com", credential="jwt")
    store.save_profile(mo)
    store.save_profile(mi)

    assert store.get_profile("mo") == mo
    assert store.get_profile("mi") == mi
    assert sorted(p.name for p in store.profiles()) == ["mi", "mo"]
    raw = _read_toml(store.config_path)
    assert raw["default_profile"] == "mo"
    assert raw["profiles"] == {
        "mi": {"api_host": DEFAULT_HOST, "metrc_hostname": "mi.metrc.com", "credential": "jwt"},
        "mo": {
            "api_host": "https://t3.example",
            "metrc_hostname": "mo.metrc.com",
            "username": "jdoe",
            "license": "LIC-00001",
            "credential": "secret_key",
        },
    }


def test_first_saved_profile_becomes_default(store: Store) -> None:
    store.save_profile(Profile(name="first"))
    store.save_profile(Profile(name="second"))
    assert store.default_profile_name() == "first"
    store.save_profile(Profile(name="third"), make_default=True)
    assert store.default_profile_name() == "third"
    store.save_profile(Profile(name="fourth"), make_default=False)
    assert store.default_profile_name() == "third"


def test_make_default_false_with_no_default(store: Store) -> None:
    store.save_profile(Profile(name="only"), make_default=False)
    assert store.default_profile_name() is None
    assert "default_profile" not in _read_toml(store.config_path)


def test_set_default(store: Store) -> None:
    store.save_profile(Profile(name="a"))
    store.save_profile(Profile(name="b"))
    store.set_default("b")
    assert store.default_profile_name() == "b"


def test_set_default_unknown_raises(store: Store) -> None:
    store.save_profile(Profile(name="a"))
    with pytest.raises(KeyError, match="No profile named 'ghost'"):
        store.set_default("ghost")
    assert store.default_profile_name() == "a"


def test_load_skips_bad_entries(store: Store) -> None:
    store.config_dir.mkdir(parents=True)
    store.config_path.write_text(
        'default_profile = 5\nprofiles = { good = { username = "u" }, bad = "x" }\n', encoding="utf-8"
    )
    config = store.load()
    assert config.default_profile is None
    assert list(config.profiles) == ["good"]
    assert config.profiles["good"].username == "u"


def test_load_without_profiles_table(store: Store) -> None:
    store.config_dir.mkdir(parents=True)
    store.config_path.write_text('default_profile = "a"\n', encoding="utf-8")
    assert store.load() == Config(default_profile="a")


def test_corrupt_config_is_survived(store: Store, caplog: pytest.LogCaptureFixture) -> None:
    store.config_dir.mkdir(parents=True)
    store.config_path.write_text("this is [not toml", encoding="utf-8")
    with caplog.at_level(logging.WARNING, logger="t3api_utils"):
        assert store.load() == Config()
    assert "Couldn't read" in caplog.text
    # The broken file is kept aside, so nothing in it is lost when a profile is saved.
    backups = list(store.config_dir.glob("config.toml.broken-*"))
    assert [b.read_text(encoding="utf-8") for b in backups] == ["this is [not toml"]
    store.save_profile(Profile(name="a"))
    assert store.default_profile_name() == "a"


def test_unreadable_config_is_survived(store: Store, caplog: pytest.LogCaptureFixture) -> None:
    store.config_path.mkdir(parents=True)  # a folder where the file should be
    with caplog.at_level(logging.WARNING, logger="t3api_utils"):
        assert store.load() == Config()
    assert "Couldn't read" in caplog.text


# --------------------------------------------------------------------------- remove_profile


def test_remove_profile_reassigns_default_and_deletes_secrets(
    store: Store, memory_keyring: MemoryKeyring
) -> None:
    for name in ("b", "c", "a"):
        store.save_profile(Profile(name=name))
    store.set_default("b")
    store.set_secret("b", "secret_key", "sk-b")
    store.set_secret("b", "jwt", "jwt-b")
    store.set_secret("c", "secret_key", "sk-c")

    assert store.remove_profile("b") is True

    assert store.get_profile("b") is None
    assert store.default_profile_name() == "a"  # first remaining, sorted
    assert (KEYRING_SERVICE, "b:secret_key") not in memory_keyring.passwords
    assert (KEYRING_SERVICE, "b:jwt") not in memory_keyring.passwords
    assert memory_keyring.passwords[(KEYRING_SERVICE, "c:secret_key")] == "sk-c"


def test_remove_non_default_profile_keeps_default(store: Store) -> None:
    store.save_profile(Profile(name="a"))
    store.save_profile(Profile(name="b"))
    assert store.remove_profile("b") is True
    assert store.default_profile_name() == "a"


def test_remove_last_profile_clears_default(store: Store) -> None:
    store.save_profile(Profile(name="a"))
    assert store.remove_profile("a") is True
    assert store.load() == Config()
    assert "default_profile" not in _read_toml(store.config_path)


def test_remove_unknown_profile(store: Store, memory_keyring: MemoryKeyring) -> None:
    # A stray secret with no profile is still cleaned up, but nothing is written.
    memory_keyring.passwords[(KEYRING_SERVICE, "ghost:jwt")] = "old"
    assert store.remove_profile("ghost") is False
    assert not store.config_path.exists()
    assert memory_keyring.passwords == {}


def test_remove_profile_deletes_file_secrets(store: Store, no_keyring: None) -> None:
    store.save_profile(Profile(name="a"))
    store.set_secret("a", "secret_key", "sk-a")
    store.set_secret("b", "jwt", "jwt-b")
    store.remove_profile("a")
    assert _read_toml(store.secrets_path) == {"b": {"jwt": "jwt-b"}}


# --------------------------------------------------------------------------- secrets in the keyring


def test_secret_round_trip_in_keyring(store: Store, memory_keyring: MemoryKeyring) -> None:
    assert store.set_secret("mo", "secret_key", "sk-123") == "keyring"
    assert memory_keyring.passwords == {(KEYRING_SERVICE, "mo:secret_key"): "sk-123"}
    assert store.get_secret("mo", "secret_key") == "sk-123"
    assert store.get_secret("mo", "jwt") is None
    assert not store.secrets_path.exists()

    store.delete_secret("mo", "secret_key")
    assert memory_keyring.passwords == {}
    assert store.get_secret("mo", "secret_key") is None


def test_delete_missing_secret_is_quiet(store: Store) -> None:
    store.delete_secret("nobody", "jwt")  # PasswordDeleteError is swallowed


def test_set_secret_in_keyring_removes_older_file_copy(
    store: Store, memory_keyring: MemoryKeyring
) -> None:
    keyring.set_keyring(fail.Keyring())  # type: ignore[no-untyped-call]
    store.set_secret("mo", "secret_key", "old-in-file")
    store.set_secret("mo", "jwt", "jwt-in-file")
    store.set_secret("other", "jwt", "other-jwt")
    keyring.set_keyring(memory_keyring)

    assert store.set_secret("mo", "secret_key", "new-in-keyring") == "keyring"

    assert store.get_secret("mo", "secret_key") == "new-in-keyring"
    assert _read_toml(store.secrets_path) == {"mo": {"jwt": "jwt-in-file"}, "other": {"jwt": "other-jwt"}}


def test_last_file_secret_removed_deletes_file(store: Store, memory_keyring: MemoryKeyring) -> None:
    keyring.set_keyring(fail.Keyring())  # type: ignore[no-untyped-call]
    store.set_secret("mo", "jwt", "jwt-in-file")
    keyring.set_keyring(memory_keyring)
    assert store.secrets_path.exists()

    store.set_secret("mo", "jwt", "jwt-in-keyring")

    assert not store.secrets_path.exists()


def test_reading_falls_back_to_file_when_keyring_has_nothing(store: Store, memory_keyring: MemoryKeyring) -> None:
    # e.g. saved to the file during a keyring outage, read back once the keyring works
    store.config_dir.mkdir(parents=True)
    store.secrets_path.write_text('[mo]\nsecret_key = "sk-file"\njwt = "jwt-file"\n', encoding="utf-8")
    memory_keyring.passwords[(KEYRING_SERVICE, "mo:secret_key")] = ""
    assert store.get_secret("mo", "secret_key") == "sk-file"  # empty keyring value
    assert store.get_secret("mo", "jwt") == "jwt-file"  # no keyring entry
    memory_keyring.passwords[(KEYRING_SERVICE, "mo:jwt")] = "jwt-keyring"
    assert store.get_secret("mo", "jwt") == "jwt-keyring"  # the keyring wins when it has one


# --------------------------------------------------------------------------- secrets without a keyring


def test_secret_goes_to_file_when_keyring_fails(
    store: Store, no_keyring: None, caplog: pytest.LogCaptureFixture
) -> None:
    with caplog.at_level(logging.WARNING, logger="t3api_utils"):
        assert store.set_secret("mo", "secret_key", "sk-file") == "file"
    assert "keyring isn't available" in caplog.text
    assert str(store.secrets_path) in caplog.text
    assert "sk-file" not in caplog.text

    assert _read_toml(store.secrets_path) == {"mo": {"secret_key": "sk-file"}}
    assert store.get_secret("mo", "secret_key") == "sk-file"
    assert store.get_secret("mo", "jwt") is None
    assert store.get_secret("other", "jwt") is None

    store.set_secret("mo", "jwt", "jwt-file")
    store.set_secret("ia", "jwt", 'with "quotes"')
    assert store.get_secret("mo", "jwt") == "jwt-file"
    assert store.get_secret("mo", "secret_key") == "sk-file"
    assert store.get_secret("ia", "jwt") == 'with "quotes"'

    store.delete_secret("mo", "secret_key")
    store.delete_secret("mo", "secret_key")  # already gone: no write, no error
    assert _read_toml(store.secrets_path) == {"mo": {"jwt": "jwt-file"}, "ia": {"jwt": 'with "quotes"'}}


@pytest.mark.skipif(sys.platform == "win32", reason="POSIX file modes")
def test_secrets_file_is_user_only(store: Store, no_keyring: None) -> None:
    store.config_dir.mkdir(parents=True)
    store.secrets_path.write_text("", encoding="utf-8")
    store.secrets_path.chmod(0o644)  # a wider mode left from before is narrowed
    store.set_secret("mo", "secret_key", "sk-file")
    assert stat.S_IMODE(store.secrets_path.stat().st_mode) == 0o600


@pytest.mark.parametrize("platform", ["win32", "linux"])
def test_secrets_file_chmod_only_off_windows(
    store: Store, no_keyring: None, monkeypatch: pytest.MonkeyPatch, platform: str
) -> None:
    chmods: list[tuple[object, int]] = []
    monkeypatch.setattr(store_module, "sys", SimpleNamespace(platform=platform))
    monkeypatch.setattr(os, "chmod", lambda path, mode: chmods.append((path, mode)))
    store.set_secret("mo", "jwt", "jwt-file")
    assert store.get_secret("mo", "jwt") == "jwt-file"
    assert chmods == ([] if platform == "win32" else [(store.secrets_path, 0o600)])


def test_corrupt_secrets_file_is_survived(
    store: Store, no_keyring: None, caplog: pytest.LogCaptureFixture
) -> None:
    store.config_dir.mkdir(parents=True)
    store.secrets_path.write_text("not = [valid", encoding="utf-8")
    with caplog.at_level(logging.WARNING, logger="t3api_utils"):
        assert store.get_secret("mo", "jwt") is None
    assert "Couldn't read" in caplog.text
    # Writing replaces the corrupt file.
    store.set_secret("mo", "jwt", "jwt-file")
    assert store.get_secret("mo", "jwt") == "jwt-file"


def test_unreadable_secrets_file_is_survived(store: Store, caplog: pytest.LogCaptureFixture) -> None:
    store.secrets_path.mkdir(parents=True)  # a folder where the file should be
    with caplog.at_level(logging.WARNING, logger="t3api_utils"):
        assert store.get_secret("mo", "jwt") is None
    assert "Couldn't read" in caplog.text


def test_secrets_file_skips_bad_entries_and_stringifies(store: Store, no_keyring: None) -> None:
    store.config_dir.mkdir(parents=True)
    store.secrets_path.write_text('stray = "value"\n[mo]\njwt = 12345\n', encoding="utf-8")
    assert store.get_secret("mo", "jwt") == "12345"
    assert store.get_secret("stray", "jwt") is None
