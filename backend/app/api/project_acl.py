"""
Project ACL API — project creation (upload/ZIP), visibility, membership, access requests.

All routes are prefixed with /api/projects by the router mounting in main.py.
"""

from __future__ import annotations

import io
import os
import shutil
import tempfile
import uuid
import zipfile
from datetime import datetime
from typing import List, Optional

from fastapi import APIRouter, Depends, File, Form, HTTPException, Request, UploadFile
from pydantic import BaseModel
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.security import (
    AuthenticatedUser,
    require_designer,
    require_viewer,
)
from app.db.db import get_async_session
from app.services import project_acl_service, project_service
from app.services.project_service import (
    VISIBILITY_HIDDEN,
    VISIBILITY_PRIVATE,
    VISIBILITY_PUBLIC,
    VISIBILITY_VALUES,
)

router = APIRouter()

KICAD_EXTENSIONS = {
    ".kicad_pro", ".kicad_sch", ".kicad_pcb",
    ".kicad_mod", ".kicad_sym", ".kicad_wks",
    ".kicad_jobset",
    ".png", ".jpg", ".jpeg", ".webp", ".svg",
    ".pdf", ".step", ".stp", ".glb", ".gltf",
    ".gbr", ".drl", ".excellon",
    ".csv", ".bom",
    ".md", ".txt", ".json",
}
MAX_UPLOAD_BYTES = 512 * 1024 * 1024  # 512 MB


# ---------------------------------------------------------------------------
# Pydantic response/request models
# ---------------------------------------------------------------------------

class ProjectMemberResponse(BaseModel):
    project_id: str
    user_email: str
    project_role: str
    added_by: str
    added_at: str


class AddMemberRequest(BaseModel):
    user_email: str
    project_role: str = "viewer"


class AccessRequestResponse(BaseModel):
    id: str
    project_id: str
    user_email: str
    requested_role: str
    status: str
    requested_at: str
    reviewed_by: Optional[str] = None
    reviewed_at: Optional[str] = None


class RequestAccessBody(BaseModel):
    requested_role: str = "viewer"


class VisibilityUpdate(BaseModel):
    visibility: str


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _membership_to_response(m) -> ProjectMemberResponse:
    return ProjectMemberResponse(
        project_id=m.project_id,
        user_email=m.user_email,
        project_role=m.project_role,
        added_by=m.added_by,
        added_at=m.added_at.isoformat() if m.added_at else "",
    )


def _req_to_response(r) -> AccessRequestResponse:
    return AccessRequestResponse(
        id=r.id,
        project_id=r.project_id,
        user_email=r.user_email,
        requested_role=r.requested_role,
        status=r.status,
        requested_at=r.requested_at.isoformat() if r.requested_at else "",
        reviewed_by=r.reviewed_by,
        reviewed_at=r.reviewed_at.isoformat() if r.reviewed_at else None,
    )


def _get_project_or_404(project_id: str) -> project_service.Project:
    project = project_service.get_project_by_id(project_id)
    if project is None:
        raise HTTPException(status_code=404, detail="Project not found")
    return project


async def _assert_project_admin(
    session: AsyncSession,
    project: project_service.Project,
    user: AuthenticatedUser,
) -> None:
    role = await project_acl_service.resolve_effective_project_role(
        session, project.id, user.email, project.visibility, user.role
    )
    if role != "admin":
        raise HTTPException(status_code=403, detail="Project admin role required")


async def _assert_project_manager(
    session: AsyncSession,
    project: project_service.Project,
    user: AuthenticatedUser,
) -> None:
    ok = await project_acl_service.can_manage_project(
        session, project.id, user.email, project.visibility, user.role
    )
    if not ok:
        raise HTTPException(status_code=403, detail="Project manager role required")


# ---------------------------------------------------------------------------
# Project creation via file upload
# ---------------------------------------------------------------------------

