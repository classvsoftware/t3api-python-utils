from enum import Enum
from typing import Final

OTP_WHITELIST = {"mi.metrc.com"}
CREDENTIAL_EMAIL_WHITELIST = {"co.metrc.com"}

# Path to the saved environment file
DEFAULT_ENV_PATH: Final[str] = ".t3.env"


class EnvKeys(str, Enum):
    METRC_HOSTNAME = "METRC_HOSTNAME"
    METRC_USERNAME = "METRC_USERNAME"
    METRC_PASSWORD = "METRC_PASSWORD"
    METRC_EMAIL = "METRC_EMAIL"

    def __str__(self) -> str:
        return self.value

    def __repr__(self) -> str:
        return repr(self.value)
