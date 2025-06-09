from typing import TypedDict, Optional


class T3StoredCredentials(TypedDict):
    hostname: str
    username: str
    password: str
    
    
class T3Credentials(T3StoredCredentials):
    hostname: str
    username: str
    password: str
    otp: Optional[str]