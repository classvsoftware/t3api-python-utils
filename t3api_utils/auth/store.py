"""Profiles in config.toml, secrets in the OS keyring (or a user-only file)."""

from __future__ import annotations

import logging
import os
import sys
import time
import tomllib
from dataclasses import asdict, dataclass, field
from pathlib import Path
from typing import Any, Literal

import tomli_w

from t3api_utils import _paths
from t3api_utils._http import DEFAULT_HOST
from t3api_utils.auth.credentials import CredentialKind

logger = logging.getLogger("t3api_utils")

KEYRING_SERVICE = "t3api-utils"
SecretLocation = Literal["keyring", "file"]


@dataclass
class Profile:
    """A saved login. Secrets aren't stored here; see :class:`Store`."""

    name: str
    api_host: str = DEFAULT_HOST
    metrc_hostname: str | None = None
    username: str | None = None
    license: str | None = None
    credential: CredentialKind | None = None

    def to_toml(self) -> dict[str, Any]:
        data = asdict(self)
        data.pop("name")
        return {k: v for k, v in data.items() if v is not None}

    @classmethod
    def from_toml(cls, name: str, data: dict[str, Any]) -> Profile:
        credential = data.get("credential")
        return cls(
            name=name,
            api_host=str(data.get("api_host") or DEFAULT_HOST),
            metrc_hostname=data.get("metrc_hostname"),
            username=data.get("username"),
            license=data.get("license"),
            credential=credential if credential in ("secret_key", "jwt") else None,
        )


@dataclass
class Config:
    default_profile: str | None = None
    profiles: dict[str, Profile] = field(default_factory=dict)


