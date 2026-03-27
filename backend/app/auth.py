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
import re
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
from sqlalchemy import func, select

from app.core.config import settings
from app.core.encryption import decrypt_token, encrypt_token
from app.core.session import create_session_token, set_session_cookie
from app.db.db import get_async_session, get_user_db
from app.db.models import OAuthAccount, User
from app.services import access_service

logger = logging.getLogger(__name__)

# Username validation pattern (shared with api/auth.py)
_USERNAME_RE = re.compile(r"^[a-zA-Z0-9_.\-]{3,50}$")


# ---------------------------------------------------------------------------
# Pydantic schemas for fastapi-users endpoints
# ---------------------------------------------------------------------------

class UserRead(schemas.BaseUser[uuid.UUID]):
    role: str
    username: Optional[str] = None
    display_name: Optional[str] = None
    notification_email: Optional[str] = None
    github_username: Optional[str] = None
    github_email: Optional[str] = None


class UserCreate(schemas.BaseUserCreate):
    username: Optional[str] = None


class UserUpdate(schemas.BaseUserUpdate):
    username: Optional[str] = None
    display_name: Optional[str] = None
    notification_email: Optional[str] = None


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


def _auto_assign_github_designer(email: str) -> None:
    """Assign 'designer' role to GitHub org members on first OAuth sign-in.

    Upgrades an existing 'viewer' role to 'designer' to ensure org members
    always receive at least designer access.  Admins are never downgraded.
    """
    existing = access_service.resolve_user_role(email)
    if existing in (None, "viewer"):
        try:
            access_service.upsert_user_role(email.lower(), "designer", "system:github_oauth")
            logger.info("Auto-assigned designer role to GitHub org member: %s", email)
        except Exception as exc:
            logger.error("Failed to assign designer role to %s: %s", email, exc)


async def _notify_admins_new_registration(new_user_email: str) -> None:
    """Email all current admins when a non-whitelisted user registers."""
    admin_emails: list[str] = list(settings.BOOTSTRAP_ADMIN_USERS)
    try:
        for assignment in access_service.list_role_assignments():
            if assignment.get("role") == "admin":
                addr = assignment["email"]
                if addr not in admin_emails:
                    admin_emails.append(addr)
    except Exception:
        pass
    for admin_email in admin_emails:
        if not admin_email:
            continue
        await _send_smtp_email(
            to=admin_email,
            subject="KiCAD Prism — New registration pending approval",
            body_html=(
                f"<p>A new user has registered and is awaiting your approval:</p>"
                f"<p><strong>{new_user_email}</strong></p>"
                "<p>Sign in as an admin and go to "
                "<em>Settings → Pending Approvals</em> to approve or deny this request.</p>"
            ),
        )


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
    async with httpx.AsyncClient(timeout=15.0) as client:
        # Use /user/memberships/orgs/{org} instead of /orgs/{org}/members/{username}.
        # The members endpoint returns 404 for private org members; the memberships
        # endpoint checks the authenticated user's own membership and works for both
        # public and private membership visibility.
        membership_resp = await client.get(
            f"https://api.github.com/user/memberships/orgs/{org}",
            headers=headers,
        )

    if membership_resp.status_code != 200:
        raise HTTPException(
            status_code=403,
            detail=f"Access denied: you must be a member of the '{org}' GitHub organization.",
        )

    state = membership_resp.json().get("state", "")
    if state != "active":
        raise HTTPException(
            status_code=403,
            detail=f"Access denied: your membership in '{org}' is not yet active (state: {state}).",
        )


async def _fetch_github_user_info(access_token: str) -> dict:
    """Fetch the authenticated user's info from the GitHub API.

    Returns an empty dict when the request fails so callers can gracefully
    degrade rather than blocking the login flow.
    """
    headers = {
        "Authorization": f"Bearer {access_token}",
        "Accept": "application/vnd.github+json",
        "X-GitHub-Api-Version": "2022-11-28",
    }
    try:
        async with httpx.AsyncClient(timeout=15.0) as client:
            resp = await client.get("https://api.github.com/user", headers=headers)
            if resp.status_code == 200:
                return resp.json()
    except Exception as exc:
        logger.warning("Failed to fetch GitHub user info: %s", exc)
    return {}


# ---------------------------------------------------------------------------
# UserManager
# ---------------------------------------------------------------------------

