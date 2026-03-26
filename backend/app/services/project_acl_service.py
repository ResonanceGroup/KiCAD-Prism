"""
Project-level Access Control Service.

Each project in the registry has:
  - visibility: "public" | "private" | "hidden"
  - A set of ProjectMembership rows (per-project roles: viewer / manager / admin)
  - A set of ProjectAccessRequest rows (pending/approved/denied)

Access-request auto-approval rules:
  - System "admin"    → always auto-approved as project admin on public/private projects
  - System "designer" → auto-approved as project viewer on PUBLIC projects (explicit membership
                        is created); requires manager approval on private projects
  - System "viewer"   → always requires manager/admin approval on any project

All roles require an explicit membership row to have access — there is no implicit access.
Hidden projects are invite-only; no access requests are accepted.
"""

from __future__ import annotations

import datetime
import logging
from typing import List, Optional

from sqlalchemy import select, delete
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import settings
from app.db.models import ProjectAccessRequest, ProjectInvite, ProjectMembership

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Role helpers
# ---------------------------------------------------------------------------

PROJECT_ROLES = ("viewer", "manager", "admin")


def _is_bootstrap_admin(email: str) -> bool:
    return email.strip().lower() in {e.strip().lower() for e in settings.BOOTSTRAP_ADMIN_USERS if e}


# ---------------------------------------------------------------------------
# Membership queries
# ---------------------------------------------------------------------------

async def get_membership(
    session: AsyncSession, project_id: str, user_email: str
) -> Optional[ProjectMembership]:
    email = user_email.strip().lower()
    result = await session.execute(
        select(ProjectMembership).where(
            ProjectMembership.project_id == project_id,
            ProjectMembership.user_email == email,
        )
    )
    return result.scalar_one_or_none()


async def list_members(session: AsyncSession, project_id: str) -> List[ProjectMembership]:
    result = await session.execute(
        select(ProjectMembership).where(ProjectMembership.project_id == project_id)
    )
    return list(result.scalars().all())


async def upsert_membership(
    session: AsyncSession,
    project_id: str,
    user_email: str,
    project_role: str,
    added_by: str,
) -> ProjectMembership:
    """Add or update a project membership row."""
    email = user_email.strip().lower()
    existing = await get_membership(session, project_id, email)
    if existing:
        existing.project_role = project_role
        existing.added_by = added_by.strip().lower()
        existing.added_at = datetime.datetime.utcnow()
        await session.commit()
        return existing

    membership = ProjectMembership(
        project_id=project_id,
        user_email=email,
        project_role=project_role,
        added_by=added_by.strip().lower(),
        added_at=datetime.datetime.utcnow(),
    )
    session.add(membership)
    await session.commit()
    await session.refresh(membership)
    return membership


async def remove_membership(
    session: AsyncSession, project_id: str, user_email: str
) -> bool:
    email = user_email.strip().lower()
    result = await session.execute(
        delete(ProjectMembership).where(
            ProjectMembership.project_id == project_id,
            ProjectMembership.user_email == email,
        )
    )
    await session.commit()
    return result.rowcount > 0  # type: ignore[return-value]


# ---------------------------------------------------------------------------
# Access-request queries
# ---------------------------------------------------------------------------

async def get_pending_request(
    session: AsyncSession, project_id: str, user_email: str
) -> Optional[ProjectAccessRequest]:
    email = user_email.strip().lower()
    result = await session.execute(
        select(ProjectAccessRequest).where(
            ProjectAccessRequest.project_id == project_id,
            ProjectAccessRequest.user_email == email,
            ProjectAccessRequest.status == "pending",
        )
    )
    return result.scalar_one_or_none()


async def list_access_requests(
    session: AsyncSession, project_id: str, status: str = "pending"
) -> List[ProjectAccessRequest]:
    result = await session.execute(
        select(ProjectAccessRequest).where(
            ProjectAccessRequest.project_id == project_id,
            ProjectAccessRequest.status == status,
        )
    )
    return list(result.scalars().all())


async def create_access_request(
    session: AsyncSession,
    project_id: str,
    user_email: str,
    requested_role: str,
) -> ProjectAccessRequest:
    email = user_email.strip().lower()
    # Clear any old denied/approved record so a fresh request can be made
    await session.execute(
        delete(ProjectAccessRequest).where(
            ProjectAccessRequest.project_id == project_id,
            ProjectAccessRequest.user_email == email,
            ProjectAccessRequest.status != "pending",
        )
    )
    req = ProjectAccessRequest(
        project_id=project_id,
        user_email=email,
        requested_role=requested_role,
        status="pending",
        requested_at=datetime.datetime.utcnow(),
    )
    session.add(req)
    await session.commit()
    await session.refresh(req)
    return req


async def resolve_access_request(
    session: AsyncSession,
    request_id: str,
    action: str,  # "approve" | "deny"
    reviewed_by: str,
) -> Optional[ProjectAccessRequest]:
    result = await session.execute(
        select(ProjectAccessRequest).where(ProjectAccessRequest.id == request_id)
    )
    req = result.scalar_one_or_none()
    if req is None:
        return None
    req.status = "approved" if action == "approve" else "denied"
    req.reviewed_by = reviewed_by.strip().lower()
    req.reviewed_at = datetime.datetime.utcnow()
    if action == "approve":
        await upsert_membership(
            session,
            project_id=req.project_id,
            user_email=req.user_email,
            project_role=req.requested_role,
            added_by=reviewed_by,
        )
    await session.commit()
    await session.refresh(req)
    return req


