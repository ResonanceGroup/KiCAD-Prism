"""
Authentication API endpoints.

Handles Google OAuth login and domain validation.
"""
import logging
import re
import smtplib
from email.mime.multipart import MIMEMultipart
from email.mime.text import MIMEText
from typing import Optional

from fastapi import APIRouter, Depends, HTTPException, Response
from pydantic import BaseModel, Field
from sqlalchemy import func, select
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
    username: Optional[str] = None
    notification_email: Optional[str] = None
    has_password: bool = False
    github_username: Optional[str] = None
    github_email: Optional[str] = None


class AuthConfig(BaseModel):
    """Authentication configuration exposed to frontend."""
    auth_enabled: bool
    dev_mode: bool
    google_client_id: str
    github_client_id: str
    workspace_name: str
    providers: list[str]
    github_app_configured: bool


# ---------------------------------------------------------------------------
# Profile update schemas
# ---------------------------------------------------------------------------

_USERNAME_RE = re.compile(r"^[a-zA-Z0-9_.\-]{3,50}$")


class UpdateProfileRequest(BaseModel):
    """Request body for profile update."""
    username: Optional[str] = Field(default=None, min_length=3, max_length=50)
    display_name: Optional[str] = Field(default=None, max_length=100)


class SetNotificationEmailRequest(BaseModel):
    """Request body for setting a notification/secondary email."""
    email: str = Field(min_length=3, max_length=254)


