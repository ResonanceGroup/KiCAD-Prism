# Workspace Behavior Notes

This document summarizes the current workspace behavior in KiCAD Prism rather than a historical changelog.

## Current Workspace Data Flow

The workspace now boots from a single internal endpoint:

```http
GET /api/workspace/bootstrap
```

Response shape:

```json
{
  "projects": [...],
  "folders": [...]
}
```

This replaces the previous need for separate initial requests for project and folder trees in the main workspace load path.

## Search Behavior

Workspace search is client-side and optimized for responsiveness.

Current behavior:
- search input is deferred so typing does not block rendering
- project matching uses fuzzy search across key project fields
- results include display names and descriptions where available

This keeps the workspace responsive without changing project data or server-side semantics.

## Folder and Visibility Model

Workspace folders are role-aware.

Current behavior:
- folder trees are filtered by the current user role
- project visibility respects RBAC assignments
- folder counts and visibility are computed without forcing full project hydration where unnecessary

## Project and Dialog Loading

The non-visualizer application shell is route-split.

Current behavior:
- login, workspace, and project detail routes are lazy-loaded
- settings and import dialogs are deferred until opened
- auth and markdown runtimes are deferred out of the initial shell

This reduces startup cost without changing user-facing features.

## Import Flow Notes

Import and analysis use async jobs.

Current behavior:
- repository analysis and import return a job id
- frontend polls job status during the active flow
- polling is stopped cleanly when dialogs close or unmount
- imported projects can expose comments helper URLs immediately after import

## Why This Matters

The workspace is the highest-frequency surface in the product. These behaviors are aimed at:
- keeping initial load small
- reducing duplicate API work
- avoiding unnecessary background polling
- preserving UI responsiveness on larger project sets

## Related Endpoints

- `GET /api/workspace/bootstrap`
- `GET /api/folders/tree`
- `GET /api/folders/contents`
- `POST /api/projects/analyze`
- `POST /api/projects/import`
- `GET /api/projects/jobs/{job_id}`
