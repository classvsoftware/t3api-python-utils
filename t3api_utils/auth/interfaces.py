from typing import Optional, TypedDict


class T3Credentials(TypedDict):
    hostname: str
    username: str
    password: str
    otp: Optional[str]