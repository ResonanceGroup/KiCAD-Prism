import { FolderPlus, Grid3X3, List, Plus, RefreshCw, Settings, Upload } from "lucide-react";

import { Button } from "@/components/ui/button";

import { ViewMode } from "./workspace-types";

interface WorkspaceProjectToolbarProps {
  viewMode: ViewMode;
  onViewModeChange: (mode: ViewMode) => void;
  onImport: () => void;
  onCreateProject: () => void;
  onCreateFolder: () => void;
  onRefresh: () => void;
  onOpenSettings: () => void;
  canManageProjects: boolean;
  canOpenSettings: boolean;
}

export function WorkspaceProjectToolbar({
  viewMode,
  onViewModeChange,
  onImport,
  onCreateProject,
  onCreateFolder,
  onRefresh,
  onOpenSettings,
  canManageProjects,
  canOpenSettings,
}: WorkspaceProjectToolbarProps) {
  return (
    <div className="flex flex-wrap items-center gap-2 px-4 py-3 md:h-14 md:flex-nowrap md:py-0">
      <div className="inline-flex rounded-md border p-1">
        <Button
          variant={viewMode === "gallery" ? "secondary" : "ghost"}
          size="sm"
          onClick={() => onViewModeChange("gallery")}
        >
          <Grid3X3 className="mr-2 h-4 w-4" />
          Gallery
        </Button>
        <Button
          variant={viewMode === "list" ? "secondary" : "ghost"}
          size="sm"
          onClick={() => onViewModeChange("list")}
        >
          <List className="mr-2 h-4 w-4" />
          List
        </Button>
      </div>

      <div className="ml-auto flex items-center gap-2">
        {canManageProjects && (
          <>
            <Button onClick={onCreateProject}>
              <Plus className="mr-2 h-4 w-4" />
              New Project
            </Button>
            <Button variant="outline" onClick={onImport}>
              <Upload className="mr-2 h-4 w-4" />
              Import
            </Button>
            <Button variant="outline" size="icon" onClick={onCreateFolder} aria-label="Create new folder">
              <FolderPlus className="h-4 w-4" />
            </Button>
          </>
        )}
        <Button variant="outline" size="icon" onClick={onRefresh} aria-label="Refresh workspace">
          <RefreshCw className="h-4 w-4" />
        </Button>
        {canOpenSettings && (
          <Button variant="outline" size="icon" onClick={onOpenSettings} aria-label="Open settings">
            <Settings className="h-4 w-4" />
          </Button>
        )}
      </div>
    </div>
  );
}
