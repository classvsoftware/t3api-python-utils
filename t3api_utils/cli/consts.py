from enum import Enum
from typing import Final

# Default values for backward compatibility (will be overridden by config)
DEFAULT_OTP_WHITELIST = {"mi.metrc.com"}
DEFAULT_CREDENTIAL_EMAIL_WHITELIST = {"co.metrc.com"}
DEFAULT_T3_API_HOST = "https://api.trackandtrace.tools"

# Path to the saved environment file
DEFAULT_ENV_PATH: Final[str] = ".t3.env"


class EnvKeys(str, Enum):
    # Authentication settings
    METRC_HOSTNAME = "METRC_HOSTNAME"
    METRC_USERNAME = "METRC_USERNAME"
    METRC_PASSWORD = "METRC_PASSWORD"
    METRC_EMAIL = "METRC_EMAIL"
    JWT_TOKEN = "JWT_TOKEN"
    API_KEY = "API_KEY"
    API_STATE_CODE = "API_STATE_CODE"

    # API connection settings
    T3_API_HOST = "T3_API_HOST"
    HTTP_TIMEOUT = "HTTP_TIMEOUT"
    HTTP_CONNECT_TIMEOUT = "HTTP_CONNECT_TIMEOUT"
    HTTP_READ_TIMEOUT = "HTTP_READ_TIMEOUT"
    VERIFY_SSL = "VERIFY_SSL"

    # Performance settings
    MAX_WORKERS = "MAX_WORKERS"
    BATCH_SIZE = "BATCH_SIZE"
    RATE_LIMIT_RPS = "RATE_LIMIT_RPS"
    RATE_LIMIT_BURST = "RATE_LIMIT_BURST"
    RETRY_MAX_ATTEMPTS = "RETRY_MAX_ATTEMPTS"
    RETRY_BACKOFF_FACTOR = "RETRY_BACKOFF_FACTOR"
    RETRY_MIN_WAIT = "RETRY_MIN_WAIT"

    # Hostname behavior
    OTP_WHITELIST = "OTP_WHITELIST"
    EMAIL_WHITELIST = "EMAIL_WHITELIST"
    OTP_SEED = "OTP_SEED"

    # Development settings
    LOG_LEVEL = "LOG_LEVEL"
    LOG_FORMAT = "LOG_FORMAT"
    DEBUG_MODE = "DEBUG_MODE"
    CACHE_RESPONSES = "CACHE_RESPONSES"

    # Output settings
    OUTPUT_DIR = "OUTPUT_DIR"
    TEMP_DIR = "TEMP_DIR"
    AUTO_OPEN_FILES = "AUTO_OPEN_FILES"
    STRIP_EMPTY_COLUMNS = "STRIP_EMPTY_COLUMNS"
    DEFAULT_FILE_FORMAT = "DEFAULT_FILE_FORMAT"

    def __str__(self) -> str:
        return self.value

    def __repr__(self) -> str:
        return repr(self.value)
