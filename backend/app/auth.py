"""FastAPI-Users authentication setup.

Provides:
- Email/password router (register, login, forgot-password, reset-password) with SMTP.
- GitHub OAuth2 router with org-membership enforcement.

The existing Google OAuth2 login (api/auth.py) is not modified; it continues to
issue the ``kicad_prism_session`` cookie via the legacy HMAC-signed token system.
All fastapi-users logins (email/password **and** GitHub OAuth) also issue that
same cookie in ``on_after_login`` so the existing RBAC guards in
``core/security.py`` work without changes.
"""

import logging
import smtplib
import uuid
from email.mime.multipart import MIMEMultipart
from email.mime.text import MIMEText
from typing import Optional

import httpx
from fastapi import Depends, HTTPException, Request, Response
from fastapi_users import BaseUserManager, FastAPIUsers, UUIDIDMixin, schemas
from fastapi_users.authentication import AuthenticationBackend, CookieTransport, JWTStrategy
from fastapi_users.db import SQLAlchemyUserDatabase
from httpx_oauth.clients.github import GitHubOAuth2

from app.core.config import settings
from app.core.session import create_session_token, set_session_cookie
from app.db.db import get_user_db
from app.db.models import User
from app.services import access_service

logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# Pydantic schemas for fastapi-users endpoints
# ---------------------------------------------------------------------------

class UserRead(schemas.BaseUser[uuid.UUID]):
    role: str


class UserCreate(schemas.BaseUserCreate):
    pass


class UserUpdate(schemas.BaseUserUpdate):
    pass


# ---------------------------------------------------------------------------
# SMTP email helper
# ---------------------------------------------------------------------------

async def _send_smtp_email(to: str, subject: str, body_html: str) -> None:
    """Send an HTML email via SMTP.  Silently skips when SMTP is not configured."""
    if not settings.SMTP_HOST:
        logger.warning("SMTP is not configured; skipping email to %s", to)
        return

    from_addr = settings.SMTP_FROM or settings.SMTP_USER
    try:
        msg = MIMEMultipart("alternative")
        msg["Subject"] = subject
        msg["From"] = from_addr
        msg["To"] = to
        msg.attach(MIMEText(body_html, "html"))
        with smtplib.SMTP(settings.SMTP_HOST, settings.SMTP_PORT) as smtp:
            if settings.SMTP_TLS:
                smtp.starttls()
            if settings.SMTP_USER and settings.SMTP_PASS:
                smtp.login(settings.SMTP_USER, settings.SMTP_PASS)
            smtp.send_message(msg)
        logger.info("Email sent to %s", to)
    except Exception as exc:
        logger.error("Failed to send email to %s: %s", to, exc)


# ---------------------------------------------------------------------------
# Domain-whitelist helpers
# ---------------------------------------------------------------------------

def _is_domain_whitelisted(email: str) -> bool:
    """Return True if the email's domain is in ALLOWED_EMAIL_DOMAINS."""
    if not settings.ALLOWED_EMAIL_DOMAINS:
        return False
    domain = email.strip().lower().split("@")[-1]
    return domain in {d.lower() for d in settings.ALLOWED_EMAIL_DOMAINS}


def _auto_approve_in_rbac(email: str) -> None:
    """Write a 'viewer' RBAC role for *email* if no role entry exists yet."""
    existing = access_service.resolve_user_role(email)
    if existing is None:
        try:
            access_service.upsert_user_role(email.lower(), "viewer", "system")
            logger.info("Auto-approved %s as viewer (domain whitelisted)", email)
        except Exception as exc:
            logger.error("Failed to auto-approve %s in RBAC: %s", email, exc)


# ---------------------------------------------------------------------------
# GitHub org-membership check
# ---------------------------------------------------------------------------

async def _check_github_org_membership(access_token: str) -> None:
    """Verify the authenticated GitHub user is a member of GITHUB_ORG_LOGIN.

    Raises HTTP 403 when GITHUB_ORG_LOGIN is configured and the user is not a
    member of that organisation.
    """
    org = settings.GITHUB_ORG_LOGIN
    if not org:
        return

    headers = {
        "Authorization": f"Bearer {access_token}",
        "Accept": "application/vnd.github+json",
        "X-GitHub-Api-Version": "2022-11-28",
    }
    async with httpx.AsyncClient() as client:
        user_resp = await client.get("https://api.github.com/user", headers=headers)
        if user_resp.status_code != 200:
            raise HTTPException(status_code=403, detail="Could not verify GitHub identity")

        username = user_resp.json().get("login")
        if not username:
            raise HTTPException(status_code=403, detail="Could not retrieve GitHub username")

        membership_resp = await client.get(
            f"https://api.github.com/orgs/{org}/members/{username}",
            headers=headers,
        )

    if membership_resp.status_code != 204:
        raise HTTPException(
            status_code=403,
            detail=f"Access denied: you must be a member of the '{org}' GitHub organization.",
        )


# ---------------------------------------------------------------------------
# UserManager
# ---------------------------------------------------------------------------

