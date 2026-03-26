"""GitHub App installation token utilities.

Handles RS256 JWT generation and GitHub App installation access-token lifecycle.
All server-side GitHub API calls (repo listing, cloning, webhook-triggered
syncs) use the installation token rather than per-user OAuth tokens.

Required environment variables
-------------------------------
GITHUB_APP_ID              Numeric GitHub App ID (shown on the App settings page).
GITHUB_APP_PRIVATE_KEY     RSA private key in one of three formats:
                             1. Base64-encoded PEM  (recommended for env vars)
                                Generate with:  base64 -w 0 private-key.pem
                             2. Raw PEM with escaped newlines  (``\\n`` literal)
                             3. Absolute path to a .pem file
GITHUB_APP_INSTALLATION_ID Installation ID for the target org/account.
                             Find it at:
                               /orgs/{org}/installations  OR
                             the GitHub App → Installations page.
"""

from __future__ import annotations

import asyncio
import base64
import logging
import os
import time
from datetime import datetime, timezone
from typing import Optional

import httpx
from jose import jwt

from app.core.config import settings

logger = logging.getLogger(__name__)

_GITHUB_API_BASE = "https://api.github.com"
_GITHUB_HEADERS = {
    "Accept": "application/vnd.github+json",
    "X-GitHub-Api-Version": "2022-11-28",
}

# ---------------------------------------------------------------------------
# Installation-token cache (module-level; refreshed automatically)
# ---------------------------------------------------------------------------
_cached_token: Optional[str] = None
_cached_token_expires_at: int = 0  # Unix timestamp
_token_lock = asyncio.Lock()


# ---------------------------------------------------------------------------
# Private helpers
# ---------------------------------------------------------------------------

def _decode_private_key() -> str:
    """Decode the GitHub App RSA private key from settings.

    Accepted formats (auto-detected):

    1. Absolute file path to a ``.pem`` file.
    2. Raw PEM string (may use literal ``\\n`` escape sequences).
    3. Base64-encoded PEM  (recommended for environment variables).
    """
    raw = settings.GITHUB_APP_PRIVATE_KEY.strip()
    if not raw:
        raise ValueError("GITHUB_APP_PRIVATE_KEY is not configured")

    # 1. File path
    if os.path.isabs(raw) and os.path.isfile(raw):
        with open(raw, "r", encoding="utf-8") as fh:
            return fh.read()

    # 2. Raw PEM (starts with the standard PEM header)
    if raw.startswith("-----"):
        return raw.replace("\\n", "\n")

    # 3. Base64-encoded PEM
    #    Linux:  base64 -w 0 private-key.pem
    #    macOS:  base64 -i private-key.pem | tr -d '\n'
    #    Portable: base64 < private-key.pem | tr -d '\n'
    try:
        return base64.b64decode(raw).decode("utf-8")
    except Exception as exc:
        raise ValueError(f"Cannot decode GITHUB_APP_PRIVATE_KEY: {exc}") from exc


def _generate_app_jwt() -> str:
    """Return a signed RS256 JWT for GitHub App authentication.

    Valid for 10 minutes.  Back-dated by 60 seconds to tolerate clock skew
    between this server and GitHub's API endpoints.
    """
    now = int(time.time())
    payload = {
        "iat": now - 60,   # issued-at (back-dated for clock skew)
        "exp": now + 600,  # expires in 10 minutes
        "iss": settings.GITHUB_APP_ID,
    }
    pem = _decode_private_key()
    return jwt.encode(payload, pem, algorithm="RS256")


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------

def is_app_configured() -> bool:
    """Return ``True`` when all required GitHub App settings are present."""
    return bool(
        settings.GITHUB_APP_ID
        and settings.GITHUB_APP_PRIVATE_KEY
        and settings.GITHUB_APP_INSTALLATION_ID
    )


async def get_installation_token() -> str:
    """Return a valid GitHub App installation access token.

    Tokens are cached and automatically refreshed 5 minutes before expiry.
    Thread-safe via an :class:`asyncio.Lock` so concurrent requests do not
    race to refresh the same token.

    Raises :class:`ValueError` when the GitHub App is not fully configured.
    Raises :class:`httpx.HTTPStatusError` on GitHub API errors.
    """
    global _cached_token, _cached_token_expires_at

    now = int(time.time())
    # Fast-path: reuse cached token if still valid (with 5-min buffer)
    if _cached_token and now < _cached_token_expires_at - 300:
        return _cached_token

    async with _token_lock:
        # Re-check after lock acquisition (another coroutine may have refreshed)
        now = int(time.time())
        if _cached_token and now < _cached_token_expires_at - 300:
            return _cached_token

        if not is_app_configured():
            raise ValueError(
                "GitHub App is not fully configured. "
                "Set GITHUB_APP_ID, GITHUB_APP_PRIVATE_KEY, and GITHUB_APP_INSTALLATION_ID."
            )

        app_jwt = _generate_app_jwt()
        async with httpx.AsyncClient() as client:
            resp = await client.post(
                f"{_GITHUB_API_BASE}/app/installations"
                f"/{settings.GITHUB_APP_INSTALLATION_ID}/access_tokens",
                headers={
                    **_GITHUB_HEADERS,
                    "Authorization": f"Bearer {app_jwt}",
                },
            )
            if resp.status_code == 401:
                raise ValueError(
                    "GitHub App JWT rejected — verify GITHUB_APP_ID and GITHUB_APP_PRIVATE_KEY."
                )
            if resp.status_code == 404:
                raise ValueError(
                    f"Installation {settings.GITHUB_APP_INSTALLATION_ID!r} not found — "
                    "verify GITHUB_APP_INSTALLATION_ID."
                )
            resp.raise_for_status()
            data = resp.json()

        _cached_token = data["token"]
        # Parse the ISO-8601 expiry timestamp returned by GitHub (has "Z" suffix)
        expires_str: str = data.get("expires_at", "")
        try:
            dt = datetime.fromisoformat(expires_str.replace("Z", "+00:00"))
            _cached_token_expires_at = int(dt.timestamp())
        except Exception:
            # Fallback: assume 1-hour lifetime
            _cached_token_expires_at = now + 3600

        logger.info(
            "GitHub App installation token refreshed (installation=%s, expires=%s)",
            settings.GITHUB_APP_INSTALLATION_ID,
            expires_str,
        )
        return _cached_token


async def get_app_installation_client() -> httpx.AsyncClient:
    """Return a pre-configured :class:`httpx.AsyncClient` using the GitHub
    App installation token.

    Use as an async context manager::

        async with await get_app_installation_client() as client:
            resp = await client.get("/orgs/myorg/repos")
    """
    token = await get_installation_token()
    return httpx.AsyncClient(
        base_url=_GITHUB_API_BASE,
        headers={
            **_GITHUB_HEADERS,
            "Authorization": f"Bearer {token}",
        },
    )
