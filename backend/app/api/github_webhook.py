"""GitHub App webhook handler.

Receives and verifies webhook events delivered by the GitHub App.

Configure the GitHub App's webhook URL as::

    {APP_URL}/api/github/webhook

All payloads are verified with HMAC-SHA256 against ``GITHUB_WEBHOOK_SECRET``
before any processing takes place.  That secret must match the value set in
the GitHub App's webhook configuration.

Subscribed events (as configured in the GitHub App settings)
------------------------------------------------------------
``create``          — A branch or tag was created.
``commit_comment``  — A comment was made on a commit.
``issues``          — An issue was opened, edited, closed, etc.
``push``            — Commits were pushed to a branch.
                      → Automatically triggers a sync (``git fetch`` + reset)
                        for any locally-registered projects that were cloned
                        from the pushed repository.
"""

from __future__ import annotations

import asyncio
import hashlib
import hmac
import logging
import subprocess
from typing import Any

from fastapi import APIRouter, BackgroundTasks, Header, HTTPException, Request

from app.core.config import settings
from app.services import project_service

router = APIRouter()
logger = logging.getLogger(__name__)

_GIT_SYNC_TIMEOUT = 60  # seconds for each git subprocess call


# ---------------------------------------------------------------------------
# Signature verification
# ---------------------------------------------------------------------------

def _verify_signature(body: bytes, signature_header: str) -> None:
    """Raise HTTP 401 when the HMAC-SHA256 signature does not match.

    If ``GITHUB_WEBHOOK_SECRET`` is not set, a warning is logged and the
    signature check is skipped.  This is acceptable during initial setup but
    **should not be used in production**.
    """
    if not settings.GITHUB_WEBHOOK_SECRET:
        logger.warning(
            "GITHUB_WEBHOOK_SECRET is not configured; skipping webhook signature "
            "verification.  Set this value in .env for production deployments."
        )
        return

    if not signature_header or not signature_header.startswith("sha256="):
        raise HTTPException(
            status_code=401, detail="Missing or malformed X-Hub-Signature-256 header"
        )

    expected = "sha256=" + hmac.new(
        settings.GITHUB_WEBHOOK_SECRET.encode("utf-8"),
        body,
        hashlib.sha256,
    ).hexdigest()

    if not hmac.compare_digest(signature_header, expected):
        raise HTTPException(status_code=401, detail="Webhook signature mismatch")


# ---------------------------------------------------------------------------
# Background sync task (push events)
# ---------------------------------------------------------------------------

async def _sync_project(project_path: str, repo_clone_url: str) -> None:
    """Fetch latest commits and hard-reset the local clone to ``FETCH_HEAD``.

    Authenticates the ``git fetch`` with the GitHub App installation token so
    private repositories are accessible.  Runs the git subprocess in an
    executor thread to avoid blocking the event loop.
    """
    # Local import to avoid module-level circular import during startup
    from app.github_app import get_installation_token

    try:
        token = await get_installation_token()
        authed_url = repo_clone_url.replace(
            "https://", f"https://x-access-token:{token}@", 1
        )
        loop = asyncio.get_event_loop()

        def _git_fetch() -> tuple[int, str]:
            r = subprocess.run(
                ["git", "fetch", authed_url, "--depth", "1"],
                cwd=project_path,
                capture_output=True,
                text=True,
                timeout=_GIT_SYNC_TIMEOUT,
            )
            return r.returncode, r.stderr

        def _git_reset() -> tuple[int, str]:
            r = subprocess.run(
                ["git", "reset", "--hard", "FETCH_HEAD"],
                cwd=project_path,
                capture_output=True,
                text=True,
                timeout=30,
            )
            return r.returncode, r.stderr

        fetch_rc, fetch_err = await loop.run_in_executor(None, _git_fetch)
        if fetch_rc != 0:
            safe_err = fetch_err.replace(token, "***")
            logger.error("git fetch failed for %s: %s", project_path, safe_err[:300])
            return

        reset_rc, reset_err = await loop.run_in_executor(None, _git_reset)
        if reset_rc == 0:
            project_service.invalidate_project_caches()
            logger.info("Auto-synced project at %s via push webhook", project_path)
        else:
            logger.error("git reset failed for %s: %s", project_path, reset_err[:300])

    except Exception as exc:
        logger.error("Error auto-syncing project at %s: %s", project_path, exc)


