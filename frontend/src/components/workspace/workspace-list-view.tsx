import { Folder, ShieldAlert, Clock } from "lucide-react";

import { SearchProject } from "@/hooks/use-workspace-search";
import { FolderTreeItem, Project } from "@/types/project";
import { Button } from "@/components/ui/button";
import { Badge } from "@/components/ui/badge";
import { useState } from "react";
import { fetchApi, readApiError } from "@/lib/api";
import { toast } from "sonner";

import { FolderActionMenu, ProjectActionMenu } from "./workspace-action-menus";

interface WorkspaceListViewProps {
  isSearching: boolean;
  selectedProjectId: string | null;
  currentFolderId: string | null;
  breadcrumbs: FolderTreeItem[];
  listFolders: FolderTreeItem[];
  listProjects: Project[];
  getProjectDisplayName: (project: Project) => string;
  onSelectProject: (project: Project) => void;
  onOpenProject: (project: Project) => void;
  onOpenFolder: (folderId: string) => void;
  onRenameFolder: (folder: FolderTreeItem) => void;
  onDeleteFolder: (folder: FolderTreeItem) => void;
  onMoveProject: (project: Project) => void;
  onDeleteProject: (project: Project) => void;
  canManageProjects: boolean;
  accessMap?: Record<string, boolean>;
}

function resolveProjectLocation(
  project: Project,
  isSearching: boolean,
  currentFolderId: string | null,
  breadcrumbs: FolderTreeItem[]
): string {
  if (isSearching && "folder_path" in project) {
    return (project as SearchProject).folder_path;
  }
  if (currentFolderId) {
    return breadcrumbs.map((crumb) => crumb.name).join(" / ");
  }
  return "Workspace Root";
}

interface ListProjectRowProps {
  project: Project;
  isSearching: boolean;
  selectedProjectId: string | null;
  currentFolderId: string | null;
  breadcrumbs: FolderTreeItem[];
  hasAccess: boolean;
  getProjectDisplayName: (project: Project) => string;
  onSelectProject: (project: Project) => void;
  onOpenProject: (project: Project) => void;
  onMoveProject: (project: Project) => void;
  onDeleteProject: (project: Project) => void;
  canManageProjects: boolean;
}

function ListProjectRow({
  project,
  isSearching,
  selectedProjectId,
  currentFolderId,
  breadcrumbs,
  hasAccess,
  getProjectDisplayName,
  onSelectProject,
  onOpenProject,
  onMoveProject,
  onDeleteProject,
  canManageProjects,
}: ListProjectRowProps) {
  const [requestPending, setRequestPending] = useState(false);
  const [showRoleMenu, setShowRoleMenu] = useState(false);

  const handleRequestAccess = async (role: "viewer" | "manager") => {
    try {
      const resp = await fetchApi(`/api/projects/${project.id}/request-access`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ requested_role: role }),
      });
      if (!resp.ok) {
        toast.error(await readApiError(resp, "Request failed"));
        return;
      }
      toast.success("Access request submitted");
      setRequestPending(true);
      setShowRoleMenu(false);
    } catch {
      toast.error("Request failed");
    }
  };

  return (
    <div
      className={`grid grid-cols-[minmax(0,2fr)_minmax(0,2fr)_minmax(0,1.4fr)_minmax(0,1fr)_auto] items-center border-b px-4 py-2 transition-colors ${
        hasAccess
          ? selectedProjectId === project.id ? "bg-primary/5" : "hover:bg-muted/30"
          : "opacity-60"
      }`}
      onClick={() => hasAccess && onSelectProject(project)}
      onDoubleClick={() => hasAccess && onOpenProject(project)}
    >
      <div className="flex min-w-0 items-center gap-2">
        {!hasAccess && <ShieldAlert className="h-3.5 w-3.5 shrink-0 text-muted-foreground" />}
        <button
          type="button"
          className={`truncate text-left text-sm font-medium ${hasAccess ? "hover:text-primary" : "cursor-default"}`}
          onClick={() => hasAccess && onSelectProject(project)}
          onDoubleClick={() => hasAccess && onOpenProject(project)}
        >
          {getProjectDisplayName(project)}
        </button>
      </div>
      <p className="truncate text-sm text-muted-foreground">{project.description || "No description"}</p>
      <p className="truncate text-sm text-muted-foreground">
        {resolveProjectLocation(project, isSearching, currentFolderId, breadcrumbs)}
      </p>
      <p className="truncate text-sm text-muted-foreground">{hasAccess ? project.last_modified : "—"}</p>
      <div
        className="flex justify-end"
        onClick={(event) => event.stopPropagation()}
        onDoubleClick={(event) => event.stopPropagation()}
      >
        {hasAccess ? (
          <ProjectActionMenu
            project={project}
            projectName={getProjectDisplayName(project)}
            onMove={onMoveProject}
            onDelete={onDeleteProject}
            canManage={canManageProjects}
          />
        ) : requestPending ? (
          <Badge variant="outline" className="text-[10px] gap-1 text-yellow-600 dark:text-yellow-400 border-yellow-500/50">
            <Clock className="h-3 w-3" /> Pending
          </Badge>
        ) : showRoleMenu ? (
          <div className="flex items-center gap-1">
            <Button size="sm" variant="default" className="h-6 text-[11px] px-2" onClick={() => handleRequestAccess("viewer")}>
              Viewer
            </Button>
            <Button size="sm" variant="outline" className="h-6 text-[11px] px-2" onClick={() => handleRequestAccess("manager")}>
              Manager
            </Button>
            <Button size="sm" variant="ghost" className="h-6 text-[11px] px-1" onClick={() => setShowRoleMenu(false)}>
              ✕
            </Button>
          </div>
        ) : (
          <Button size="sm" variant="outline" className="h-6 text-[11px] px-2" onClick={() => setShowRoleMenu(true)}>
            Request Access
          </Button>
        )}
      </div>
    </div>
  );
}

