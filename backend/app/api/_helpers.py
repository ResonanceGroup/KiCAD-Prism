from pathlib import Path

from fastapi import HTTPException
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.roles import Role
from app.core.security import AuthenticatedUser
from app.services import folder_service, project_service


VALID_OUTPUT_TYPES = {"design", "manufacturing"}


def get_project_or_404(project_id: str) -> project_service.Project:
    project = project_service.get_project_by_id(project_id)
    if not project:
        raise HTTPException(status_code=404, detail="Project not found")
    return project


def get_project_for_role_or_404(project_id: str, role: Role) -> project_service.Project:
    project = get_project_or_404(project_id)
    if not folder_service.is_folder_visible_to_role(project.folder_id, role):
        raise HTTPException(status_code=404, detail="Project not found")
    return project


async def get_project_with_acl(
    project_id: str,
    user: AuthenticatedUser,
    session: AsyncSession,
) -> project_service.Project:
    """Fetch a project and verify the user has access through project-level ACL.

    Combines folder visibility checks with project membership enforcement.
    Returns the project if the user has access, otherwise raises 403 or 404.
    """
    from app.services import project_acl_service

    project = get_project_or_404(project_id)
    if not folder_service.is_folder_visible_to_role(project.folder_id, user.role):
        raise HTTPException(status_code=404, detail="Project not found")

    role = await project_acl_service.resolve_effective_project_role(
        session, project.id, user.email, project.visibility, user.role
    )
    if not role:
        raise HTTPException(
            status_code=403,
            detail="Access denied. Request access to this project first.",
        )
    return project


def require_output_type(value: str) -> str:
    normalized = value.strip().lower()
    if normalized not in VALID_OUTPUT_TYPES:
        raise HTTPException(status_code=400, detail="Type must be 'design' or 'manufacturing'")
    return normalized


def resolve_path_within_root(root: str, relative_path: str, *, invalid_detail: str) -> Path:
    root_path = Path(root).resolve()
    target_path = (root_path / relative_path).resolve()

    try:
        target_path.relative_to(root_path)
    except ValueError as error:
        raise HTTPException(status_code=400, detail=invalid_detail) from error

    return target_path
