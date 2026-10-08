"""
Shadow Traffic — API Key Authentication
Role in Architecture:
    Enforces authentication for metric ingestion endpoints via X-API-Key headers.
    Protects the system from unauthorized ingestion streams and identifies site callers.
"""

import logging
from typing import Optional
from fastapi import HTTPException, Header, Security, status
from fastapi.security import APIKeyHeader
from ..config import settings

logger = logging.getLogger("backend.security.auth")

API_KEY_HEADER = APIKeyHeader(name="X-API-Key", auto_error=False)


async def extract_api_key(api_key: Optional[str] = Security(API_KEY_HEADER)) -> Optional[str]:
    """Extracts raw API key from header without strict validation."""
    return api_key


async def verify_api_key(api_key: Optional[str] = Security(API_KEY_HEADER)) -> str:
    """
    FastAPI dependency: verifies the X-API-Key header.
    Returns the valid API key or raises HTTP 401 Unauthorized.
    """
    if not settings.ENABLE_API_KEY_AUTH:
        return "auth-disabled"

    if not api_key:
        logger.warning("Rejected ingestion request: Missing X-API-Key header.")
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Missing required authentication header: X-API-Key",
            headers={"WWW-Authenticate": "ApiKey"},
        )

    if api_key not in settings.ALLOWED_API_KEYS and api_key != settings.DEFAULT_API_KEY:
        logger.warning(f"Rejected ingestion request: Invalid API key '{api_key[:4]}***'.")
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid or unauthorized API key",
            headers={"WWW-Authenticate": "ApiKey"},
        )

    return api_key
