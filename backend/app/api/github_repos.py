"""GitHub repository browsing and cloning endpoints.

All routes are prefixed with /api/github by the router mounting in main.py.

All repository operations use the GitHub App installation token rather than
per-user OAuth tokens.  This means every designer-or-above user can browse
and clone repositories that the GitHub App has been installed on, without
needing to have signed in with GitHub themselves.

Flow
----
1.  ``GET  /api/github/repos``        — list repositories accessible to the
    GitHub App installation (filtered to ``GITHUB_ORG_LOGIN`` when set).
2.  ``POST /api/github/repos/clone``  — clone a GitHub repository onto the
    server using the App token, register it as a KiCAD Prism project, and
    add the requesting user as a project member with *manager* role.
"""

from __future__ import annotations

import logging
import os
import shutil
import subprocess
import uuid
from typing import Optional

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import settings
from app.core.security import AuthenticatedUser, require_designer
from app.db.db import get_async_session
from app.github_app import get_app_installation_client, is_app_configured
from app.services import project_acl_service, project_service
from app.services.project_service import (
    VISIBILITY_HIDDEN,
    VISIBILITY_PUBLIC,
    VISIBILITY_VALUES,
)

router = APIRouter()
logger = logging.getLogger(__name__)

SUBPROCESS_TIMEOUT = 120  # seconds for git clone
MAX_CLONE_ERROR_LENGTH = 500  # characters of git stderr to include in error responses


# ---------------------------------------------------------------------------
# Request / response models
# ---------------------------------------------------------------------------

class CloneRequest(BaseModel):
    clone_url: str   # HTTPS clone URL, e.g. https://github.com/org/repo.git
    name: str        # Display name for the project on the server
    description: str = ""
    visibility: str = VISIBILITY_PUBLIC  # public / private (hidden requires admin)


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _inject_app_token_into_url(clone_url: str, token: str) -> str:
    """Return *clone_url* with the GitHub App installation token embedded.

    GitHub App installation tokens use the ``x-access-token`` username format::

        https://x-access-token:{token}@github.com/org/repo.git
    """
    if clone_url.startswith("https://"):
        return clone_url.replace("https://", f"https://x-access-token:{token}@", 1)
    return clone_url


def _require_app_configured() -> None:
    """Raise HTTP 503 when the GitHub App is not configured."""
    if not is_app_configured():
        raise HTTPException(
            status_code=503,
            detail=(
                "GitHub App integration is not configured on this server. "
                "Ask your admin to set GITHUB_APP_ID, GITHUB_APP_PRIVATE_KEY, "
                "and GITHUB_APP_INSTALLATION_ID."
            ),
        )


# ---------------------------------------------------------------------------
# Endpoints
# ---------------------------------------------------------------------------

@router.get("/repos")
async def list_github_repos(
    auth_user: AuthenticatedUser = Depends(require_designer),
):
    """Return GitHub repositories accessible to the GitHub App installation.

    When ``GITHUB_ORG_LOGIN`` is set the list is scoped to that organization;
    otherwise all repositories accessible to the installation are returned.
    """
    _require_app_configured()

    try:
        async with await get_app_installation_client() as client:
            org = settings.GITHUB_ORG_LOGIN
            if org:
                resp = await client.get(
                    f"/orgs/{org}/repos",
                    params={"per_page": 100, "sort": "updated", "type": "all"},
                )
            else:
                resp = await client.get(
                    "/installation/repositories",
                    params={"per_page": 100},
                )

            if resp.status_code == 401:
                raise HTTPException(
                    status_code=401,
                    detail="GitHub App token is invalid or expired",
                )
            if resp.status_code == 403:
                raise HTTPException(
                    status_code=403,
                    detail="GitHub App lacks required permissions",
                )
            resp.raise_for_status()
            raw = resp.json()
            # /installation/repositories wraps the list under a key
            repos = raw.get("repositories", raw) if isinstance(raw, dict) else raw

    except HTTPException:
        raise
    except Exception as exc:
        logger.error("Failed to list GitHub repos via App: %s", exc)
        raise HTTPException(status_code=502, detail=f"GitHub API error: {exc}")

    # Mark repos that are already registered on this server
    registered_projects = project_service.get_registered_projects()
    cloned_urls = {
        (p.github_source_url or "").rstrip("/").lower()
        for p in registered_projects
        if p.github_source_url
    }

    result = []
    for repo in repos:
        clone_url = repo.get("clone_url") or repo.get("html_url", "")
        result.append({
            "id": repo.get("id"),
            "name": repo.get("name"),
            "full_name": repo.get("full_name"),
            "description": repo.get("description") or "",
            "clone_url": clone_url,
            "html_url": repo.get("html_url"),
            "private": repo.get("private", False),
            "updated_at": repo.get("updated_at"),
            "already_cloned": clone_url.rstrip("/").lower() in cloned_urls,
        })

    return result


