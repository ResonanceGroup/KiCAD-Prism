import uuid

from fastapi import Depends, HTTPException, Request
from jose import JWTError, jwt
from pydantic import BaseModel
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import settings
from app.core.roles import Role, normalize_role, role_meets_minimum
from app.core.session import SESSION_COOKIE_NAME, decode_session_token
from app.db.db import get_async_session
from app.db.models import User
from app.services import access_service

# Cookie name used by fastapi-users CookieTransport (default value).
_FU_COOKIE_NAME = "fastapiusers_auth"
# Audience claim set by fastapi-users JWTStrategy (default value).
_FU_JWT_AUDIENCE = ["fastapi-users:auth"]


class AuthenticatedUser(BaseModel):
    email: str
    name: str
    picture: str = ""
    role: Role


def guest_user() -> AuthenticatedUser:
    return AuthenticatedUser(email="guest@local", name="Guest User", picture="", role="viewer")


def _resolve_allowed_user_role(email: str) -> Role | None:
    role = access_service.resolve_user_role(email)
    if role is None:
        return None
    return normalize_role(role)


async def _get_user_from_fu_jwt(token: str, session: AsyncSession) -> User | None:
    """Decode a fastapi-users JWT cookie and return the matching User row.

    Returns ``None`` when the token is missing, expired, or malformed, or when
    no user with the embedded UUID exists in the database.
    """
    if not settings.SESSION_SECRET:
        return None
    try:
        payload = jwt.decode(
            token,
            settings.SESSION_SECRET,
            algorithms=["HS256"],
            audience=_FU_JWT_AUDIENCE,
        )
        user_id_str = payload.get("sub")
        if not user_id_str:
            return None
        user_id = uuid.UUID(user_id_str)
    except (JWTError, ValueError):
        return None

    stmt = select(User).where(User.id == user_id)
    result = await session.execute(stmt)
    return result.scalar_one_or_none()


async def get_current_user(
    request: Request,
    session: AsyncSession = Depends(get_async_session),
) -> AuthenticatedUser:
    if not settings.AUTH_ENABLED:
        return guest_user()

    # 1. Try the legacy HMAC session cookie (set by Google OAuth and
    #    fastapi-users on_after_login).
    token = request.cookies.get(SESSION_COOKIE_NAME)
    payload = decode_session_token(token or "")
    if payload:
        role = _resolve_allowed_user_role(payload["email"])
        if role:
            return AuthenticatedUser(
                email=payload["email"],
                name=payload["name"],
                picture=payload["picture"],
                role=role,
            )
        # Authenticated identity but no RBAC role assigned yet.
        raise HTTPException(
            status_code=403,
            detail="Access denied. No role assignment found for your account.",
        )

    # 2. Fall back to the fastapi-users JWT cookie so that clients which hold
    #    a valid fastapi-users session (but whose custom HMAC cookie has lapsed)
    #    remain authenticated.
    jwt_token = request.cookies.get(_FU_COOKIE_NAME)
    if jwt_token:
        user = await _get_user_from_fu_jwt(jwt_token, session)
        if user:
            role = _resolve_allowed_user_role(user.email)
            if role:
                return AuthenticatedUser(
                    email=user.email,
                    name=user.email.split("@")[0],
                    picture="",
                    role=role,
                )
            # Authenticated via JWT but no RBAC role assigned yet.
            raise HTTPException(
                status_code=403,
                detail="Access denied. No role assignment found for your account.",
            )

    raise HTTPException(status_code=401, detail="Authentication required")


async def require_viewer(user: AuthenticatedUser = Depends(get_current_user)) -> AuthenticatedUser:
    return user


async def require_designer(user: AuthenticatedUser = Depends(get_current_user)) -> AuthenticatedUser:
    if not role_meets_minimum(user.role, "designer"):
        raise HTTPException(status_code=403, detail="Designer role required")
    return user


async def require_admin(user: AuthenticatedUser = Depends(get_current_user)) -> AuthenticatedUser:
    if not role_meets_minimum(user.role, "admin"):
        raise HTTPException(status_code=403, detail="Admin role required")
    return user