@router.post("/create")
async def create_project_from_upload(
    name: str = Form(...),
    description: str = Form(""),
    visibility: str = Form("public"),
    files: List[UploadFile] = File(default=[]),
    zip_file: Optional[UploadFile] = File(default=None),
    user: AuthenticatedUser = Depends(require_designer),
    session: AsyncSession = Depends(get_async_session),
):
    """Create a new project from uploaded KiCAD files or a ZIP archive.

    - Pass individual files via the ``files`` field, OR
    - Pass a single ZIP via ``zip_file`` (the ZIP is extracted into the project folder).
    - ``visibility`` must be one of: **public**, **private**, **hidden**.
    """
    if visibility not in VISIBILITY_VALUES:
        raise HTTPException(status_code=400, detail=f"visibility must be one of {list(VISIBILITY_VALUES)}")

    safe_name = "".join(c if c.isalnum() or c in "-_ " else "_" for c in name).strip()
    if not safe_name:
        raise HTTPException(status_code=400, detail="Invalid project name")

    project_id = str(uuid.uuid4())
    project_dir = os.path.join(project_service.PROJECTS_ROOT, "type1", project_id)
    os.makedirs(project_dir, exist_ok=True)

    try:
        if zip_file is not None:
            # --- ZIP path ---
            zip_bytes = await zip_file.read()
            if len(zip_bytes) > MAX_UPLOAD_BYTES:
                raise HTTPException(status_code=413, detail="ZIP file exceeds 512 MB limit")
            with zipfile.ZipFile(io.BytesIO(zip_bytes)) as zf:
                # Detect common root prefix (so a zipped folder extracts cleanly)
                names = zf.namelist()
                prefix = ""
                if names:
                    parts = names[0].split("/")
                    candidate = parts[0] + "/" if len(parts) > 1 else ""
                    if candidate and all(n.startswith(candidate) for n in names):
                        prefix = candidate
                for member in zf.infolist():
                    rel = member.filename[len(prefix):]
                    if not rel or rel.endswith("/"):
                        continue
                    target = os.path.normpath(os.path.join(project_dir, rel))
                    # Path traversal guard
                    if not target.startswith(os.path.abspath(project_dir)):
                        continue
                    os.makedirs(os.path.dirname(target), exist_ok=True)
                    with zf.open(member) as src, open(target, "wb") as dst:
                        shutil.copyfileobj(src, dst)
        elif files:
            # --- Individual files path ---
            total = 0
            for f in files:
                data = await f.read()
                total += len(data)
                if total > MAX_UPLOAD_BYTES:
                    raise HTTPException(status_code=413, detail="Total upload exceeds 512 MB limit")
                filename = os.path.basename(f.filename or "unnamed")
                target = os.path.join(project_dir, filename)
                with open(target, "wb") as fh:
                    fh.write(data)
        else:
            # No files — create an empty project directory (user will upload files later)
            pass

        # Initialise a bare git repo so history tracking works
        try:
            import subprocess
            subprocess.run(["git", "init", project_dir], check=True, capture_output=True)
            subprocess.run(
                ["git", "config", "user.email", "prism@localhost"],
                cwd=project_dir, check=False, capture_output=True,
            )
            subprocess.run(
                ["git", "config", "user.name", "KiCAD Prism"],
                cwd=project_dir, check=False, capture_output=True,
            )
            subprocess.run(
                ["git", "add", "-A"],
                cwd=project_dir, check=False, capture_output=True,
            )
            subprocess.run(
                ["git", "commit", "-m", "Initial upload via KiCAD Prism"],
                cwd=project_dir, check=False, capture_output=True,
            )
        except Exception:
            pass  # git init failure is non-fatal

        project_service.register_project(
            project_id=project_id,
            name=safe_name,
            path=project_dir,
            repo_url="",
            description=description or f"Project {safe_name}",
            visibility=visibility,
        )

        # Grant the creator project-admin membership
        await project_acl_service.upsert_membership(
            session,
            project_id=project_id,
            user_email=user.email,
            project_role="admin",
            added_by=user.email,
        )

        return {"id": project_id, "name": safe_name, "visibility": visibility}

    except HTTPException:
        shutil.rmtree(project_dir, ignore_errors=True)
        raise
    except Exception as exc:
        shutil.rmtree(project_dir, ignore_errors=True)
        raise HTTPException(status_code=500, detail=f"Failed to create project: {exc}") from exc


# ---------------------------------------------------------------------------
# Visibility update
# ---------------------------------------------------------------------------

