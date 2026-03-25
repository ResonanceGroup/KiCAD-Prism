from typing import Dict, List

from fastapi import APIRouter, Depends
from pydantic import BaseModel
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.security import AuthenticatedUser, require_viewer
from app.db.db import get_async_session
from app.services import folder_service, project_service
from app.services import project_acl_service

router = APIRouter(dependencies=[Depends(require_viewer)])


class WorkspaceBootstrapResponse(BaseModel):
    projects: List[project_service.Project]
    folders: List[folder_service.FolderTreeItem]
    access_map: Dict[str, bool] = {}


@router.get("/bootstrap", response_model=WorkspaceBootstrapResponse)
async def get_workspace_bootstrap(
    user: AuthenticatedUser = Depends(require_viewer),
    session: AsyncSession = Depends(get_async_session),
):
    all_projects = folder_service.filter_projects_for_role(project_service.get_registered_projects(), user.role)

    # Viewers only see projects they have explicit membership in.
    # The Discover tab is where they find and request access to other projects.
    if user.role == "viewer" and not project_acl_service._is_bootstrap_admin(user.email):
        accessible = []
        for p in all_projects:
            m = await project_acl_service.get_membership(session, p.id, user.email)
            if m:
                accessible.append(p)
        projects = accessible
    else:
        projects = all_projects

    access_map: Dict[str, bool] = {p.id: True for p in projects}
    folders = folder_service.get_folder_tree(user.role)
    return WorkspaceBootstrapResponse(projects=projects, folders=folders, access_map=access_map)
