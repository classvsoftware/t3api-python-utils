from typing import Final


OTP_WHITELIST = {"mi.metrc.com"}

# Path to the saved environment file
ENV_PATH: Final[str] = ".t3.env"

# Environment variable keys required for authentication
REQUIRED_ENV_KEYS: Final[list[str]] = [
    "T3_HOSTNAME",
    "T3_USERNAME",
    "T3_PASSWORD",
]

# Optional OTP field, conditionally required
OTP_ENV_KEY: Final[str] = "T3_OTP"