@router.put("/{project_id}/visibility")
async def set_project_visibility(
    project_id: str,
    body: VisibilityUpdate,
    user: AuthenticatedUser = Depends(require_viewer),
    session: AsyncSession = Depends(get_async_session),
):
    project = _get_project_or_404(project_id)
    await _assert_project_admin(session, project, user)
    if body.visibility not in VISIBILITY_VALUES:
        raise HTTPException(status_code=400, detail=f"visibility must be one of {list(VISIBILITY_VALUES)}")
    project_service.update_project_visibility(project_id, body.visibility)
    return {"id": project_id, "visibility": body.visibility}


# ---------------------------------------------------------------------------
# Discover / list projects (respects visibility + membership)
# ---------------------------------------------------------------------------

@router.get("/discover")
async def discover_projects(
    user: AuthenticatedUser = Depends(require_viewer),
    session: AsyncSession = Depends(get_async_session),
):
    """Return all public and private projects the current user can see.

    Hidden projects are excluded unless the user is the bootstrap admin.
    """
    all_projects = project_service.get_registered_projects()
    is_bootstrap = project_acl_service._is_bootstrap_admin(user.email)
    result = []
    for p in all_projects:
        if p.visibility == VISIBILITY_HIDDEN and not is_bootstrap:
            continue
        has_access = await project_acl_service.resolve_effective_project_role(
            session, p.id, user.email, p.visibility, user.role
        )
        membership = await project_acl_service.get_membership(session, p.id, user.email)
        pending = await project_acl_service.get_pending_request(session, p.id, user.email)
        result.append({
            "id": p.id,
            "name": p.display_name or p.name,
            "description": p.description,
            "visibility": p.visibility,
            "thumbnail_url": p.thumbnail_url,
            "last_modified": p.last_modified,
            "my_role": has_access,
            "my_membership_role": membership.project_role if membership else None,
            "pending_request": pending.requested_role if pending else None,
        })
    return result


# ---------------------------------------------------------------------------
# Membership management
# ---------------------------------------------------------------------------

@router.get("/{project_id}/members", response_model=List[ProjectMemberResponse])
async def list_project_members(
    project_id: str,
    user: AuthenticatedUser = Depends(require_viewer),
    session: AsyncSession = Depends(get_async_session),
):
    project = _get_project_or_404(project_id)
    role = await project_acl_service.resolve_effective_project_role(
        session, project.id, user.email, project.visibility, user.role
    )
    if not role:
        raise HTTPException(status_code=403, detail="Access denied")
    members = await project_acl_service.list_members(session, project_id)
    return [_membership_to_response(m) for m in members]


@router.post("/{project_id}/members")
async def add_project_member(
    project_id: str,
    body: AddMemberRequest,
    user: AuthenticatedUser = Depends(require_viewer),
    session: AsyncSession = Depends(get_async_session),
):
    """Add or update a member's project role.  Requires project-manager or above."""
    project = _get_project_or_404(project_id)
    await _assert_project_manager(session, project, user)
    if body.project_role not in ("viewer", "manager", "admin"):
        raise HTTPException(status_code=400, detail="project_role must be viewer/manager/admin")
    membership = await project_acl_service.upsert_membership(
        session,
        project_id=project_id,
        user_email=body.user_email,
        project_role=body.project_role,
        added_by=user.email,
    )
    return _membership_to_response(membership)


@router.delete("/{project_id}/members/{email}")
async def remove_project_member(
    project_id: str,
    email: str,
    user: AuthenticatedUser = Depends(require_viewer),
    session: AsyncSession = Depends(get_async_session),
):
    project = _get_project_or_404(project_id)
    await _assert_project_manager(session, project, user)
    removed = await project_acl_service.remove_membership(session, project_id, email)
    if not removed:
        raise HTTPException(status_code=404, detail="Member not found")
    return {"removed": email}


@router.post("/{project_id}/join")
async def self_join_project(
    project_id: str,
    user: AuthenticatedUser = Depends(require_viewer),
    session: AsyncSession = Depends(get_async_session),
):
    """System manager/admin can self-join public projects; system admin can also join private ones.
    Viewers must request access instead.
    """
    project = _get_project_or_404(project_id)

    if project.visibility == VISIBILITY_HIDDEN:
        raise HTTPException(status_code=403, detail="Hidden projects are invite-only")

    if user.role not in ("designer", "admin"):
        raise HTTPException(status_code=403, detail="Only managers and admins can self-join projects")

    if project.visibility == VISIBILITY_PRIVATE and user.role != "admin":
        raise HTTPException(status_code=403, detail="Managers must request access to private projects")

    membership = await project_acl_service.upsert_membership(
        session,
        project_id=project_id,
        user_email=user.email,
        project_role="manager" if user.role == "designer" else "admin",
        added_by=user.email,
    )
    return _membership_to_response(membership)


