"""
Project-level Access Control Service.

Each project in the registry has:
  - visibility: "public" | "private" | "hidden"
  - A set of ProjectMembership rows (per-project roles: viewer / manager / admin)
  - A set of ProjectAccessRequest rows (pending/approved/denied)

System-level role mapping:
  - System "viewer"   → can request access to public/private projects; invited-only otherwise
  - System "designer" → treated as "manager"; can self-join public projects
  - System "admin"    → can self-join public or private projects; full control

Hidden projects do not appear in any listing except to the bootstrap admin.
"""

from __future__ import annotations

import datetime
import logging
from typing import List, Optional

from sqlalchemy import select, delete
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import settings
from app.db.models import ProjectAccessRequest, ProjectMembership

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
    1. Bootstrap admin → always "admin"
    2. System admin    → always "admin" (except hidden projects where only bootstrap admin applies)
    3. Explicit membership row → return that role
    4. Public project + system designer/admin → implicit "viewer" (no membership needed)
    5. Otherwise → None (no access)
    """
    email = user_email.strip().lower()

    if _is_bootstrap_admin(email):
        return "admin"

    if visibility == "hidden":
        # Hidden projects: only bootstrap admin (handled above)
        membership = await get_membership(session, project_id, email)
        return membership.project_role if membership else None

    if system_role == "admin":
        return "admin"

    membership = await get_membership(session, project_id, email)
    if membership:
        return membership.project_role

    if visibility == "public":
        return "viewer"

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
