"""Authentication credential interfaces for the T3 API."""

from typing import Optional, TypedDict


class T3Credentials(TypedDict):
    """Credentials required to authenticate with the T3 API via Metrc.

    Used by :func:`t3api_utils.auth.utils.create_credentials_authenticated_client_or_error`
    and related helpers to build an authenticated API client.
    """

    hostname: str
    """Metrc state hostname (e.g. ``"ca.metrc.com"``, ``"co.metrc.com"``)."""

    username: str
    """Metrc account username."""

    password: str
    """Metrc account password."""

    otp: Optional[str]
    """One-time password for two-factor authentication. Required for hostnames
    in the OTP whitelist (e.g. ``mi.metrc.com``)."""

    email: Optional[str]
    """Email address associated with the Metrc account. Required for hostnames
    in the credential-email whitelist (e.g. ``co.metrc.com``)."""