# ---------------------------------------------------------------------------
# Access requests
# ---------------------------------------------------------------------------

@router.post("/{project_id}/request-access")
async def request_project_access(
    project_id: str,
    body: RequestAccessBody,
    request: Request,
    user: AuthenticatedUser = Depends(require_viewer),
    session: AsyncSession = Depends(get_async_session),
):
    project = _get_project_or_404(project_id)

    if project.visibility == VISIBILITY_HIDDEN:
        raise HTTPException(status_code=403, detail="Hidden projects are invite-only")

    existing = await project_acl_service.get_membership(session, project_id, user.email)
    if existing:
        raise HTTPException(status_code=400, detail="You are already a member of this project")

    if body.requested_role not in ("viewer", "manager"):
        raise HTTPException(status_code=400, detail="requested_role must be viewer or manager")

    req = await project_acl_service.create_access_request(
        session, project_id, user.email, body.requested_role
    )

    # Notify project managers and admins
    try:
        from app.auth import _send_smtp_email
        members = await project_acl_service.list_members(session, project_id)
        notify_emails = [m.user_email for m in members if m.project_role in ("manager", "admin")]
        project_name = project.display_name or project.name
        for email in notify_emails:
            await _send_smtp_email(
                to=email,
                subject=f"KiCAD Prism — Access request for {project_name}",
                body_html=(
                    f"<p><strong>{user.email}</strong> has requested <em>{body.requested_role}</em> "
                    f"access to project <strong>{project_name}</strong>.</p>"
                    "<p>Sign in and open the project settings to approve or deny this request.</p>"
                ),
            )
    except Exception:
        pass  # notification failure is non-fatal

    return _req_to_response(req)


@router.get("/{project_id}/access-requests", response_model=List[AccessRequestResponse])
async def list_project_access_requests(
    project_id: str,
    user: AuthenticatedUser = Depends(require_viewer),
    session: AsyncSession = Depends(get_async_session),
):
    project = _get_project_or_404(project_id)
    await _assert_project_manager(session, project, user)
    requests = await project_acl_service.list_access_requests(session, project_id)
    return [_req_to_response(r) for r in requests]


@router.post("/{project_id}/access-requests/{request_id}/approve")
async def approve_access_request(
    project_id: str,
    request_id: str,
    user: AuthenticatedUser = Depends(require_viewer),
    session: AsyncSession = Depends(get_async_session),
):
    project = _get_project_or_404(project_id)
    await _assert_project_manager(session, project, user)
    req = await project_acl_service.resolve_access_request(session, request_id, "approve", user.email)
    if not req:
        raise HTTPException(status_code=404, detail="Access request not found")
    # Notify the requester
    try:
        from app.auth import _send_smtp_email
        project_name = project.display_name or project.name
        await _send_smtp_email(
            to=req.user_email,
            subject=f"Your access request for {project_name} has been approved",
            body_html=(
                f"<p>Your request to join <strong>{project_name}</strong> "
                f"as <em>{req.requested_role}</em> has been approved.</p>"
                "<p>You can now access the project in KiCAD Prism.</p>"
            ),
        )
    except Exception:
        pass
    return _req_to_response(req)


@router.post("/{project_id}/access-requests/{request_id}/deny")
async def deny_access_request(
    project_id: str,
    request_id: str,
    user: AuthenticatedUser = Depends(require_viewer),
    session: AsyncSession = Depends(get_async_session),
):
    project = _get_project_or_404(project_id)
    await _assert_project_manager(session, project, user)
    req = await project_acl_service.resolve_access_request(session, request_id, "deny", user.email)
    if not req:
        raise HTTPException(status_code=404, detail="Access request not found")
    try:
        from app.auth import _send_smtp_email
        project_name = project.display_name or project.name
        await _send_smtp_email(
            to=req.user_email,
            subject=f"Your access request for {project_name}",
            body_html=(
                f"<p>Your request to join <strong>{project_name}</strong> "
                "has been reviewed and was not approved at this time.</p>"
                "<p>Please contact the project administrator for more information.</p>"
            ),
        )
    except Exception:
        pass
    return _req_to_response(req)
