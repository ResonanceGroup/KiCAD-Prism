"""
Authentication API endpoints.

Handles Google OAuth login and domain validation.
"""
import logging

from fastapi import APIRouter, Depends, HTTPException, Response
from pydantic import BaseModel, Field
from google.oauth2 import id_token
from google.auth.transport import requests
from app.core.config import settings
from app.core.roles import Role
from app.core.security import AuthenticatedUser, get_current_user, guest_user
from app.core.session import clear_session_cookie, create_session_token, set_session_cookie
from app.services import access_service

router = APIRouter()
logger = logging.getLogger(__name__)


class TokenRequest(BaseModel):
    """Request body for login endpoint."""
    token: str = Field(min_length=1)


class UserSession(BaseModel):
    """User session data returned after successful login."""
    email: str
    name: str
    picture: str = ""
    role: Role


class AuthConfig(BaseModel):
    """Authentication configuration exposed to frontend."""
    auth_enabled: bool
    dev_mode: bool
    google_client_id: str
    github_client_id: str
    workspace_name: str
    providers: list[str]


def _guest_user_session() -> UserSession:
    guest = guest_user()
    return UserSession(email=guest.email, name=guest.name, picture=guest.picture, role=guest.role)


def _validate_allowed_user(email: str) -> None:
    normalized_email = email.strip().casefold()
    if not normalized_email:
        raise HTTPException(status_code=401, detail="Invalid token")

    allowed_users = {user.strip().casefold() for user in settings.ALLOWED_USERS if user.strip()}
    if allowed_users and normalized_email not in allowed_users:
        raise HTTPException(
            status_code=403,
            detail="Access denied. Your email is not in the allowed users list.",
        )

    allowed_domains = {domain.strip().casefold() for domain in settings.ALLOWED_DOMAINS if domain.strip()}
    if allowed_domains:
        domain = normalized_email.split("@")[-1]
        if domain not in allowed_domains:
            raise HTTPException(
                status_code=403,
                detail="Access denied. Your email domain is not in the allowed domains list.",
            )


def _require_session_secret() -> None:
    if settings.AUTH_ENABLED and not settings.SESSION_SECRET:
        raise HTTPException(status_code=500, detail="SESSION_SECRET is not configured")


@router.get("/config", response_model=AuthConfig)
async def get_auth_config():
    """
    Get authentication configuration for the frontend.
    
    This allows the frontend to know whether to show the login page
    or go directly to the gallery.
    """
    providers: list[str] = []
    if settings.GOOGLE_CLIENT_ID:
        providers.append("google")
    if settings.GITHUB_CLIENT_ID:
        providers.append("github")
    if settings.SESSION_SECRET:
        providers.append("email")

    return AuthConfig(
        auth_enabled=settings.AUTH_ENABLED,
        dev_mode=settings.DEV_MODE,
        google_client_id=settings.GOOGLE_CLIENT_ID,
        github_client_id=settings.GITHUB_CLIENT_ID,
        workspace_name=settings.WORKSPACE_NAME,
        providers=providers,
    )


@router.post("/login", response_model=UserSession)
async def login(request: TokenRequest, response: Response):
    """
    Authenticate user with Google OAuth token.
    
    Validates the token, checks domain restrictions, and returns user session data.
    """
    # If auth is disabled, this endpoint shouldn't normally be called,
    # but handle gracefully just in case
    if not settings.AUTH_ENABLED:
        return _guest_user_session()

    _require_session_secret()
    
    try:
        # Verify the token with Google
        id_info = id_token.verify_oauth2_token(
            request.token,
            requests.Request(),
            settings.GOOGLE_CLIENT_ID
        )

        email = (id_info.get("email") or "").strip()
        if not email:
            raise HTTPException(status_code=401, detail="Invalid token")

        _validate_allowed_user(email)
        role = access_service.resolve_user_role(email)
        if not role:
            raise HTTPException(
                status_code=403,
                detail="Access denied. No role assignment found for your account.",
            )

        name = id_info.get("name", email.split("@")[0])
        picture = id_info.get("picture", "")

        token = create_session_token(
            email=email,
            name=name,
            picture=picture,
            role=role,
        )
        set_session_cookie(response, token)

        return UserSession(
            email=email,
            name=name,
            picture=picture,
            role=role,
        )

    except ValueError:
        # Token verification failed
        raise HTTPException(status_code=401, detail="Invalid token")
    except HTTPException:
        # Re-raise HTTP exceptions (like 403 for domain validation)
        raise
    except Exception:
        # Catch-all for unexpected errors
        logger.exception("Authentication error during Google OAuth login")
        raise HTTPException(status_code=500, detail="Authentication service unavailable")


@router.get("/me", response_model=UserSession)
async def get_current_session_user(user: AuthenticatedUser = Depends(get_current_user)):
    return UserSession(
        email=user.email,
        name=user.name,
        picture=user.picture,
        role=user.role,
    )


@router.post("/logout")
async def logout(response: Response):
    clear_session_cookie(response)
    return {"success": True}
