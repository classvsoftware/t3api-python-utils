from functools import wraps
from typing import Callable, Optional

import typer

OTP_WHITELIST = {"mi.metrc.com"}


def cli_options(func: Callable):
    @wraps(func)
    def wrapper(
        host: str = typer.Option("https://api.trackandtrace.tools", "--host"),
        hostname: str = typer.Option(..., "--hostname"),
        username: str = typer.Option(..., "--username"),
    ):
        password = typer.prompt("Enter password", hide_input=True)
        otp = (
            typer.prompt("Enter T3 6-digit OTP") if hostname in OTP_WHITELIST else None
        )
        return func(host, hostname, username, password, otp)

    return wrapper  # ← Typer will parse this wrapper’s signature, not the original