class UserManager(UUIDIDMixin, BaseUserManager[User, uuid.UUID]):
    reset_password_token_secret = settings.SESSION_SECRET
    verification_token_secret = settings.SESSION_SECRET

    async def create(
        self,
        user_create: UserCreate,  # type: ignore[override]
        safe: bool = False,
        request: Optional[Request] = None,
    ) -> User:
        """Override create to validate and persist a username supplied at registration."""
        username: Optional[str] = getattr(user_create, "username", None)
        if username:
            username = username.strip()
            if not _USERNAME_RE.match(username):
                raise HTTPException(
                    status_code=422,
                    detail="Username must be 3–50 characters and contain only letters, numbers, underscores, hyphens, or dots.",
                )
            # Case-insensitive uniqueness check
            existing = await self.user_db.session.execute(
                select(User).where(func.lower(User.username) == username.lower())
            )
            if existing.unique().scalar_one_or_none() is not None:
                raise HTTPException(status_code=409, detail="Username is already taken.")

        return await super().create(user_create, safe=safe, request=request)

    async def on_after_register(
        self, user: User, request: Optional[Request] = None
    ) -> None:
        """Called after email/password registration.

        All new email/password accounts are automatically granted the 'viewer'
        role so they can immediately explore the workspace.  An admin can
        promote the user to 'designer' or 'admin' at any time via the RBAC UI.

        Bootstrap admins and users that already have a role assignment are left
        untouched.
        """
        if access_service.resolve_user_role(user.email) is None:
            try:
                access_service.upsert_user_role(user.email.lower(), "viewer", "system:email_register")
                logger.info("Auto-assigned viewer role to new email user: %s", user.email)
            except Exception as exc:
                logger.error("Failed to assign viewer role to %s: %s", user.email, exc)

        if not user.is_verified:
            try:
                await self.request_verify(user, request)
            except Exception as exc:
                logger.warning("Could not send verification email to %s: %s", user.email, exc)

    async def on_after_forgot_password(
        self, user: User, token: str, request: Optional[Request] = None
    ) -> None:
        base = settings.APP_URL.rstrip("/") if settings.APP_URL else (
            str(request.base_url).rstrip("/") if request else ""
        )
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
        base = settings.APP_URL.rstrip("/") if settings.APP_URL else (
            str(request.base_url).rstrip("/") if request else ""
        )
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

        Also applies post-login checks:

        - **Domain whitelist**: auto-approves the user as *viewer* in the RBAC
          store if their email domain is in ``ALLOWED_EMAIL_DOMAINS`` and they
          have not yet been assigned a role.  This is idempotent and serves as a
          safety net in case the auto-approval during registration or OAuth
          callback was skipped.

        - **GitHub org check**: when ``GITHUB_ORG_LOGIN`` is configured and the
          user has a linked GitHub OAuth account, the stored access token is used
          to re-verify org membership.  This guards against users who have both
          GitHub OAuth and email/password credentials and attempt to bypass the
          OAuth-callback check by logging in with their password after their org
          membership has been revoked.

        Only users with an active RBAC role receive the custom session cookie;
        users awaiting admin approval will not be able to access protected
        endpoints.
        """
        # Re-apply domain whitelist auto-approval in case it was skipped at
        # registration or during a previous OAuth callback.
        if _is_domain_whitelisted(user.email):
            _auto_approve_in_rbac(user.email)

        # GitHub org membership re-check for users with a linked GitHub account.
        # When the org check passes, also ensure the user has at least designer role.
        if settings.GITHUB_ORG_LOGIN:
            github_account = next(
                (acc for acc in (user.oauth_accounts or []) if acc.oauth_name == "github"),
                None,
            )
            if github_account and github_account.access_token:
                await _check_github_org_membership(github_account.access_token)
                # Promote to designer if still at viewer level
                _auto_assign_github_designer(user.email)

        if response is None:
            return

        role = access_service.resolve_user_role(user.email)
        if role is None:
            raise HTTPException(
                status_code=403,
                detail="Your account is pending admin approval. You will be notified when access is granted.",
            )

        name = user.display_name or user.username or user.email.split("@")[0]
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

        if oauth_name == "github":
            encrypted = encrypt_token(access_token)
            if encrypted is not None:
                user = await self.user_db.update(user, {"github_access_token_encrypted": encrypted})
            # GitHub org members are auto-promoted to designer
            _auto_assign_github_designer(account_email)

            # Fetch the GitHub login (username) and try to store it.
            # If the login isn't taken yet, also set it as the in-app username.
            github_info = await _fetch_github_user_info(access_token)
            github_login: Optional[str] = github_info.get("login") or None
            updates: dict = {"github_email": account_email}
            if github_login:
                updates["github_username"] = github_login
                # Only set the in-app username if the user doesn't have one yet.
                if not user.username:
                    # Case-insensitive check: if no other user has the same login
                    clash = await self.user_db.session.execute(
                        select(User).where(
                            func.lower(User.username) == github_login.lower(),
                            User.email != account_email.lower(),
                        )
                    )
                    if clash.unique().scalar_one_or_none() is None:
                        updates["username"] = github_login
            try:
                user = await self.user_db.update(user, updates)
            except Exception as exc:
                logger.warning("Could not update GitHub info for %s: %s", account_email, exc)
        elif _is_domain_whitelisted(account_email):
            _auto_approve_in_rbac(account_email)

        return user

    async def oauth_associate_callback(
        self,
        user: User,
        oauth_name: str,
        access_token: str,
        account_id: str,
        account_email: str,
        expires_at: Optional[int] = None,
        refresh_token: Optional[str] = None,
        request: Optional[Request] = None,
    ) -> User:
        """Intercept the OAuth-associate callback to apply GitHub-specific
        post-link logic (identical to the post-login logic in oauth_callback).
        """
        logger.info(
            "OAuth associate callback started: user=%s, oauth_name=%s, account_email=%s",
            user.email,
            oauth_name,
            account_email,
        )
        
        user = await super().oauth_associate_callback(
            user,
            oauth_name,
            access_token,
            account_id,
            account_email,
            expires_at,
            refresh_token,
            request,
        )

        if oauth_name == "github":
            encrypted = encrypt_token(access_token)
            updates: dict = {"github_email": account_email}
            if encrypted is not None:
                updates["github_access_token_encrypted"] = encrypted

            # Fetch the GitHub login and try to set it as the in-app username.
            github_info = await _fetch_github_user_info(access_token)
            github_login: Optional[str] = github_info.get("login") or None
            if github_login:
                updates["github_username"] = github_login
                if not user.username:
                    clash = await self.user_db.session.execute(
                        select(User).where(
                            func.lower(User.username) == github_login.lower(),
                            User.email != user.email,
                        )
                    )
                    if clash.unique().scalar_one_or_none() is None:
                        updates["username"] = github_login

            if updates:
                try:
                    user = await self.user_db.update(user, updates)
                except Exception as exc:
                    logger.warning(
                        "Could not update GitHub info after account link for %s: %s",
                        user.email,
                        exc,
                    )

            _auto_assign_github_designer(user.email)

        logger.info(
            "OAuth associate callback completed successfully: user=%s, oauth_name=%s",
            user.email,
            oauth_name,
        )
        return user


# ---------------------------------------------------------------------------
# UserManager dependency
# ---------------------------------------------------------------------------

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
# This uses a GitHub Organization-owned OAuth App (recommended).
# Create it at: https://github.com/organizations/YOUR_ORG/settings/applications/new
# The consent screen will show your organization's name and branding.

class _TimeoutGitHubOAuth2(GitHubOAuth2):
    """GitHubOAuth2 client with explicit timeout to prevent Cloudflare 524 errors.
    
    Overrides get_httpx_client to return a client with a 30-second timeout for
    all outbound requests to GitHub's API (token exchange, get_id_email, etc.).
    This prevents the OAuth callback from exceeding Cloudflare's 100s timeout.
    """
    def get_httpx_client(self):
        import contextlib
        @contextlib.asynccontextmanager
        async def _client():
            async with httpx.AsyncClient(timeout=30.0) as client:
                yield client
        return _client()


github_oauth_client = _TimeoutGitHubOAuth2(
    client_id=settings.GITHUB_CLIENT_ID,
    client_secret=settings.GITHUB_CLIENT_SECRET,
    scopes=[s.strip() for s in settings.GITHUB_SCOPES.split(",") if s.strip()],
)


# ---------------------------------------------------------------------------
# FastAPIUsers instance  (shared by all fastapi-users routers)
# ---------------------------------------------------------------------------

fastapi_users_instance = FastAPIUsers[User, uuid.UUID](get_user_manager, [auth_backend])


# ---------------------------------------------------------------------------
# Helper: Get GitHub token for an authenticated user
# ---------------------------------------------------------------------------

async def get_github_token_for_user(email: str, session) -> Optional[str]:
    """Retrieve the GitHub OAuth token for a user by email.
    
    Returns None if the user hasn't linked their GitHub account.
    
    The token is retrieved from:
    1. ``user.github_access_token_encrypted`` (if TOKEN_ENCRYPTION_KEY is set), or
    2. The ``oauth_accounts`` table (fallback when encryption is disabled).
    """
    token: Optional[str] = None
    
    # Query the User model to check for encrypted token and oauth accounts
    result = await session.execute(
        select(User).where(func.lower(User.email) == email.lower())
    )
    db_user = result.unique().scalar_one_or_none()
    
    if not db_user:
        logger.debug("No user found with email %s", email)
        return None
    
    # Try encrypted token first (if TOKEN_ENCRYPTION_KEY is configured)
    if db_user.github_access_token_encrypted:
        token = decrypt_token(db_user.github_access_token_encrypted)
        if token:
            logger.debug("Retrieved GitHub token from encrypted user field for %s", email)
            return token
    
    # Fallback: query oauth_accounts table for GitHub token
    result = await session.execute(
        select(OAuthAccount).where(
            OAuthAccount.user_id == db_user.id,
            OAuthAccount.oauth_name == "github",
        )
    )
    oauth_account = result.scalar_one_or_none()
    if oauth_account and oauth_account.access_token:
        token = oauth_account.access_token
        logger.debug("Retrieved GitHub token from oauth_accounts table for %s", email)
        return token
    
    logger.debug("No GitHub token found for user %s", email)
    return None