# ---------------------------------------------------------------------------
# Event handlers
# ---------------------------------------------------------------------------

def _handle_push(payload: dict[str, Any], background_tasks: BackgroundTasks) -> None:
    """Schedule a background sync for any local projects cloned from the repo."""
    clone_url: str = payload.get("repository", {}).get("clone_url", "")
    if not clone_url:
        return

    all_projects = project_service.get_registered_projects()
    matching = [
        p for p in all_projects
        if (p.github_source_url or "").rstrip("/").lower() == clone_url.rstrip("/").lower()
    ]

    if not matching:
        logger.debug(
            "Push webhook for %s — no matching local projects to sync", clone_url
        )
        return

    ref = payload.get("ref", "")
    for project in matching:
        logger.info(
            "Scheduling auto-sync for project %s (ref=%s, repo=%s)",
            project.id, ref, clone_url,
        )
        background_tasks.add_task(_sync_project, project.path, clone_url)


def _handle_create(payload: dict[str, Any]) -> None:
    ref_type = payload.get("ref_type", "")
    ref = payload.get("ref", "")
    repo = payload.get("repository", {}).get("full_name", "unknown")
    logger.info(
        "GitHub create event: %s %r created in %s", ref_type, ref, repo
    )


def _handle_commit_comment(payload: dict[str, Any]) -> None:
    comment = payload.get("comment", {})
    repo = payload.get("repository", {}).get("full_name", "unknown")
    author = comment.get("user", {}).get("login", "unknown")
    body_preview = (comment.get("body") or "")[:120]
    logger.info(
        "GitHub commit_comment event: %s commented on %s: %s",
        author, repo, body_preview,
    )


def _handle_issues(payload: dict[str, Any]) -> None:
    action = payload.get("action", "")
    issue = payload.get("issue", {})
    repo = payload.get("repository", {}).get("full_name", "unknown")
    logger.info(
        "GitHub issues event: #%s %s in %s — %s",
        issue.get("number"), action, repo, (issue.get("title") or "")[:80],
    )


# ---------------------------------------------------------------------------
# Webhook endpoint
# ---------------------------------------------------------------------------

@router.post("/webhook")
async def github_webhook(
    request: Request,
    background_tasks: BackgroundTasks,
    x_hub_signature_256: str = Header(default=""),
    x_github_event: str = Header(default=""),
    x_github_delivery: str = Header(default=""),
) -> dict[str, str]:
    """Receive and process GitHub App webhook events.

    Register this URL in the GitHub App's webhook settings::

        {APP_URL}/api/github/webhook

    All payloads are verified against ``GITHUB_WEBHOOK_SECRET`` before any
    processing takes place.
    """
    body = await request.body()
    _verify_signature(body, x_hub_signature_256)

    logger.debug(
        "GitHub webhook received: event=%s delivery=%s size=%d",
        x_github_event, x_github_delivery, len(body),
    )

    try:
        payload: dict[str, Any] = await request.json()
    except Exception:
        raise HTTPException(status_code=400, detail="Invalid JSON webhook payload")

    event = x_github_event.lower()

    if event == "push":
        _handle_push(payload, background_tasks)
    elif event == "create":
        _handle_create(payload)
    elif event == "commit_comment":
        _handle_commit_comment(payload)
    elif event == "issues":
        _handle_issues(payload)
    elif event == "ping":
        hook_id = payload.get("hook_id", "unknown")
        zen = payload.get("zen", "")
        logger.info(
            "GitHub App webhook ping received (hook_id=%s): %s", hook_id, zen
        )
    else:
        logger.debug("Unhandled GitHub webhook event type: %s", event)

    return {"ok": "true", "event": event, "delivery": x_github_delivery}
