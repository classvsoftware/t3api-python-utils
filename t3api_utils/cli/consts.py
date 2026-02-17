"""CLI constants and environment variable keys for t3api_utils configuration.

Defines default values and the :class:`EnvKeys` enum whose members map to
environment variables (and ``.t3.env`` file keys) that control authentication,
HTTP behaviour, performance tuning, and output settings.
"""

from enum import Enum
from typing import Final

DEFAULT_OTP_WHITELIST = {"mi.metrc.com"}
"""Metrc hostnames that require a one-time password for authentication."""

DEFAULT_CREDENTIAL_EMAIL_WHITELIST = {"co.metrc.com"}
"""Metrc hostnames that require an email address for authentication."""

DEFAULT_T3_API_HOST = "https://api.trackandtrace.tools"
"""Default base URL for the T3 API when no override is configured."""

DEFAULT_ENV_PATH: Final[str] = ".t3.env"
"""Default path to the dotenv file where credentials and settings are persisted."""


class EnvKeys(str, Enum):
    """Environment variable keys recognised by :class:`t3api_utils.cli.utils.ConfigManager`.

    Each member's value is the literal env-var / dotenv key string.
    Members are grouped by concern: authentication, connection, performance,
    hostname behaviour, development, and output.
    """

    # -- Authentication settings --

    METRC_HOSTNAME = "METRC_HOSTNAME"
    """Metrc state hostname (e.g. ``ca.metrc.com``)."""

    METRC_USERNAME = "METRC_USERNAME"
    """Metrc account username."""

    METRC_PASSWORD = "METRC_PASSWORD"
    """Metrc account password."""

    METRC_EMAIL = "METRC_EMAIL"
    """Email address for hostnames that require it (see :data:`DEFAULT_CREDENTIAL_EMAIL_WHITELIST`)."""

    JWT_TOKEN = "JWT_TOKEN"
    """Pre-issued JWT bearer token for direct authentication."""

    API_KEY = "API_KEY"
    """T3 API key for API-key-based authentication."""

    API_STATE_CODE = "API_STATE_CODE"
    """Two-letter US state code associated with the API key."""

    # -- API connection settings --

    T3_API_HOST = "T3_API_HOST"
    """Base URL of the T3 API (overrides :data:`DEFAULT_T3_API_HOST`)."""

    HTTP_TIMEOUT = "HTTP_TIMEOUT"
    """Overall HTTP request timeout in seconds."""

    HTTP_CONNECT_TIMEOUT = "HTTP_CONNECT_TIMEOUT"
    """TCP connection timeout in seconds."""

    HTTP_READ_TIMEOUT = "HTTP_READ_TIMEOUT"
    """HTTP response read timeout in seconds."""

    VERIFY_SSL = "VERIFY_SSL"
    """Whether to verify TLS certificates (``"true"`` / ``"false"``)."""

    # -- Performance settings --

    MAX_WORKERS = "MAX_WORKERS"
    """Maximum number of parallel workers for concurrent data fetching."""

    BATCH_SIZE = "BATCH_SIZE"
    """Number of pages to fetch per batch in async parallel loading."""

    RATE_LIMIT_RPS = "RATE_LIMIT_RPS"
    """Maximum requests per second for the rate limiter."""

    RATE_LIMIT_BURST = "RATE_LIMIT_BURST"
    """Maximum burst size allowed by the rate limiter."""

    RETRY_MAX_ATTEMPTS = "RETRY_MAX_ATTEMPTS"
    """Maximum number of retry attempts for failed HTTP requests."""

    RETRY_BACKOFF_FACTOR = "RETRY_BACKOFF_FACTOR"
    """Exponential backoff multiplier between retries."""

    RETRY_MIN_WAIT = "RETRY_MIN_WAIT"
    """Minimum wait time in seconds between retries."""

    # -- Hostname behaviour --

    OTP_WHITELIST = "OTP_WHITELIST"
    """Comma-separated list of hostnames requiring OTP authentication."""

    EMAIL_WHITELIST = "EMAIL_WHITELIST"
    """Comma-separated list of hostnames requiring an email address."""

    OTP_SEED = "OTP_SEED"
    """TOTP seed for automatic one-time password generation."""

    # -- Development settings --

    LOG_LEVEL = "LOG_LEVEL"
    """Logging level (e.g. ``DEBUG``, ``INFO``, ``WARNING``)."""

    LOG_FORMAT = "LOG_FORMAT"
    """Custom log format string."""

    DEBUG_MODE = "DEBUG_MODE"
    """Enable debug mode (``"true"`` / ``"false"``)."""

    CACHE_RESPONSES = "CACHE_RESPONSES"
    """Cache API responses locally (``"true"`` / ``"false"``)."""

    # -- HTTP debug logging --

    T3_LOG_HTTP = "T3_LOG_HTTP"
    """Enable verbose HTTP request/response logging (``"true"`` / ``"false"``)."""

    T3_LOG_HEADERS = "T3_LOG_HEADERS"
    """Log request headers when HTTP logging is enabled (``"true"`` / ``"false"``, default ``"true"``)."""

    T3_LOG_BODY = "T3_LOG_BODY"
    """Log request body/payload when HTTP logging is enabled (``"true"`` / ``"false"``, default ``"true"``)."""

    T3_LOG_FILE = "T3_LOG_FILE"
    """File path for HTTP debug logs. File is truncated on each run. Empty to disable file logging."""

    # -- Output settings --

    OUTPUT_DIR = "OUTPUT_DIR"
    """Directory for CSV/JSON output files."""

    TEMP_DIR = "TEMP_DIR"
    """Directory for temporary files."""

    AUTO_OPEN_FILES = "AUTO_OPEN_FILES"
    """Automatically open exported files after saving (``"true"`` / ``"false"``)."""

    STRIP_EMPTY_COLUMNS = "STRIP_EMPTY_COLUMNS"
    """Remove columns that are entirely empty from CSV output (``"true"`` / ``"false"``)."""

    DEFAULT_FILE_FORMAT = "DEFAULT_FILE_FORMAT"
    """Default export format (``"csv"`` or ``"json"``)."""

    def __str__(self) -> str:
        return self.value

    def __repr__(self) -> str:
        return repr(self.value)