@router.post("/repos/clone")
async def clone_github_repo(
    body: CloneRequest,
    auth_user: AuthenticatedUser = Depends(require_designer),
    session: AsyncSession = Depends(get_async_session),
):
    """Clone a GitHub repository onto the server and register it as a project.

    - The requesting user is added as a *manager* of the new project.
    - The clone is read-only from GitHub (``origin`` remote is removed after
      cloning to prevent accidental pushes).
    - Visibility is enforced: only admins may create hidden projects.
    """
    _require_app_configured()

    if body.visibility not in VISIBILITY_VALUES:
        raise HTTPException(
            status_code=400,
            detail=f"visibility must be one of {list(VISIBILITY_VALUES)}",
        )

    if body.visibility == VISIBILITY_HIDDEN and auth_user.role not in ("admin",):
        raise HTTPException(
            status_code=403, detail="Only admins can create hidden projects"
        )

    safe_name = "".join(c if c.isalnum() or c in "-_ " else "_" for c in body.name).strip()
    if not safe_name:
        raise HTTPException(status_code=400, detail="Invalid project name")

    # Fetch the installation token once up-front (cached, so cheap)
    try:
        from app.github_app import get_installation_token
        token = await get_installation_token()
    except ValueError as exc:
        raise HTTPException(status_code=503, detail=str(exc))

    project_id = str(uuid.uuid4())
    project_dir = os.path.join(project_service.PROJECTS_ROOT, "type1", project_id)
    os.makedirs(project_dir, exist_ok=True)

    authenticated_url = _inject_app_token_into_url(body.clone_url, token)

    try:
        result = subprocess.run(
            ["git", "clone", "--depth", "1", authenticated_url, project_dir],
            capture_output=True,
            text=True,
            timeout=SUBPROCESS_TIMEOUT,
        )
        if result.returncode != 0:
            safe_stderr = result.stderr.replace(token, "***")
            logger.error("git clone failed: %s", safe_stderr)
            raise HTTPException(
                status_code=500,
                detail=f"Failed to clone repository: {safe_stderr[:MAX_CLONE_ERROR_LENGTH]}",
            )
    except subprocess.TimeoutExpired:
        shutil.rmtree(project_dir, ignore_errors=True)
        raise HTTPException(
            status_code=504, detail="Clone timed out (repository may be too large)"
        )
    except HTTPException:
        shutil.rmtree(project_dir, ignore_errors=True)
        raise
    except Exception as exc:
        shutil.rmtree(project_dir, ignore_errors=True)
        raise HTTPException(status_code=500, detail=f"Clone error: {exc}") from exc

    # Remove the remote to prevent accidental pushes
    try:
        subprocess.run(
            ["git", "remote", "remove", "origin"],
            cwd=project_dir,
            capture_output=True,
            timeout=10,
        )
    except Exception:
        pass  # Non-fatal

    project_service.register_project(
        project_id=project_id,
        name=safe_name,
        path=project_dir,
        repo_url=body.clone_url,
        description=body.description or f"Cloned from {body.clone_url}",
        visibility=body.visibility,
        github_source_url=body.clone_url,
    )

    # Add the cloning user as project manager
    await project_acl_service.upsert_membership(
        session,
        project_id=project_id,
        user_email=auth_user.email,
        project_role="manager",
        added_by=auth_user.email,
    )

    return {
        "id": project_id,
        "name": safe_name,
        "visibility": body.visibility,
        "github_source_url": body.clone_url,
    }