# ---------------------------------------------------------------------------
# Authorisation helpers used by API layer
# ---------------------------------------------------------------------------

async def resolve_effective_project_role(
    session: AsyncSession,
    project_id: str,
    user_email: str,
    visibility: str,
    system_role: str,
) -> Optional[str]:
    """Return the effective project-role for a user, or None if no access.

    Rules (evaluated top-down, first match wins):
    1. Bootstrap admin  → always "admin"
    2. System admin     → always "admin" (except hidden projects)
    3. Explicit approved membership row → return that role
    4. Otherwise        → None (no access)

    Note: designers are NOT implicitly granted access to public projects.
    They must go through /request-access, which auto-approves them and
    creates an explicit membership row.  The discover endpoint uses
    project visibility (not this function) to decide whether the project
    is *visible* to a designer in the listing.
    """
    email = user_email.strip().lower()

    if _is_bootstrap_admin(email):
        return "admin"

    if visibility == "hidden":
        # Hidden projects: only bootstrap admin (handled above) or explicit membership
        membership = await get_membership(session, project_id, email)
        if membership:
            return membership.project_role
        return None

    if system_role == "admin":
        return "admin"

    membership = await get_membership(session, project_id, email)
    if membership:
        return membership.project_role

    return None


async def can_manage_project(
    session: AsyncSession,
    project_id: str,
    user_email: str,
    visibility: str,
    system_role: str,
) -> bool:
    """Return True if the user has manager-or-above on this project."""
    role = await resolve_effective_project_role(
        session, project_id, user_email, visibility, system_role
    )
    return role in ("manager", "admin")


# ---------------------------------------------------------------------------
# Project Invites
# ---------------------------------------------------------------------------

async def create_project_invite(
    session: AsyncSession,
    project_id: str,
    invited_email: str,
    invited_role: str,
    invited_by: str,
    expires_days: int = 7,
) -> ProjectInvite:
    """Create a new invite, revoking any existing pending invite for the same user+project."""
    email = invited_email.strip().lower()
    # Revoke any existing pending invite so only one is active at a time
    result = await session.execute(
        select(ProjectInvite).where(
            ProjectInvite.project_id == project_id,
            ProjectInvite.invited_email == email,
            ProjectInvite.status == "pending",
        )
    )
    old = result.scalar_one_or_none()
    if old:
        old.status = "revoked"
        await session.commit()

    invite = ProjectInvite(
        project_id=project_id,
        invited_email=email,
        invited_role=invited_role,
        invited_by=invited_by.strip().lower(),
        expires_at=datetime.datetime.utcnow() + datetime.timedelta(days=expires_days),
    )
    session.add(invite)
    await session.commit()
    await session.refresh(invite)
    return invite


async def get_invite_by_token(
    session: AsyncSession, token: str
) -> Optional[ProjectInvite]:
    result = await session.execute(
        select(ProjectInvite).where(ProjectInvite.token == token)
    )
    return result.scalar_one_or_none()


async def list_pending_invites_for_user(
    session: AsyncSession, user_email: str
) -> List[ProjectInvite]:
    email = user_email.strip().lower()
    now = datetime.datetime.utcnow()
    result = await session.execute(
        select(ProjectInvite)
        .where(
            ProjectInvite.invited_email == email,
            ProjectInvite.status == "pending",
        )
        .order_by(ProjectInvite.created_at.desc())
    )
    invites = list(result.scalars().all())
    return [i for i in invites if i.expires_at is None or i.expires_at > now]


async def accept_project_invite(
    session: AsyncSession, token: str, accepting_email: str
) -> tuple:
    """Accept an invite by token.  Returns (membership, error_str)."""
    invite = await get_invite_by_token(session, token)
    if invite is None:
        return None, "Invite not found"
    if invite.status != "pending":
        return None, f"Invite is already {invite.status}"
    now = datetime.datetime.utcnow()
    if invite.expires_at and invite.expires_at < now:
        return None, "Invite has expired"
    membership = await upsert_membership(
        session,
        project_id=invite.project_id,
        user_email=accepting_email,
        project_role=invite.invited_role,
        added_by=invite.invited_by,
    )
    invite.status = "accepted"
    await session.commit()
    return membership, None


async def accept_project_invite_by_id(
    session: AsyncSession, invite_id: str, accepting_email: str
) -> tuple:
    """Accept an invite by invite ID.  Returns (membership, error_str)."""
    result = await session.execute(
        select(ProjectInvite).where(ProjectInvite.id == invite_id)
    )
    invite = result.scalar_one_or_none()
    if invite is None or invite.invited_email != accepting_email.strip().lower():
        return None, "Invite not found"
    if invite.status != "pending":
        return None, f"Invite is already {invite.status}"
    now = datetime.datetime.utcnow()
    if invite.expires_at and invite.expires_at < now:
        return None, "Invite has expired"
    membership = await upsert_membership(
        session,
        project_id=invite.project_id,
        user_email=accepting_email,
        project_role=invite.invited_role,
        added_by=invite.invited_by,
    )
    invite.status = "accepted"
    await session.commit()
    return membership, None


async def decline_project_invite(
    session: AsyncSession, invite_id: str, user_email: str
) -> bool:
    result = await session.execute(
        select(ProjectInvite).where(ProjectInvite.id == invite_id)
    )
    invite = result.scalar_one_or_none()
    if invite is None or invite.invited_email != user_email.strip().lower():
        return False
    if invite.status != "pending":
        return False
    invite.status = "declined"
    await session.commit()
    return True
