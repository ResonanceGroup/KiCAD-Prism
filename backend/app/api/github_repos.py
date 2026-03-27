"""GitHub repository browsing and cloning endpoints.

All routes are prefixed with /api/github by the router mounting in main.py.

Repository browsing uses the user's OAuth token to enforce GitHub permissions.
Users must have linked their GitHub account via OAuth to browse repositories.
Cloning uses the GitHub App installation token for server-side operations,
but users can only clone repositories they have access to on GitHub.

Flow
----
1.  ``GET  /api/github/repos``        — list repositories the authenticated
    user has access to on GitHub (filtered to ``GITHUB_ORG_LOGIN`` when set).
    Requires the user to have linked their GitHub account.
2.  ``POST /api/github/repos/clone``  — clone a GitHub repository onto the
    server using the App token, register it as a KiCAD Prism project, and
    add the requesting user as a project member with *manager* role.
    Requires the user to have access to the repository on GitHub.
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

from app.auth import get_github_token_for_user
from app.core.config import settings
from app.core.roles import role_meets_minimum
from app.core.security import AuthenticatedUser, get_current_user
from app.db.db import get_async_session
from app.github import get_github_client
from app.github_app import get_app_installation_client, is_app_configured
from app.services import access_service, project_acl_service, project_service
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
    auth_user: AuthenticatedUser = Depends(get_current_user),
    session = Depends(get_async_session),
):
    """Return GitHub repositories the authenticated user has access to.

    Requires the user to have linked their GitHub account via OAuth and have
    at least designer role.
    
    When ``GITHUB_ORG_LOGIN`` is set the list is scoped to that organization;
    otherwise all repositories the user has access to are returned.
    
    This ensures users can only see repositories they have permissions for on GitHub.
    """
    # Verify user has at least designer role (uses role store, respects bootstrap admins)
    if not role_meets_minimum(auth_user.role, "designer"):
        raise HTTPException(
            status_code=403,
            detail="Only designers and admins can browse GitHub repositories",
        )
    
    # Get the user's GitHub OAuth token
    github_token = await get_github_token_for_user(auth_user.email, session)
    
    if not github_token:
        raise HTTPException(
            status_code=403,
            detail=(
                "You must link your GitHub account to browse repositories. "
                "Go to your profile settings to connect your GitHub account."
            ),
        )
    
    _require_app_configured()

    try:
        async with await get_github_client(github_token) as client:
            org = settings.GITHUB_ORG_LOGIN
            if org:
                # List org repos the user has access to
                resp = await client.get(
                    f"/orgs/{org}/repos",
                    params={"per_page": 100, "sort": "updated", "type": "all"},
                )
            else:
                # List all repos the user has access to
                resp = await client.get(
                    "/user/repos",
                    params={"per_page": 100, "sort": "updated", "affiliation": "owner,collaborator,organization_member"},
                )

            if resp.status_code == 401:
                raise HTTPException(
                    status_code=401,
                    detail="Your GitHub token is invalid or expired. Please unlink and re-link your GitHub account.",
                )
            if resp.status_code == 403:
                raise HTTPException(
                    status_code=403,
                    detail="GitHub API rate limit exceeded or insufficient permissions",
                )
            resp.raise_for_status()
            repos = resp.json()

    except HTTPException:
        raise
    except Exception as exc:
        logger.error("Failed to list GitHub repos for user %s: %s", auth_user.email, exc, exc_info=True)
        raise HTTPException(status_code=502, detail=f"GitHub API error: {type(exc).__name__}: {exc}")

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
    auth_user: AuthenticatedUser = Depends(get_current_user),
    session: AsyncSession = Depends(get_async_session),
):
    """Clone a GitHub repository onto the server and register it as a project.

    Requires the user to have linked their GitHub account, have at least designer role,
    and have access to the repository on GitHub.

    - The requesting user is added as a *manager* of the new project.
    - The clone is read-only from GitHub (``origin`` remote is removed after
      cloning to prevent accidental pushes).
    - Visibility is enforced: only admins may create hidden projects.
    """
    # Verify user has at least designer role (uses role store, respects bootstrap admins)
    if not role_meets_minimum(auth_user.role, "designer"):
        raise HTTPException(
            status_code=403,
            detail="Only designers and admins can clone GitHub repositories",
        )
    
    # Get the user's GitHub OAuth token
    github_token = await get_github_token_for_user(auth_user.email, session)
    
    if not github_token:
        raise HTTPException(
            status_code=403,
            detail=(
                "You must link your GitHub account to clone repositories. "
                "Go to your profile settings to connect your GitHub account."
            ),
        )
    
    _require_app_configured()

    if body.visibility not in VISIBILITY_VALUES:
        raise HTTPException(
            status_code=400,
            detail=f"visibility must be one of {list(VISIBILITY_VALUES)}",
        )

    if body.visibility == VISIBILITY_HIDDEN and not role_meets_minimum(auth_user.role, "admin"):
        raise HTTPException(
            status_code=403, detail="Only admins can create hidden projects"
        )

    safe_name = "".join(c if c.isalnum() or c in "-_ " else "_" for c in body.name).strip()
    if not safe_name:
        raise HTTPException(status_code=400, detail="Invalid project name")

    # Verify the user has access to this repository on GitHub
    try:
        # Extract owner/repo from clone URL
        # Format: https://github.com/owner/repo.git
        import re
        match = re.match(r'https://github\.com/([^/]+)/([^/]+?)(?:\.git)?$', body.clone_url)
        if not match:
            raise HTTPException(status_code=400, detail="Invalid GitHub clone URL format")
        
        owner, repo_name = match.groups()
        
        # Check if user has access to this repository
        async with await get_github_client(github_token) as client:
            resp = await client.get(f"/repos/{owner}/{repo_name}")
            
            if resp.status_code == 404:
                raise HTTPException(
                    status_code=404,
                    detail=f"Repository not found or you don't have access to {owner}/{repo_name}",
                )
            if resp.status_code == 403:
                raise HTTPException(
                    status_code=403,
                    detail=f"You don't have permission to access {owner}/{repo_name}",
                )
            resp.raise_for_status()
            
            logger.info(
                "User %s verified to have access to %s/%s",
                auth_user.email,
                owner,
                repo_name,
            )
            
    except HTTPException:
        raise
    except Exception as exc:
        logger.error("Failed to verify repo access for user %s: %s", auth_user.email, exc, exc_info=True)
        raise HTTPException(
            status_code=502,
            detail=f"Failed to verify repository access: {exc}",
        )

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
            ["git", "clone", authenticated_url, project_dir],
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

