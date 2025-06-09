from enum import Enum
from typing import Final

OTP_WHITELIST = {"mi.metrc.com"}

# Path to the saved environment file
DEFAULT_ENV_PATH: Final[str] = ".t3.env"


class EnvKeys(str, Enum):
    METRC_HOSTNAME = "METRC_HOSTNAME"
    METRC_USERNAME = "METRC_USERNAME"
    METRC_PASSWORD = "METRC_PASSWORD"

    def __str__(self) -> str:
        return self.value

    def __repr__(self) -> str:
        return repr(self.value)


# Environment variable keys required for authentication
REQUIRED_ENV_KEYS: Final[list[EnvKeys]] = [
    EnvKeys.METRC_HOSTNAME,
    EnvKeys.METRC_USERNAME,
    EnvKeys.METRC_PASSWORD,
]