export function WorkspaceListView({
  isSearching,
  selectedProjectId,
  currentFolderId,
  breadcrumbs,
  listFolders,
  listProjects,
  getProjectDisplayName,
  onSelectProject,
  onOpenProject,
  onOpenFolder,
  onRenameFolder,
  onDeleteFolder,
  onMoveProject,
  onDeleteProject,
  canManageProjects,
  accessMap,
}: WorkspaceListViewProps) {
  return (
    <div className="overflow-hidden rounded-xl border">
      <div className="grid grid-cols-[minmax(0,2fr)_minmax(0,2fr)_minmax(0,1.4fr)_minmax(0,1fr)_auto] border-b bg-muted/30 px-4 py-2 text-xs font-semibold uppercase tracking-wide text-muted-foreground">
        <div>Name</div>
        <div>Description</div>
        <div>Location</div>
        <div>Updated</div>
        <div className="w-8" />
      </div>

      {listFolders.length === 0 && listProjects.length === 0 ? (
        <div className="p-10 text-center text-sm text-muted-foreground">No items to display.</div>
      ) : (
        <div>
          {listFolders.map((folder) => (
            <div
              key={folder.id}
              className="grid grid-cols-[minmax(0,2fr)_minmax(0,2fr)_minmax(0,1.4fr)_minmax(0,1fr)_auto] items-center border-b px-4 py-2"
            >
              <button
                type="button"
                className="flex min-w-0 items-center gap-2 text-left text-sm font-medium hover:text-primary"
                onClick={() => onOpenFolder(folder.id)}
              >
                <Folder className="h-4 w-4 shrink-0 text-muted-foreground" />
                <span className="truncate">{folder.name}</span>
              </button>
              <p className="truncate text-sm text-muted-foreground">Folder</p>
              <p className="truncate text-sm text-muted-foreground">Current Level</p>
              <p className="truncate text-sm text-muted-foreground">-</p>
              <div className="flex justify-end">
                <FolderActionMenu
                  folder={folder}
                  onRename={onRenameFolder}
                  onDelete={onDeleteFolder}
                  canManage={canManageProjects}
                />
              </div>
            </div>
          ))}

          {listProjects.map((project) => {
            const hasAccess = accessMap ? (accessMap[project.id] ?? true) : true;
            return (
              <ListProjectRow
                key={project.id}
                project={project}
                isSearching={isSearching}
                selectedProjectId={selectedProjectId}
                currentFolderId={currentFolderId}
                breadcrumbs={breadcrumbs}
                hasAccess={hasAccess}
                getProjectDisplayName={getProjectDisplayName}
                onSelectProject={onSelectProject}
                onOpenProject={onOpenProject}
                onMoveProject={onMoveProject}
                onDeleteProject={onDeleteProject}
                canManageProjects={canManageProjects}
              />
            );
          })}
        </div>
      )}
    </div>
  );
}
