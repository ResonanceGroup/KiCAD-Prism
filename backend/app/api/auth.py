"""
Authentication API endpoints.

Handles Google OAuth login and domain validation.
"""
import logging
import smtplib
from email.mime.multipart import MIMEMultipart
from email.mime.text import MIMEText
from typing import Optional

from fastapi import APIRouter, Depends, HTTPException, Response
from pydantic import BaseModel, Field
from sqlalchemy import select
from google.oauth2 import id_token
from google.auth.transport import requests
from app.core.config import settings
from app.core.roles import Role
from app.core.security import AuthenticatedUser, get_current_user, guest_user
from app.core.session import clear_session_cookie, create_session_token, set_session_cookie
from app.db.db import async_session_maker, get_async_session
from app.db.models import OAuthAccount, ProjectMembership, User as UserModel
from app.services import access_service

router = APIRouter()
logger = logging.getLogger(__name__)


class TokenRequest(BaseModel):
    """Request body for login endpoint."""
    token: str = Field(min_length=1)


# TODO: TESTING ONLY — remove before production
class TestEmailRequest(BaseModel):
    """Request body for SMTP test endpoint."""
    email: str = Field(min_length=3)


class UserSession(BaseModel):
    """User session data returned after successful login."""
    email: str
    name: str
    picture: str = ""
    role: Role
    github_connected: bool = False


class AuthConfig(BaseModel):
    """Authentication configuration exposed to frontend."""
    auth_enabled: bool
    dev_mode: bool
    google_client_id: str
    github_client_id: str
    workspace_name: str
    providers: list[str]
    github_app_configured: bool


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
        github_app_configured=bool(
            settings.GITHUB_APP_ID
            and settings.GITHUB_APP_PRIVATE_KEY
            and settings.GITHUB_APP_INSTALLATION_ID
        ),
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
async def get_current_session_user(
    user: AuthenticatedUser = Depends(get_current_user),
    session=Depends(get_async_session),
):
    """Return the current user's session info, including GitHub connection status."""
    # Check whether the user has a linked GitHub OAuth account in the database
    github_connected = False
    try:
        result = await session.execute(
            select(OAuthAccount)
            .join(UserModel, OAuthAccount.user_id == UserModel.id)
            .where(
                UserModel.email == user.email.lower(),
                OAuthAccount.oauth_name == "github",
            )
        )
        github_connected = result.scalar_one_or_none() is not None
    except Exception:
        pass  # Non-fatal — fall back to github_connected=False

    return UserSession(
        email=user.email,
        name=user.name,
        picture=user.picture,
        role=user.role,
        github_connected=github_connected,
    )


@router.post("/logout")
async def logout(response: Response):
    clear_session_cookie(response)
    return {"success": True}


# TODO: TESTING ONLY — remove this endpoint before production
@router.post("/test-email")
async def send_test_email(request: TestEmailRequest):
    """Send a test email to verify SMTP configuration. FOR TESTING ONLY."""
    if not settings.SMTP_HOST:
        raise HTTPException(status_code=400, detail="SMTP is not configured (SMTP_HOST is empty)")

    from_addr = settings.SMTP_FROM or settings.SMTP_USER
    msg = MIMEMultipart("alternative")
    msg["Subject"] = "KiCAD Prism \u2014 SMTP Test"
    msg["From"] = from_addr
    msg["To"] = request.email
    msg.attach(MIMEText(
        "<p>This is a test email from <strong>KiCAD Prism</strong>.</p>"
        "<p>If you received this, your SMTP configuration is working correctly.</p>",
        "html",
    ))

    try:
        if settings.SMTP_PORT == 465:
            with smtplib.SMTP_SSL(settings.SMTP_HOST, settings.SMTP_PORT) as smtp:
                if settings.SMTP_USER and settings.SMTP_PASS:
                    smtp.login(settings.SMTP_USER, settings.SMTP_PASS)
                smtp.send_message(msg)
        else:
            with smtplib.SMTP(settings.SMTP_HOST, settings.SMTP_PORT) as smtp:
                if settings.SMTP_TLS:
                    smtp.starttls()
                if settings.SMTP_USER and settings.SMTP_PASS:
                    smtp.login(settings.SMTP_USER, settings.SMTP_PASS)
                smtp.send_message(msg)
        return {"success": True, "message": f"Test email sent to {request.email}"}
    except Exception as exc:
        raise HTTPException(status_code=500, detail=f"SMTP error: {exc}")


@router.get("/users/search")
async def search_users(
    q: str = "",
    project_id: Optional[str] = None,
    user: AuthenticatedUser = Depends(get_current_user),
):
    """
    Return user emails matching the query string (for @mention autocomplete).
    Returns at most 10 results. Requires a logged-in user.

    When ``project_id`` is supplied the results are restricted to users who
    hold a *manager* or *admin* project-level role on that project (Viewer
    accounts are excluded because they cannot post comments or reply to
    mentions).
    """
    if not q or len(q) < 1:
        return []
    q_lower = q.lower()
    assignments = access_service.list_role_assignments()

    if project_id:
        async with async_session_maker() as session:
            result = await session.execute(
                select(ProjectMembership).where(
                    ProjectMembership.project_id == project_id,
                    ProjectMembership.project_role.in_(["manager", "admin"]),
                )
            )
            member_emails = {m.user_email.lower() for m in result.scalars().all()}
        assignments = [a for a in assignments if a["email"].lower() in member_emails]

    results = [
        {"email": a["email"]}
        for a in assignments
        if q_lower in a["email"].lower()
    ]
    return results[:10]


@router.get("/users")
async def list_users(
    user: AuthenticatedUser = Depends(get_current_user),
):
    """Return all workspace users with their UAC role. Requires authentication."""
    assignments = access_service.list_role_assignments()
    return [{"email": a["email"], "role": a["role"]} for a in assignments]
