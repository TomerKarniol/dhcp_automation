"""API key authentication dependency.

The expected key is read from the DHCP_API_KEY environment variable (set in .env).
Every route automatically requires the header X-API-Key when this dependency is
applied globally in main.py.
"""

import os

from fastapi import HTTPException, Security, status
from fastapi.security import APIKeyHeader

_header = APIKeyHeader(name="X-API-Key", auto_error=True)


def require_api_key(key: str = Security(_header)) -> str:
    expected = os.getenv("DHCP_API_KEY", "")
    if not expected:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Server misconfiguration: DHCP_API_KEY is not set",
        )
    if key != expected:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid API key",
        )
    return key
