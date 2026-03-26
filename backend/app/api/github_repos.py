"""GitHub repository browsing and cloning endpoints.

All routes are prefixed with /api/github by the router mounting in main.py.

Flow
----
1.  ``GET  /api/github/repos``        — list repositories the authenticated user
    can access via their stored GitHub OAuth token.  Requires the user to have
    signed in with GitHub (or to be a bootstrap admin with a server-level token
    configured via GITHUB_TOKEN).
2.  ``POST /api/github/repos/clone``  — clone a GitHub repository onto the
    server, register it as a KiCAD Prism project, and add the requesting user
    as a project member with *manager* role.
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

from app.auth import get_current_user_with_github_token
from app.core.config import settings
from app.core.security import AuthenticatedUser, require_designer
from app.db.db import get_async_session
from app.db.models import User
from app.github import get_github_client
from app.services import project_acl_service, project_service
from app.services.project_service import (
    VISIBILITY_HIDDEN,
    VISIBILITY_PRIVATE,
    VISIBILITY_PUBLIC,
    VISIBILITY_VALUES,
)

router = APIRouter()
logger = logging.getLogger(__name__)

SUBPROCESS_TIMEOUT = 120  # seconds
MAX_CLONE_ERROR_MESSAGE_LENGTH = 500  # characters to include from git stderr in error responses


# ---------------------------------------------------------------------------
# Request / response models
# ---------------------------------------------------------------------------

class CloneRequest(BaseModel):
    clone_url: str  # HTTPS clone URL, e.g. https://github.com/org/repo.git
    name: str       # Display name for the project on the server
    description: str = ""
    visibility: str = VISIBILITY_PUBLIC  # public / private (hidden requires admin)


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _get_effective_github_token(user: User, user_token: Optional[str]) -> Optional[str]:
    """Return the best available GitHub token for the given user.

    Priority:
    1. The user's own decrypted OAuth token (only present when they signed in via GitHub).
    2. The server-level GITHUB_TOKEN from environment (useful for bootstrap admins
       and email-only users when an org-level PAT is configured by the server admin).
    """
    if user_token:
        return user_token
    if settings.GITHUB_TOKEN:
        return settings.GITHUB_TOKEN
    return None


def _inject_token_into_url(clone_url: str, token: str) -> str:
    """Return *clone_url* with the token embedded for authenticated HTTPS cloning."""
    if clone_url.startswith("https://"):
        return clone_url.replace("https://", f"https://{token}@", 1)
    return clone_url


# ---------------------------------------------------------------------------
# Endpoints
# ---------------------------------------------------------------------------

@router.get("/repos")
async def list_github_repos(
    user_and_token: tuple = Depends(get_current_user_with_github_token),
    _: AuthenticatedUser = Depends(require_designer),
):
    """Return GitHub repositories visible to the authenticated user.

    Uses the user's OAuth token (preferred) or the server-level GITHUB_TOKEN.
    Returns repositories from the configured org (GITHUB_ORG_LOGIN) when set,
    otherwise returns all repositories accessible to the user.
    """
    user, user_token = user_and_token
    token = _get_effective_github_token(user, user_token)

    if not token:
        raise HTTPException(
            status_code=400,
            detail=(
                "No GitHub token available. Sign in with GitHub or ask your server "
                "admin to configure GITHUB_TOKEN."
            ),
        )

    try:
        async with await get_github_client(token) as client:
            org = settings.GITHUB_ORG_LOGIN
            if org:
                # List repos the OAuth app / PAT can see within the org
                resp = await client.get(
                    f"/orgs/{org}/repos",
                    params={"per_page": 100, "sort": "updated", "type": "all"},
                )
            else:
                # Fall back to listing all repos accessible to the authenticated user
                resp = await client.get(
                    "/user/repos",
                    params={"per_page": 100, "sort": "updated", "affiliation": "owner,collaborator,organization_member"},
                )

            if resp.status_code == 401:
                raise HTTPException(status_code=401, detail="GitHub token is invalid or expired")
            if resp.status_code == 403:
                raise HTTPException(status_code=403, detail="GitHub token lacks required permissions")
            resp.raise_for_status()
            repos = resp.json()
    except HTTPException:
        raise
    except Exception as exc:
        logger.error("Failed to list GitHub repos: %s", exc)
        raise HTTPException(status_code=502, detail=f"GitHub API error: {exc}")

    # Determine which repos are already registered on the server
    registered_projects = project_service.get_registered_projects()
    cloned_urls = {
        (p.github_source_url or "").rstrip("/").lower()
        for p in registered_projects
        if p.github_source_url
    }

    result = []
    for repo in repos:
        clone_url = repo.get("clone_url") or repo.get("html_url", "")
        already_cloned = clone_url.rstrip("/").lower() in cloned_urls
        result.append({
            "id": repo.get("id"),
            "name": repo.get("name"),
            "full_name": repo.get("full_name"),
            "description": repo.get("description") or "",
            "clone_url": clone_url,
            "html_url": repo.get("html_url"),
            "private": repo.get("private", False),
            "updated_at": repo.get("updated_at"),
            "already_cloned": already_cloned,
        })

    return result


@router.post("/repos/clone")
async def clone_github_repo(
    body: CloneRequest,
    user_and_token: tuple = Depends(get_current_user_with_github_token),
    designer_user: AuthenticatedUser = Depends(require_designer),
    session: AsyncSession = Depends(get_async_session),
):
    """Clone a GitHub repository onto the server and register it as a project.

    - The requesting user is added as a *manager* of the new project.
    - The project is read-only from GitHub (no push access is configured).
    - Visibility is enforced: only admins may create hidden projects.
    """
    user, user_token = user_and_token
    # Use designer_user for role checks (it's the same user, just a different dependency result)
    auth_user = designer_user

    if body.visibility not in VISIBILITY_VALUES:
        raise HTTPException(status_code=400, detail=f"visibility must be one of {list(VISIBILITY_VALUES)}")

    if body.visibility == VISIBILITY_HIDDEN and auth_user.role not in ("admin",):
        raise HTTPException(status_code=403, detail="Only admins can create hidden projects")

    token = _get_effective_github_token(user, user_token)
    if not token:
        raise HTTPException(
            status_code=400,
            detail=(
                "No GitHub token available. Sign in with GitHub or ask your server "
                "admin to configure GITHUB_TOKEN."
            ),
        )

    safe_name = "".join(c if c.isalnum() or c in "-_ " else "_" for c in body.name).strip()
    if not safe_name:
        raise HTTPException(status_code=400, detail="Invalid project name")

    project_id = str(uuid.uuid4())
    project_dir = os.path.join(project_service.PROJECTS_ROOT, "type1", project_id)
    os.makedirs(project_dir, exist_ok=True)

    authenticated_url = _inject_token_into_url(body.clone_url, token)

    try:
        result = subprocess.run(
            ["git", "clone", "--depth", "1", authenticated_url, project_dir],
            capture_output=True,
            text=True,
            timeout=SUBPROCESS_TIMEOUT,
        )
        if result.returncode != 0:
            # Mask the token in error messages before logging / returning
            safe_stderr = result.stderr.replace(token, "***")
            logger.error("git clone failed: %s", safe_stderr)
            raise HTTPException(
                status_code=500,
                detail=f"Failed to clone repository: {safe_stderr[:MAX_CLONE_ERROR_MESSAGE_LENGTH]}",
            )
    except subprocess.TimeoutExpired:
        shutil.rmtree(project_dir, ignore_errors=True)
        raise HTTPException(status_code=504, detail="Clone timed out (repository may be too large)")
    except HTTPException:
        shutil.rmtree(project_dir, ignore_errors=True)
        raise
    except Exception as exc:
        shutil.rmtree(project_dir, ignore_errors=True)
        raise HTTPException(status_code=500, detail=f"Clone error: {exc}") from exc

    # Remove the remote so the local repo becomes read-only (no accidental pushes)
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

    # Add the cloning user as a project manager
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
