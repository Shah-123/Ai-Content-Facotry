"""Optional shared-secret API key gate.

The API exposes every job to every caller: list, read, export, delete. That is
fine on `localhost` for a demo, and not fine the moment the box is reachable by
anyone else.

Set `API_KEY` in `.env` to require callers to present it as `X-API-Key`
(or `?api_key=` for WebSockets, which cannot set headers from the browser).
Leave `API_KEY` unset and the API stays open, so local development and the
existing docker-compose setup work unchanged.

This is a single shared secret, not per-user auth — enough to stop a
drive-by on the LAN, not a replacement for OAuth2 if this is ever deployed
publicly. See readme "Known Limitations".
"""

import os
import secrets

from fastapi import HTTPException, Request, Security, status
from fastapi.security import APIKeyHeader

API_KEY_HEADER = "X-API-Key"

_api_key_header = APIKeyHeader(name=API_KEY_HEADER, auto_error=False)


def _expected_key() -> str:
    return (os.getenv("API_KEY") or "").strip()


def api_key_is_valid(candidate: str | None) -> bool:
    """True when auth is disabled, or when `candidate` matches the configured key."""
    expected = _expected_key()
    if not expected:
        return True  # auth disabled
    # compare_digest to keep the check constant-time
    return bool(candidate) and secrets.compare_digest(candidate, expected)


async def require_api_key(
    request: Request,
    api_key: str | None = Security(_api_key_header),
) -> None:
    """FastAPI dependency. No-op when `API_KEY` is unset.

    Falls back to a `?api_key=` query param for the URLs the browser fetches
    on its own and cannot attach headers to — `<img src>` for generated images
    and the export download links.
    """
    if not api_key_is_valid(api_key):
        api_key = request.query_params.get("api_key")
    if not api_key_is_valid(api_key):
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail=f"Missing or invalid {API_KEY_HEADER} header.",
        )