class SetPasswordRequest(BaseModel):
    """Request body for setting a password on an OAuth-only account."""
    password: str = Field(min_length=8)


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
    username: Optional[str] = None
    notification_email: Optional[str] = None
    has_password = False
    github_username: Optional[str] = None
    github_email: Optional[str] = None
    try:
        result = await session.execute(
            select(UserModel).where(UserModel.email == user.email.lower())
        )
        db_user = result.unique().scalar_one_or_none()
        if db_user:
            username = db_user.username
            notification_email = db_user.notification_email
            github_username = db_user.github_username
            github_email = db_user.github_email
            # A user has a usable password when hashed_password is set and is not
            # the fastapi-users "unusable password" sentinel ("!").
            has_password = bool(db_user.hashed_password and db_user.hashed_password != "!")
            github_connected = any(
                acc.oauth_name == "github" for acc in (db_user.oauth_accounts or [])
            )
    except Exception:
        pass  # Non-fatal — fall back to defaults

    return UserSession(
        email=user.email,
        name=user.name,
        picture=user.picture,
        role=user.role,
        github_connected=github_connected,
        username=username,
        notification_email=notification_email,
        has_password=has_password,
        github_username=github_username,
        github_email=github_email,
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


# ---------------------------------------------------------------------------
# User profile endpoints
# ---------------------------------------------------------------------------

@router.get("/profile", response_model=UserSession)
async def get_profile(
    user: AuthenticatedUser = Depends(get_current_user),
    session=Depends(get_async_session),
):
    """Return the full profile for the currently authenticated user."""
    return await get_current_session_user(user=user, session=session)


@router.patch("/profile", response_model=UserSession)
async def update_profile(
    body: UpdateProfileRequest,
    user: AuthenticatedUser = Depends(get_current_user),
    session=Depends(get_async_session),
):
    """Update the current user's username and/or display name."""
    username = body.username
    display_name = body.display_name

    # Validate username format
    if username is not None:
        if not _USERNAME_RE.match(username):
            raise HTTPException(
                status_code=422,
                detail="Username must be 3–50 characters and contain only letters, numbers, underscores, hyphens, or dots.",
            )
        # Check uniqueness (case-insensitive)
        existing = await session.execute(
            select(UserModel).where(
                func.lower(UserModel.username) == username.lower(),
                UserModel.email != user.email.lower(),
            )
        )
        if existing.unique().scalar_one_or_none() is not None:
            raise HTTPException(status_code=409, detail="Username is already taken.")

    result = await session.execute(
        select(UserModel).where(UserModel.email == user.email.lower())
    )
    db_user = result.unique().scalar_one_or_none()
    if db_user is None:
        raise HTTPException(status_code=404, detail="User not found.")

    if username is not None:
        db_user.username = username
    if display_name is not None:
        db_user.display_name = display_name if display_name.strip() else None
    await session.commit()
    await session.refresh(db_user)

    return await get_current_session_user(user=user, session=session)


@router.post("/profile/notification-email", response_model=UserSession)
async def set_notification_email(
    body: SetNotificationEmailRequest,
    user: AuthenticatedUser = Depends(get_current_user),
    session=Depends(get_async_session),
):
    """Set or replace the notification (secondary) email for the current user.

    The notification email:
    - Must be different from the account's primary email.
    - Must not be used as a primary email by any other user.
    - Must not be used as a notification email by any other user.
    """
    new_email = body.email.strip().lower()

    if new_email == user.email.lower():
        raise HTTPException(
            status_code=422,
            detail="Notification email must be different from your primary email.",
        )

    # Check it isn't already a primary email of another account
    primary_clash = await session.execute(
        select(UserModel).where(
            UserModel.email == new_email,
        )
    )
    if primary_clash.unique().scalar_one_or_none() is not None:
        raise HTTPException(
            status_code=409,
            detail="That email is already registered as a primary account email.",
        )

    # Check it isn't already a notification email of another account
    notif_clash = await session.execute(
        select(UserModel).where(
            UserModel.notification_email == new_email,
            UserModel.email != user.email.lower(),
        )
    )
    if notif_clash.unique().scalar_one_or_none() is not None:
        raise HTTPException(
            status_code=409,
            detail="That email is already associated with another account.",
        )

    result = await session.execute(
        select(UserModel).where(UserModel.email == user.email.lower())
    )
    db_user = result.unique().scalar_one_or_none()
    if db_user is None:
        raise HTTPException(status_code=404, detail="User not found.")

    db_user.notification_email = new_email
    await session.commit()

    return await get_current_session_user(user=user, session=session)


@router.delete("/profile/notification-email", response_model=UserSession)
async def remove_notification_email(
    user: AuthenticatedUser = Depends(get_current_user),
    session=Depends(get_async_session),
):
    """Remove the notification (secondary) email from the current user's account."""
    result = await session.execute(
        select(UserModel).where(UserModel.email == user.email.lower())
    )
    db_user = result.unique().scalar_one_or_none()
    if db_user is None:
        raise HTTPException(status_code=404, detail="User not found.")

    db_user.notification_email = None
    await session.commit()

    return await get_current_session_user(user=user, session=session)


@router.post("/profile/set-password")
async def set_password(
    body: SetPasswordRequest,
    user: AuthenticatedUser = Depends(get_current_user),
    session=Depends(get_async_session),
):
    """Set a password for an account that currently has none (e.g. GitHub-only sign-in).

    This endpoint only works when the account has no usable password.
    Users who already have a password should use the forgot-password / reset
    flow instead.
    """
    from app.auth import get_user_manager, UserUpdate
    from app.db.db import get_user_db
    from fastapi_users.db import SQLAlchemyUserDatabase
    from app.db.models import OAuthAccount

    result = await session.execute(
        select(UserModel).where(UserModel.email == user.email.lower())
    )
    db_user = result.unique().scalar_one_or_none()
    if db_user is None:
        raise HTTPException(status_code=404, detail="User not found.")

    has_password = bool(db_user.hashed_password and db_user.hashed_password != "!")
    if has_password:
        raise HTTPException(
            status_code=409,
            detail="Your account already has a password. Use the forgot-password flow to change it.",
        )

    user_db = SQLAlchemyUserDatabase(session, UserModel, OAuthAccount)
    async for manager in get_user_manager(user_db):
        await manager.update(
            UserUpdate(password=body.password),
            db_user,
            safe=True,
        )

    return {"success": True, "message": "Password set successfully. You can now log in with your email and password."}


@router.delete("/profile/github")
async def unlink_github(
    user: AuthenticatedUser = Depends(get_current_user),
    session=Depends(get_async_session),
):
    """
    Unlink the user's GitHub OAuth account.
    
    Removes the OAuth account association, clears GitHub-specific fields,
    and revokes the OAuth token on GitHub's side to ensure the authorization
    is fully terminated.
    """
    import base64

    logger.info("GitHub unlink requested by user: %s", user.email)

    result = await session.execute(
        select(UserModel).where(UserModel.email == user.email.lower())
    )
    db_user = result.unique().scalar_one_or_none()
    if db_user is None:
        raise HTTPException(status_code=404, detail="User not found.")

    # Check if the user has a GitHub OAuth account linked
    github_account = next(
        (acc for acc in (db_user.oauth_accounts or []) if acc.oauth_name == "github"),
        None,
    )
    if github_account is None:
        raise HTTPException(status_code=400, detail="No GitHub account is currently linked.")

    logger.info("Found GitHub account to unlink: account_id=%s", github_account.account_id)

    # Revoke the OAuth token on GitHub's side before deleting locally
    # This ensures the user's GitHub authorization is fully terminated
    if github_account.access_token and settings.GITHUB_CLIENT_ID and settings.GITHUB_CLIENT_SECRET:
        try:
            import httpx
            logger.info("Attempting to revoke GitHub token for %s", user.email)
            auth_string = f"{settings.GITHUB_CLIENT_ID}:{settings.GITHUB_CLIENT_SECRET}"
            auth_encoded = base64.b64encode(auth_string.encode()).decode()
            async with httpx.AsyncClient(timeout=10.0) as client:
                response = await client.request(
                    method="DELETE",
                    url=f"https://api.github.com/applications/{settings.GITHUB_CLIENT_ID}/token",
                    headers={
                        "Authorization": f"Basic {auth_encoded}",
                        "Accept": "application/vnd.github+json",
                        "X-GitHub-Api-Version": "2022-11-28",
                    },
                    json={"access_token": github_account.access_token},
                )
                if response.status_code in (204, 404):
                    logger.info(
                        "Successfully revoked GitHub token for %s: HTTP %d",
                        user.email,
                        response.status_code,
                    )
                else:
                    logger.warning(
                        "Failed to revoke GitHub token for %s: HTTP %d, body: %s",
                        user.email,
                        response.status_code,
                        response.text,
                    )
        except Exception as exc:
            # Log but don't block the unlink if revocation fails
            logger.warning("Failed to revoke GitHub token for %s: %s", user.email, exc)

    # Remove the OAuth account from the user
    db_user.oauth_accounts.remove(github_account)
    await session.delete(github_account)

    # Clear GitHub-specific fields on the user
    db_user.github_username = None
    db_user.github_email = None
    db_user.github_access_token_encrypted = None

    await session.commit()

    logger.info("Successfully unlinked GitHub account for user: %s", user.email)
    return {"success": True, "message": "GitHub account unlinked successfully."}
