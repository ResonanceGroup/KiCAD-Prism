from typing import List

from fastapi import APIRouter, Depends
from pydantic import BaseModel

from app.core.security import AuthenticatedUser, require_viewer
from app.services import folder_service, project_service

router = APIRouter(dependencies=[Depends(require_viewer)])


class WorkspaceBootstrapResponse(BaseModel):
    projects: List[project_service.Project]
    folders: List[folder_service.FolderTreeItem]


@router.get("/bootstrap", response_model=WorkspaceBootstrapResponse)
async def get_workspace_bootstrap(user: AuthenticatedUser = Depends(require_viewer)):
    projects = folder_service.filter_projects_for_role(project_service.get_registered_projects(), user.role)
    folders = folder_service.get_folder_tree(user.role)
    return WorkspaceBootstrapResponse(projects=projects, folders=folders)