class UserManager(UUIDIDMixin, BaseUserManager[User, uuid.UUID]):
    reset_password_token_secret = settings.SESSION_SECRET
    verification_token_secret = settings.SESSION_SECRET

    async def on_after_register(
        self, user: User, request: Optional[Request] = None
    ) -> None:
        """Called after email/password registration.

        - Whitelisted domain  → writes a 'viewer' RBAC entry automatically.
        - Other domain        → no RBAC entry; access is denied until an admin
                                assigns a role via the existing RBAC UI
                                (PUT /api/settings/access/users/{email}).
        """
        if _is_domain_whitelisted(user.email):
            _auto_approve_in_rbac(user.email)
        else:
            logger.info(
                "User %s registered without auto-approval; "
                "awaiting admin role assignment.",
                user.email,
            )

    async def on_after_forgot_password(
        self, user: User, token: str, request: Optional[Request] = None
    ) -> None:
        base = str(request.base_url).rstrip("/") if request else ""
        reset_url = f"{base}/reset-password?token={token}"
        await _send_smtp_email(
            to=user.email,
            subject="Reset your KiCAD Prism password",
            body_html=(
                "<p>You requested a password reset for your KiCAD Prism account.</p>"
                f"<p><a href='{reset_url}'>Click here to reset your password</a></p>"
                f"<p>Or copy this link: {reset_url}</p>"
                "<p>This link expires in 1 hour.</p>"
            ),
        )

    async def on_after_request_verify(
        self, user: User, token: str, request: Optional[Request] = None
    ) -> None:
        base = str(request.base_url).rstrip("/") if request else ""
        verify_url = f"{base}/verify?token={token}"
        await _send_smtp_email(
            to=user.email,
            subject="Verify your KiCAD Prism email address",
            body_html=(
                "<p>Please verify your email address for KiCAD Prism.</p>"
                f"<p><a href='{verify_url}'>Click here to verify</a></p>"
                f"<p>Or copy this link: {verify_url}</p>"
            ),
        )

    async def on_after_login(
        self,
        user: User,
        request: Optional[Request] = None,
        response: Optional[Response] = None,
    ) -> None:
        """Issue the custom kicad_prism_session cookie after every fastapi-users login.

        This bridges the fastapi-users auth backend to the existing
        ``core/security.py`` RBAC guards, which read the custom HMAC-signed
        session cookie rather than the fastapi-users JWT cookie.  Only users
        with an active RBAC role receive the cookie; users awaiting admin
        approval will not be able to access protected endpoints.
        """
        if response is None:
            return

        role = access_service.resolve_user_role(user.email)
        if role is None:
            return

        name = user.email.split("@")[0]
        token = create_session_token(email=user.email, name=name, picture="", role=role)
        set_session_cookie(response, token)

    async def oauth_callback(
        self,
        oauth_name: str,
        access_token: str,
        account_id: str,
        account_email: str,
        expires_at: Optional[int] = None,
        refresh_token: Optional[str] = None,
        request: Optional[Request] = None,
        *,
        associate_by_email: bool = False,
        is_verified_by_default: bool = False,
    ) -> User:
        """Intercept the OAuth callback to enforce GitHub org membership and
        auto-approve whitelisted domains on first OAuth sign-in.
        """
        if oauth_name == "github":
            await _check_github_org_membership(access_token)

        user = await super().oauth_callback(
            oauth_name=oauth_name,
            access_token=access_token,
            account_id=account_id,
            account_email=account_email,
            expires_at=expires_at,
            refresh_token=refresh_token,
            request=request,
            associate_by_email=associate_by_email,
            is_verified_by_default=is_verified_by_default,
        )

        if _is_domain_whitelisted(account_email):
            _auto_approve_in_rbac(account_email)

        return user


async def get_user_manager(user_db: SQLAlchemyUserDatabase = Depends(get_user_db)):
    yield UserManager(user_db)


# ---------------------------------------------------------------------------
# Authentication backend  (HttpOnly cookie + JWT strategy)
# ---------------------------------------------------------------------------

cookie_transport = CookieTransport(
    cookie_httponly=True,
    cookie_secure=settings.SESSION_COOKIE_SECURE,
)


def get_jwt_strategy() -> JWTStrategy:
    return JWTStrategy(
        secret=settings.SESSION_SECRET,
        lifetime_seconds=settings.SESSION_TTL_HOURS * 3600,
    )


auth_backend = AuthenticationBackend(
    name="cookie",
    transport=cookie_transport,
    get_strategy=get_jwt_strategy,
)


# ---------------------------------------------------------------------------
# GitHub OAuth2 client
# ---------------------------------------------------------------------------

github_oauth_client = GitHubOAuth2(
    client_id=settings.GITHUB_CLIENT_ID,
    client_secret=settings.GITHUB_CLIENT_SECRET,
)


# ---------------------------------------------------------------------------
# FastAPIUsers instance  (shared by all fastapi-users routers)
# ---------------------------------------------------------------------------

fastapi_users_instance = FastAPIUsers[User, uuid.UUID](get_user_manager, [auth_backend])
