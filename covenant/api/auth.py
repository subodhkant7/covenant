"""Authentication and authorization dependencies for Covenant API."""

import hmac
from typing import Optional

from fastapi import Header, HTTPException, status

from covenant.config import settings


async def verify_simulation_token(
    x_simulation_token: Optional[str] = Header(None, alias="X-Simulation-Token"),
) -> None:
    """
    Dedicated authorization guard for simulation endpoints.
    Requires constant-time comparison against the server-side COVENANT_SIMULATION_TOKEN.

    Security model:
    1. In production (COVENANT_ENV in production/prod/live), fails closed (401 Unauthorized)
       if COVENANT_SIMULATION_TOKEN is unset or empty.
    2. Whenever COVENANT_SIMULATION_TOKEN is configured (both dev and prod), requests lacking
       a valid X-Simulation-Token header are rejected with 401 Unauthorized.
    3. In non-production environments where COVENANT_SIMULATION_TOKEN is unset, simulation is permitted
       to allow local developers to test offline without configuring secrets.
    4. Rejections use uniform 401 Unauthorized without leaking token expectations or comparison progress.
    """
    configured_token = (settings.simulation_token or "").strip() or None

    # Production fail-closed rule: token must be configured in production
    if settings.is_production and not configured_token:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Unauthorized",
        )

    # When token is configured, enforce strict constant-time check
    if configured_token:
        if not x_simulation_token or not hmac.compare_digest(x_simulation_token, configured_token):
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED,
                detail="Unauthorized",
            )
