"""
Comments API for KiCAD-Prism Collaboration Feature.

All comment CRUD is backed by SQLite (single source of truth).
comments.json is generated from DB only during push/export workflows.
"""

import os
import re
from typing import List, Optional

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field

from app.api._helpers import get_project_for_role_or_404
from app.core.security import AuthenticatedUser, require_designer, require_viewer
from app.services.comments_store_service import comments_store

router = APIRouter(dependencies=[Depends(require_viewer)])


# ============================================================
# PYDANTIC MODELS
# ============================================================

class CommentLocation(BaseModel):
    x: float
    y: float
    layer: str = ""
    page: str = ""


class CreateCommentRequest(BaseModel):
    context: str  # "PCB" or "SCH"
    location: CommentLocation
    content: str
    author: Optional[str] = "anonymous"


class CreateReplyRequest(BaseModel):
    content: str
    author: Optional[str] = "anonymous"


class UpdateCommentRequest(BaseModel):
    status: Optional[str] = None  # "OPEN" or "RESOLVED"


class CommentReply(BaseModel):
    author: str
    timestamp: str
    content: str


class Comment(BaseModel):
    id: str
    author: str
    timestamp: str
    status: str
    context: str
    location: CommentLocation
    content: str
    replies: List[CommentReply] = Field(default_factory=list)


class CommentsMeta(BaseModel):
    version: str = "1.0"
    generator: str = "KiCad-Prism-Web"


class CommentsFile(BaseModel):
    meta: CommentsMeta = Field(default_factory=CommentsMeta)
    comments: List[Comment] = Field(default_factory=list)


def _normalize_author(author: Optional[str]) -> str:
    return (author or "anonymous").strip() or "anonymous"


def _normalize_context(context: str) -> str:
    normalized = context.upper().strip()
    if normalized not in {"PCB", "SCH"}:
        raise HTTPException(status_code=400, detail="Context must be 'PCB' or 'SCH'")
    return normalized


# ---------------------------------------------------------------------------
# @mention notification helper
# ---------------------------------------------------------------------------

_MENTION_RE = re.compile(r"@([a-zA-Z0-9._%+\-]+@[a-zA-Z0-9.\-]+\.[a-zA-Z]{2,})", re.IGNORECASE)


async def _notify_mentions(
    content: str,
    author: str,
    project_name: str,
    project_id: str,
) -> None:
    """Parse @email mentions in comment text and send email notifications."""
    mentioned = set(_MENTION_RE.findall(content))
    mentioned.discard(author.lower())
    if not mentioned:
        return
    try:
        from app.auth import _send_smtp_email
        for email in mentioned:
            await _send_smtp_email(
                to=email,
                subject=f"You were mentioned in a comment on {project_name}",
                body_html=(
                    f"<p><strong>{author}</strong> mentioned you in a comment on "
                    f"project <strong>{project_name}</strong>:</p>"
                    f"<blockquote>{content}</blockquote>"
                    "<p>Sign in to KiCAD Prism to view the full discussion.</p>"
                ),
            )
    except Exception:
        pass  # notification failure is non-fatal


def _normalize_content(content: str, *, field: str = "content") -> str:
    normalized = content.strip()
    if not normalized:
        raise HTTPException(status_code=400, detail=f"{field.capitalize()} cannot be empty")
    return normalized


# ============================================================
# API ENDPOINTS
# ============================================================

@router.get("/{project_id}/comments")
async def get_comments(project_id: str, user: AuthenticatedUser = Depends(require_viewer)):
    """
    Get all comments for a project from DB snapshot.
    """
    project = get_project_for_role_or_404(project_id, user.role)
    return comments_store.get_comments_file(project.id, project.path)


@router.post("/{project_id}/comments", dependencies=[Depends(require_designer)])
async def create_comment(
    project_id: str,
    request: CreateCommentRequest,
    user: AuthenticatedUser = Depends(require_viewer),
):
    """
    Create a new comment on the design.
    """
    project = get_project_for_role_or_404(project_id, user.role)

    context = _normalize_context(request.context)
    content = _normalize_content(request.content)

    result = comments_store.create_comment(
        project_id=project.id,
        project_path=project.path,
        context=context,
        location=request.location.model_dump(),
        content=content,
        author=_normalize_author(request.author),
    )

    await _notify_mentions(
        content=content,
        author=user.email,
        project_name=project.display_name or project.name,
        project_id=project.id,
    )
    return result


@router.patch("/{project_id}/comments/{comment_id}", dependencies=[Depends(require_designer)])
async def update_comment(
    project_id: str,
    comment_id: str,
    request: UpdateCommentRequest,
    user: AuthenticatedUser = Depends(require_viewer),
):
    """
    Update a comment's status (e.g., resolve it).
    """
    project = get_project_for_role_or_404(project_id, user.role)

    if request.status is None:
        raise HTTPException(status_code=400, detail="No update fields provided")

    status = request.status.upper()
    if status not in {"OPEN", "RESOLVED"}:
        raise HTTPException(status_code=400, detail="Status must be 'OPEN' or 'RESOLVED'")

    updated_comment = comments_store.update_comment_status(
        project_id=project.id,
        project_path=project.path,
        comment_id=comment_id,
        status=status,
    )

    if not updated_comment:
        raise HTTPException(status_code=404, detail="Comment not found")

    return updated_comment


@router.post("/{project_id}/comments/{comment_id}/replies", dependencies=[Depends(require_designer)])
async def add_reply(
    project_id: str,
    comment_id: str,
    request: CreateReplyRequest,
    user: AuthenticatedUser = Depends(require_viewer),
):
    """
    Add a reply to an existing comment.
    """
    project = get_project_for_role_or_404(project_id, user.role)

    result = comments_store.add_reply(
        project_id=project.id,
        project_path=project.path,
        comment_id=comment_id,
        content=_normalize_content(request.content),
        author=_normalize_author(request.author),
    )

    if not result:
        raise HTTPException(status_code=404, detail="Comment not found")

    comment, reply = result

    await _notify_mentions(
        content=_normalize_content(request.content),
        author=user.email,
        project_name=project.display_name or project.name,
        project_id=project.id,
    )
    return {"comment": comment, "reply": reply}


@router.delete("/{project_id}/comments/{comment_id}", dependencies=[Depends(require_designer)])
async def delete_comment(
    project_id: str,
    comment_id: str,
    user: AuthenticatedUser = Depends(require_viewer),
):
    """
    Delete a comment.
    """
    project = get_project_for_role_or_404(project_id, user.role)

    deleted = comments_store.delete_comment(
        project_id=project.id,
        project_path=project.path,
        comment_id=comment_id,
    )

    if not deleted:
        raise HTTPException(status_code=404, detail="Comment not found")

    return {"deleted": comment_id}


# ============================================================
# EXPORT ENDPOINT
# ============================================================

@router.post("/{project_id}/comments/push", dependencies=[Depends(require_designer)])
async def push_comments(project_id: str, user: AuthenticatedUser = Depends(require_viewer)):
    """
    Export DB snapshot to comments.json artifact only.
    Git commit/push is intentionally left to the user workflow.
    """
    project = get_project_for_role_or_404(project_id, user.role)

    try:
        comments_path = comments_store.export_comments_json(project.id, project.path)
        comments_rel_path = os.path.relpath(comments_path, project.path)

        return {
            "success": True,
            "message": "Generated comments artifact from DB snapshot.",
            "comments_path": comments_rel_path,
        }
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Unexpected error: {str(e)}")