class Store:
    """Reads and writes profiles and their secrets.

    Secrets go to the OS keyring under service ``t3api-utils`` with entry
    ``<profile>:<kind>``. If no keyring is available, or a write fails, they go
    to ``secrets.toml`` next to the config, readable only by the user.
    """

    def __init__(self, config_dir: Path | None = None) -> None:
        self.config_dir = config_dir or _paths.config_dir()

    @property
    def config_path(self) -> Path:
        return self.config_dir / "config.toml"

    @property
    def secrets_path(self) -> Path:
        return self.config_dir / "secrets.toml"

    # ------------------------------------------------------------------ profiles

    def load(self) -> Config:
        try:
            raw = tomllib.loads(self.config_path.read_text(encoding="utf-8"))
        except FileNotFoundError:
            return Config()
        except OSError as exc:
            logger.warning("Couldn't read %s: %s", self.config_path, exc)
            return Config()
        except tomllib.TOMLDecodeError as exc:
            # Keep the broken file, so saving a profile can't silently wipe the others.
            backup = self.config_path.with_name(f"config.toml.broken-{int(time.time())}")
            self.config_path.replace(backup)
            logger.warning(
                "Couldn't read %s (%s). Moved it to %s; profiles start empty.",
                self.config_path,
                exc,
                backup.name,
            )
            return Config()
        profiles = {
            name: Profile.from_toml(name, data)
            for name, data in (raw.get("profiles") or {}).items()
            if isinstance(data, dict)
        }
        default = raw.get("default_profile")
        return Config(default_profile=default if isinstance(default, str) else None, profiles=profiles)

    def save(self, config: Config) -> None:
        data: dict[str, Any] = {}
        if config.default_profile:
            data["default_profile"] = config.default_profile
        data["profiles"] = {name: p.to_toml() for name, p in sorted(config.profiles.items())}
        self.config_dir.mkdir(parents=True, exist_ok=True)
        self.config_path.write_text(tomli_w.dumps(data), encoding="utf-8")

    def profiles(self) -> list[Profile]:
        return list(self.load().profiles.values())

    def get_profile(self, name: str) -> Profile | None:
        return self.load().profiles.get(name)

    def default_profile_name(self) -> str | None:
        return self.load().default_profile

    def save_profile(self, profile: Profile, *, make_default: bool | None = None) -> None:
        """Save a profile. It becomes the default if asked, or if there is no default yet."""
        config = self.load()
        config.profiles[profile.name] = profile
        if make_default or (make_default is None and not config.default_profile):
            config.default_profile = profile.name
        self.save(config)

    def set_default(self, name: str) -> None:
        config = self.load()
        if name not in config.profiles:
            raise KeyError(f"No profile named {name!r}.")
        config.default_profile = name
        self.save(config)

    def remove_profile(self, name: str) -> bool:
        """Delete a profile and its secrets. Returns False if it didn't exist."""
        config = self.load()
        existed = config.profiles.pop(name, None) is not None
        if config.default_profile == name:
            config.default_profile = next(iter(sorted(config.profiles)), None)
        if existed:
            self.save(config)
        for kind in ("secret_key", "jwt"):
            self.delete_secret(name, kind)
        return existed

    # ------------------------------------------------------------------ secrets

    @staticmethod
    def _entry(profile: str, kind: CredentialKind) -> str:
        return f"{profile}:{kind}"

    def get_secret(self, profile: str, kind: CredentialKind) -> str | None:
        try:
            import keyring

            value = keyring.get_password(KEYRING_SERVICE, self._entry(profile, kind))
        except Exception as exc:  # noqa: BLE001 - keyring backends raise anything
            logger.debug("Keyring read failed: %s", exc)
            value = None
        if value:
            return value
        return self._read_secrets_file().get(profile, {}).get(kind)

    def set_secret(self, profile: str, kind: CredentialKind, value: str) -> SecretLocation:
        """Store a secret; returns where it went."""
        try:
            import keyring

            keyring.set_password(KEYRING_SERVICE, self._entry(profile, kind), value)
        except Exception as exc:  # noqa: BLE001 - keyring backends raise anything
            logger.warning(
                "The OS keyring isn't available (%s). Saving the secret to %s, readable "
                "only by you. In CI, set T3_SECRET_KEY instead.",
                exc,
                self.secrets_path,
            )
            secrets = self._read_secrets_file()
            secrets.setdefault(profile, {})[kind] = value
            self._write_secrets_file(secrets)
            return "file"
        # Don't leave an older copy behind in the file.
        self._delete_from_file(profile, kind)
        return "keyring"

    def delete_secret(self, profile: str, kind: CredentialKind) -> None:
        try:
            import keyring

            keyring.delete_password(KEYRING_SERVICE, self._entry(profile, kind))
        except Exception as exc:  # noqa: BLE001 - includes PasswordDeleteError when absent
            logger.debug("Keyring delete skipped: %s", exc)
        self._delete_from_file(profile, kind)

    def _delete_from_file(self, profile: str, kind: str) -> None:
        secrets = self._read_secrets_file()
        if kind in secrets.get(profile, {}):
            del secrets[profile][kind]
            if not secrets[profile]:
                del secrets[profile]
            self._write_secrets_file(secrets)

    def _read_secrets_file(self) -> dict[str, dict[str, str]]:
        try:
            raw = tomllib.loads(self.secrets_path.read_text(encoding="utf-8"))
        except FileNotFoundError:
            return {}
        except (OSError, tomllib.TOMLDecodeError) as exc:
            logger.warning("Couldn't read %s: %s", self.secrets_path, exc)
            return {}
        return {
            name: {k: str(v) for k, v in values.items()}
            for name, values in raw.items()
            if isinstance(values, dict)
        }

    def _write_secrets_file(self, secrets: dict[str, dict[str, str]]) -> None:
        self.config_dir.mkdir(parents=True, exist_ok=True)
        if not secrets:
            self.secrets_path.unlink(missing_ok=True)
            return
        data = tomli_w.dumps(secrets).encode()
        flags = os.O_WRONLY | os.O_CREAT | os.O_TRUNC | getattr(os, "O_BINARY", 0)
        fd = os.open(self.secrets_path, flags, 0o600)
        with os.fdopen(fd, "wb") as handle:
            handle.write(data)
        if sys.platform != "win32":
            os.chmod(self.secrets_path, 0o600)
